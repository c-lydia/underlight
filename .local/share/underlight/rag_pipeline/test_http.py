"""Exercise the HTTP handler with in-memory requests and mocked backends."""
import importlib
import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"RAG_CONFIG": str(Path(__file__).with_name(".ragconfig.example.yaml"))}):
            cls.server = importlib.import_module("rag_server")

    def request(self, data, path="/ask", headers=None):
        body = json.dumps(data).encode()
        handler = object.__new__(self.server.RagHandler)
        handler.path = path
        handler.headers = headers or {"Content-Length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        handler._json = Mock()
        handler.do_POST()
        return handler._json.call_args.args

    def test_malformed_objects_and_fields_return_400_without_backend_calls(self):
        cases = [[], None, "text", {"query": 1}, {"query": " "},
                 {"query": "q", "top_k": True}, {"query": "q", "top_k": 1.5},
                 {"query": "q", "tables": "projects"}, {"query": "q", "tables": []},
                 {"query": "q", "remember": "false"}, {"query": "q", "project": []},
                 {"query": "q", "system_prompt": {}}]
        with patch.object(self.server, "retrieve") as retrieve:
            for case in cases:
                with self.subTest(case=case):
                    self.assertEqual(self.request(case)[0], 400)
            retrieve.assert_not_called()

    def test_bad_lengths_and_large_bodies_are_rejected(self):
        for length, status in [("-1", 400), ("invalid", 400), (str(2**30), 413)]:
            with self.subTest(length=length):
                self.assertEqual(self.request({}, headers={"Content-Length": length})[0], status)

    def test_log_failure_is_not_reported_as_success(self):
        with patch.object(self.server, "log_chat", return_value={"error": "disk full"}):
            status, body = self.request({"text": "message"}, "/log")
        self.assertEqual(status, 500)
        self.assertFalse(body["logged"])

    def test_log_validates_types_and_reports_success(self):
        with patch.object(self.server, "log_chat", return_value={"id": "test"}) as log:
            for data in ({"text": []}, {"text": "text", "role": []}, {"text": "text", "project": 1}):
                self.assertEqual(self.request(data, "/log")[0], 400)
            log.assert_not_called()
            self.assertEqual(self.request({"text": "message"}, "/log"), (200, {"logged": True, "result": {"id": "test"}}))

    def test_backend_failure_returns_error_without_remembering(self):
        with patch.object(self.server, "retrieve", side_effect=RuntimeError("database unavailable")):
            self.assertEqual(self.request({"query": "q"})[0], 503)
        with patch.object(self.server, "retrieve", return_value=[]), \
                patch.object(self.server, "ask_ollama", side_effect=RuntimeError("offline")), \
                patch.object(self.server, "log_chat") as log:
            self.assertEqual(self.request({"query": "q"})[0], 502)
            log.assert_not_called()

    def test_success_uses_configured_context_and_propagates_memory_failure(self):
        with patch.object(self.server, "retrieve", return_value=[]), \
                patch.object(self.server, "ask_ollama", return_value="answer") as ask:
            status, body = self.request({"query": "q"})
            self.assertEqual((status, body["answer"]), (200, "answer"))
            self.assertTrue(ask.call_args.kwargs["raise_on_error"])
            with patch.dict(os.environ, {"RAG_CONFIG": str(Path(__file__).with_name(".ragconfig.example.yaml"))}), \
                    patch("chat_tracker.query_chat", return_value=[]), \
                    patch.object(self.server, "log_chat", return_value={"error": "write failed"}):
                status, body = self.request({"query": "q", "remember": True})
                self.assertEqual(status, 500)
                self.assertFalse(body["logged"])

    def test_ollama_errors_can_be_raised_instead_of_returned_as_answers(self):
        import assistant
        with patch.object(assistant.requests, "post", side_effect=assistant.requests.exceptions.ConnectionError):
            with self.assertRaisesRegex(RuntimeError, "Cannot reach"):
                assistant.ask_ollama("q", raise_on_error=True)
            self.assertTrue(assistant.ask_ollama("q").startswith("[ERROR:"))
