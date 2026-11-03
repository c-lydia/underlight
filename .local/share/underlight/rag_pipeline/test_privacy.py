"""Verify the disclosure boundary before retrieval and after generation."""
import importlib
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


class PrivacyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {'RAG_CONFIG': str(Path(__file__).with_name('.ragconfig.example.yaml'))}):
            # These tests need the policy/dispatcher, not a database installation.
            with patch.dict(sys.modules, {'lancedb': Mock()}):
                cls.server = importlib.import_module('rag_mcp_server')

    def test_local_mode_denies_both_exports_before_retrieval(self):
        with patch.dict(os.environ, {'UNDERLIGHT_PRIVACY': 'local'}), patch.object(self.server, 'retrieve') as retrieve:
            for name in ('search_local_knowledge', 'ask_local_assistant'):
                response = self.server.dispatch({'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': {'query': 'q'}}})
                self.assertTrue(response['result']['isError'])
            retrieve.assert_not_called()

    def test_answer_mode_never_returns_raw_chunks(self):
        chunk = {'text': 'RAW NOTE CONTENT', 'score': 1, 'path': 'notes/example.md'}
        with patch.dict(os.environ, {'UNDERLIGHT_PRIVACY': 'local-answer'}), \
                patch.object(self.server, 'retrieve', return_value=[chunk]), \
                patch.object(self.server, 'ask_ollama', return_value='local answer'):
            result = self.server.ask_local_assistant_impl('question')
            self.assertEqual(result['answer'], 'local answer')
            self.assertNotIn('RAW NOTE CONTENT', str(result))
            self.assertEqual(result['sources'][0]['path'], 'notes/example.md')
            with self.assertRaises(ValueError):
                self.server.search_local_knowledge_impl('question')

    def test_cloud_context_is_required_to_return_search_chunks(self):
        with patch.dict(os.environ, {'UNDERLIGHT_PRIVACY': 'cloud-context'}), \
                patch.object(self.server, 'retrieve', return_value=[{'text': 'explicitly allowed'}]):
            self.assertEqual(self.server.search_local_knowledge_impl('q')['results'][0]['text'], 'explicitly allowed')

    def test_switching_to_local_during_inference_blocks_the_result(self):
        def generate(*args, **kwargs):
            os.environ['UNDERLIGHT_PRIVACY'] = 'local'
            return 'answer'
        with patch.dict(os.environ, {'UNDERLIGHT_PRIVACY': 'local-answer'}), \
                patch.object(self.server, 'retrieve', return_value=[]), \
                patch.object(self.server, 'ask_ollama', side_effect=generate):
            with self.assertRaises(ValueError):
                self.server.ask_local_assistant_impl('q')

    def test_remote_generation_and_embedding_are_rejected_before_http(self):
        import assistant
        from rag_core import Embedder
        with patch.dict(assistant.cfg['ollama'], {'base_url': 'https://remote.example'}), \
                patch.object(assistant.requests, 'post') as post:
            with self.assertRaises(ValueError):
                assistant.ask_ollama('private prompt')
            embedder = Embedder({'embedder': {'device': 'ollama', 'model': 'embed'},
                                 'ollama': {'base_url': 'https://remote.example'}})
            with self.assertRaises(ValueError):
                embedder.embed(['private note'])
            post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
