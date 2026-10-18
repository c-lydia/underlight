"""Index failures must not change the last successfully published snapshot."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import indexer

try:
    import lancedb
except ImportError:
    lancedb = None


@unittest.skipIf(lancedb is None, "LanceDB is not installed")
class IndexSafetyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.note = self.source / "note.md"
        self.note.write_text("original content")
        self.other = self.source / "other.md"
        self.other.write_text("other content")
        self.db = lancedb.connect(self.root / "store")
        self.config = {"embedder": {"model": "test-v1", "device": "cpu", "batch_size": 1},
                       "chunking": {"text": {"max_tokens": 100, "overlap_tokens": 10}}}
        self.source_config = {"root": str(self.source), "extensions": [".md"]}
        self.embedder = Mock()
        self.embedder.embed.side_effect = lambda texts: [[1., .5, .2] for _ in texts]
        self.run_index()
        self.embedder.reset_mock()

    def run_index(self, **kwargs):
        return indexer.index_dir(self.source_config, "docs", "test", self.config, self.embedder, self.db, **kwargs)

    def snapshot(self):
        table = self.db.open_table("docs")
        return table.version, sorted(table.to_arrow().to_pylist(), key=lambda row: row["id"])

    def test_failed_rebuild_preserves_original_after_partial_embedding(self):
        before = self.snapshot()
        self.embedder.embed.side_effect = [[[1., .5, .2]], RuntimeError("offline")]
        with self.assertRaisesRegex(RuntimeError, "offline"):
            self.run_index(rebuild=True)
        self.assertEqual(self.snapshot(), before)

    def test_failed_incremental_embedding_preserves_original(self):
        before = self.snapshot()
        self.note.write_text("changed content")
        self.embedder.embed.side_effect = RuntimeError("offline")
        with self.assertRaisesRegex(RuntimeError, "offline"):
            self.run_index()
        self.assertEqual(self.snapshot(), before)

    def test_read_error_preserves_content_for_normal_and_rebuild_runs(self):
        before = self.snapshot()
        original_read = Path.read_text
        def read(path, *args, **kwargs):
            if path == self.note:
                raise PermissionError("unreadable")
            return original_read(path, *args, **kwargs)
        for rebuild in (False, True):
            with self.subTest(rebuild=rebuild), patch.object(Path, "read_text", read):
                with self.assertRaisesRegex(RuntimeError, "previous index preserved"):
                    self.run_index(rebuild=rebuild)
            self.assertEqual(self.snapshot(), before)

    def test_missing_ocr_dependency_does_not_replace_index(self):
        before = self.snapshot()
        (self.source / "image.png").write_bytes(b"fixture")
        self.source_config.update(extensions=[".md", ".png"], ocr={"enabled": True})
        with patch.object(indexer, "ocr_image", side_effect=ImportError("OCR missing")):
            with self.assertRaisesRegex(RuntimeError, "previous index preserved"):
                self.run_index()
        self.assertEqual(self.snapshot(), before)

    def test_cache_reuses_unchanged_chunks_and_deletes_removed_files(self):
        self.run_index()
        self.embedder.embed.assert_not_called()
        self.note.write_text("new content")
        self.run_index()
        self.embedder.embed.assert_called_once_with(["new content"])
        self.embedder.reset_mock()
        self.other.unlink()
        self.run_index()
        self.embedder.embed.assert_not_called()
        self.assertEqual([row["text"] for row in self.snapshot()[1]], ["new content"])

    def test_model_change_requires_rebuild_even_with_same_dimension(self):
        before = self.snapshot()
        self.config["embedder"]["model"] = "test-v2"
        with self.assertRaisesRegex(RuntimeError, "configuration changed"):
            self.run_index()
        self.assertEqual(self.snapshot(), before)
        self.run_index(rebuild=True)
        self.assertEqual(self.embedder.embed.call_count, 2)
        self.embedder.reset_mock()
        self.run_index()
        self.embedder.embed.assert_not_called()

    def test_legacy_table_without_model_metadata_is_reembedded(self):
        table = self.db.open_table("docs").to_arrow().replace_schema_metadata(None)
        self.db.create_table("docs", data=table, mode="overwrite")
        self.run_index()
        self.assertEqual(self.embedder.embed.call_count, 2)

    def test_failed_publish_preserves_previous_lancedb_version(self):
        import pyarrow as pa
        before = self.snapshot()
        create = self.db.create_table
        def fail_during_write(name, *, data, schema, mode):
            def batches():
                yield next(data)
                raise RuntimeError("simulated staging read failure")
            return create(name, data=pa.RecordBatchReader.from_batches(schema, batches()), schema=schema, mode=mode)
        with patch.object(self.db, "create_table", side_effect=fail_during_write):
            with self.assertRaises(Exception):
                self.run_index(rebuild=True)
        self.assertEqual(self.snapshot(), before)

    def test_empty_rebuild_keeps_an_empty_searchable_table(self):
        self.note.unlink()
        self.other.unlink()
        self.run_index(rebuild=True)
        self.assertEqual(self.db.open_table("docs").count_rows(), 0)

    def test_normal_update_preserves_other_projects(self):
        other_source = self.root / "second"
        other_source.mkdir()
        (other_source / "second.md").write_text("second project")
        indexer.index_dir({"root": str(other_source), "extensions": [".md"]}, "docs", "second",
                          self.config, self.embedder, self.db)
        self.note.unlink()
        self.run_index()
        self.assertEqual({row["text"] for row in self.snapshot()[1]}, {"second project", "other content"})

    def test_scan_failure_does_not_treat_unreadable_directory_as_deleted(self):
        before = self.snapshot()
        def walk(root, *, onerror):
            onerror(PermissionError("unreadable directory"))
            return iter(())
        with patch.object(indexer.os, "walk", side_effect=walk):
            with self.assertRaises(PermissionError):
                self.run_index()
        self.assertEqual(self.snapshot(), before)

    def test_concurrent_update_is_not_overwritten(self):
        original = self.db.open_table("docs").to_arrow()
        def embed(texts):
            self.db.create_table("docs", data=original, mode="overwrite")
            return [[1., .5, .2] for _ in texts]
        self.embedder.embed.side_effect = embed
        with self.assertRaisesRegex(RuntimeError, "Index changed during this run"):
            self.run_index(rebuild=True)
        self.assertEqual(self.snapshot()[1], sorted(original.to_pylist(), key=lambda row: row["id"]))

    def test_empty_table_can_adopt_a_new_vector_dimension(self):
        self.note.unlink()
        self.other.unlink()
        self.config["embedder"]["model"] = "four-dimensions"
        self.run_index(rebuild=True)
        self.note.write_text("new content")
        self.embedder.embed.side_effect = lambda texts: [[1., .5, .2, .1] for _ in texts]
        self.run_index()
        self.assertEqual(self.db.open_table("docs").schema.field("embedding").type.list_size, 4)
