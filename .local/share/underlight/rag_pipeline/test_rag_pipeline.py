from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from config_loader import load_config
from indexer import chunk_code, chunk_text, should_index
from rag_core import Embedder, cosine_score, sql_string

try:
    import lancedb
except ImportError:
    lancedb = None


class RagPipelineTests(unittest.TestCase):
    def test_config_expands_home_and_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rag.yaml"
            path.write_text(
                """embedder: {model: test, device: cpu}
store: {dir: '$RAG_TEST_ROOT/store'}
ollama: {base_url: 'http://localhost:11434'}
assistant: {}
chat: {}
chunking: {}
""",
                encoding="utf-8",
            )
            previous = os.environ.get("RAG_TEST_ROOT")
            os.environ["RAG_TEST_ROOT"] = directory
            try:
                config = load_config(path)
            finally:
                if previous is None:
                    os.environ.pop("RAG_TEST_ROOT", None)
                else:
                    os.environ["RAG_TEST_ROOT"] = previous
            self.assertEqual(config["store"]["dir"], f"{directory}/store")

    def test_code_chunking_uses_definition_boundaries(self):
        chunks = chunk_code("header = 1\n\ndef one():\n    pass\n\nclass Two:\n    pass")
        self.assertEqual(len(chunks), 3)
        self.assertTrue(chunks[1].startswith("def one"))
        self.assertTrue(chunks[2].startswith("class Two"))

    def test_text_chunking_discards_blank_paragraphs(self):
        self.assertEqual(chunk_text("first\n\n\nsecond"), ["first", "second"])

    def test_source_filters_honor_include_exclude_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src"
            source.mkdir()
            keep = source / "keep.py"
            keep.write_text("pass", encoding="utf-8")
            ignored = source / "cache.pyc"
            ignored.write_bytes(b"x")
            link = root / "linked.py"
            link.symlink_to(keep)
            config = {"include": ["src/**"], "exclude": ["cache*"], "extensions": [".py"]}
            self.assertTrue(should_index(keep, root, config))
            self.assertFalse(should_index(ignored, root, config))
            self.assertFalse(should_index(link, root, config))

    def test_embedder_is_lazy_and_normalizes_sentence_vectors(self):
        class FakeModel:
            def encode(self, texts, **kwargs):
                self.kwargs = kwargs

                class Vectors:
                    @staticmethod
                    def tolist():
                        return [[1.0, 0.0]]

                return Vectors()

        embedder = Embedder({"embedder": {"model": "fake", "device": "cpu", "batch_size": 2}})
        fake = FakeModel()
        embedder._model = fake
        self.assertEqual(embedder.embed(["hello"]), [[1.0, 0.0]])
        self.assertTrue(fake.kwargs["normalize_embeddings"])

    def test_distance_and_sql_helpers(self):
        self.assertAlmostEqual(cosine_score(0.25), 0.75)
        self.assertEqual(sql_string("Lydia's"), "'Lydia''s'")

    def test_upsert_boundary_deduplicates_document_ids(self):
        from rag_core import upsert_rows

        class Merge:
            def when_matched_update_all(self):
                return self

            def when_not_matched_insert_all(self):
                return self

            def execute(self, data):
                self.data = data

        class Table:
            def merge_insert(self, key):
                self.key = key
                self.merge = Merge()
                return self.merge

        try:
            import pyarrow as pa
        except ImportError:
            self.skipTest("PyArrow is not installed")
        schema = pa.schema([pa.field("id", pa.string()), pa.field("text", pa.string())])
        table = Table()
        upsert_rows(table, [
            {"id": "same", "text": "first"},
            {"id": "same", "text": "second"},
        ], schema)
        self.assertEqual(table.merge.data.num_rows, 1)
        self.assertEqual(table.merge.data.to_pylist()[0]["text"], "second")

    @unittest.skipIf(lancedb is None, "LanceDB is not installed")
    def test_incremental_index_replaces_changed_and_deleted_chunks(self):
        from indexer import index_dir

        class FakeEmbedder:
            @staticmethod
            def embed(texts):
                return [[1.0, float(len(text) % 7), 0.5] for text in texts]

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source_root = base / "source"
            source_root.mkdir()
            document = source_root / "note.md"
            document.write_text("first version", encoding="utf-8")
            source = {
                "root": str(source_root),
                "include": ["*"],
                "exclude": [],
                "extensions": [".md"],
            }
            config = {
                "embedder": {"batch_size": 4},
                "chunking": {
                    "code": {"max_tokens": 10, "overlap_tokens": 2},
                    "text": {"max_tokens": 10, "overlap_tokens": 2},
                }
            }
            db = lancedb.connect(base / "store")

            index_dir(source, "documents", "test", config, FakeEmbedder(), db)
            table = db.open_table("documents")
            self.assertEqual(table.count_rows(), 1)
            self.assertEqual(table.to_arrow().to_pylist()[0]["text"], "first version")

            document.write_text("second version", encoding="utf-8")
            index_dir(source, "documents", "test", config, FakeEmbedder(), db)
            table = db.open_table("documents")
            self.assertEqual(table.count_rows(), 1)
            self.assertEqual(table.to_arrow().to_pylist()[0]["text"], "second version")

            document.write_text("repeated paragraph\n\nrepeated paragraph", encoding="utf-8")
            count = index_dir(source, "documents", "test", config, FakeEmbedder(), db)
            table = db.open_table("documents")
            self.assertEqual(count, 1)
            self.assertEqual(table.count_rows(), 1)

            document.unlink()
            index_dir(source, "documents", "test", config, FakeEmbedder(), db)
            table = db.open_table("documents")
            self.assertEqual(table.count_rows(), 0)

    @unittest.skipUnless(os.environ.get("UNDERLIGHT_RAG_OLLAMA_TEST"), "local Ollama test disabled")
    def test_local_ollama_index_and_search(self):
        from indexer import index_dir

        config = load_config()
        embedder = Embedder(config)
        source = {
            "root": str(Path(__file__).parent),
            "include": ["README.md"],
            "exclude": [],
            "extensions": [".md"],
        }
        with tempfile.TemporaryDirectory() as directory:
            db = lancedb.connect(Path(directory) / "store")
            count = index_dir(source, "documents", "test", config, embedder, db)
            self.assertGreater(count, 0)
            query = embedder.embed(["How do I ask the local RAG from Neovim?"])[0]
            hits = (db.open_table("documents")
                    .search(query, vector_column_name="embedding")
                    .distance_type("cosine").limit(3).to_list())
            self.assertTrue(hits)
            self.assertTrue(all(hit["path"].endswith("README.md") for hit in hits))
            self.assertTrue(all("_distance" in hit for hit in hits))


if __name__ == "__main__":
    unittest.main()
