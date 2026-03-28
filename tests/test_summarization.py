from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tldr_feed.models import NormalizedItem
from tldr_feed.summarization import (
    AzureOpenAISummarizer,
    DeterministicSummarizer,
    OllamaSummarizer,
    build_summarizer_from_env,
)
from tldr_feed.utils import utc_now


class SummarizationTests(unittest.TestCase):
    def test_fallback_when_no_abstract_exists(self) -> None:
        item = NormalizedItem(
            item_id="item-1",
            source="linkedin_import",
            source_id="post-1",
            item_type="social_post",
            title="Interesting Post",
            authors_or_author=["Dana"],
            published_at=date(2026, 3, 20),
            discovered_at=utc_now(),
            abstract_or_body=None,
            url="https://www.linkedin.com/posts/example",
            doi=None,
            topic_ids=["edge_ai"],
            raw_hash="hash",
            raw_payload={"id": "post-1"},
            identity_key="url:https://www.linkedin.com/posts/example",
        )
        summary = DeterministicSummarizer().summarize(item)
        self.assertIn("metadata only", summary.short_summary)

    def test_gpt5_payload_uses_max_completion_tokens(self) -> None:
        previous = {key: os.environ.get(key) for key in _AZURE_ENV_KEYS}
        try:
            os.environ["AZURE_OPENAI_ENDPOINT"] = "https://example.openai.azure.com"
            os.environ["AZURE_OPENAI_API_KEY"] = "test-key"
            os.environ["AZURE_OPENAI_API_VERSION"] = "2024-10-21"
            os.environ["AZURE_OPENAI_DEPLOYMENT"] = "gpt-5.4"

            summarizer = AzureOpenAISummarizer()
            payload = summarizer._build_request_payload("Test prompt")

            self.assertEqual(payload["max_completion_tokens"], 1024)
            self.assertNotIn("max_tokens", payload)
            self.assertNotIn("temperature", payload)
        finally:
            _restore_env(previous)

    def test_non_gpt5_payload_uses_chat_completion_shape(self) -> None:
        previous = {key: os.environ.get(key) for key in _AZURE_ENV_KEYS}
        try:
            os.environ["AZURE_OPENAI_ENDPOINT"] = "https://example.openai.azure.com"
            os.environ["AZURE_OPENAI_API_KEY"] = "test-key"
            os.environ["AZURE_OPENAI_API_VERSION"] = "2024-10-21"
            os.environ["AZURE_OPENAI_DEPLOYMENT"] = "gpt-4o"

            summarizer = AzureOpenAISummarizer()
            payload = summarizer._build_request_payload("Test prompt")

            self.assertEqual(payload["max_tokens"], 1024)
            self.assertEqual(payload["temperature"], 0.2)
            self.assertNotIn("max_completion_tokens", payload)
        finally:
            _restore_env(previous)

    def test_build_summarizer_from_env_selects_ollama(self) -> None:
        previous = {key: os.environ.get(key) for key in _SUMMARIZER_ENV_KEYS}
        try:
            os.environ["SUMMARIZER_PROVIDER"] = "ollama"
            os.environ["OLLAMA_MODEL"] = "llama3.1:8b"

            summarizer = build_summarizer_from_env()

            self.assertIsInstance(summarizer, OllamaSummarizer)
        finally:
            _restore_env(previous)

    def test_ollama_payload_uses_local_generate_shape(self) -> None:
        previous = {key: os.environ.get(key) for key in _SUMMARIZER_ENV_KEYS}
        try:
            os.environ["OLLAMA_MODEL"] = "llama3.1:8b"
            summarizer = OllamaSummarizer()

            payload = summarizer._build_request_payload("Test prompt")

            self.assertEqual(payload["model"], "llama3.1:8b")
            self.assertEqual(payload["prompt"], "Test prompt")
            self.assertEqual(payload["stream"], False)
            self.assertEqual(payload["options"]["temperature"], 0.2)
            self.assertEqual(payload["options"]["num_predict"], 1024)
        finally:
            _restore_env(previous)

    def test_ollama_summary_uses_response_field(self) -> None:
        previous = {key: os.environ.get(key) for key in _SUMMARIZER_ENV_KEYS}
        try:
            os.environ["OLLAMA_MODEL"] = "llama3.1:8b"
            summarizer = OllamaSummarizer()
            item = _build_item(abstract_or_body="A short abstract about autonomous vessels.")

            with patch("tldr_feed.summarization.urlopen", return_value=_FakeResponse({"response": "Local summary"})):
                summary = summarizer.summarize(item)

            self.assertEqual(summary.short_summary, "Local summary")
            self.assertEqual(summary.provider, "ollama:llama3.1:8b")
        finally:
            _restore_env(previous)


_AZURE_ENV_KEYS = [
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_DEPLOYMENT",
]

_SUMMARIZER_ENV_KEYS = _AZURE_ENV_KEYS + [
    "SUMMARIZER_PROVIDER",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OLLAMA_TIMEOUT_SECONDS",
]


def _restore_env(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _build_item(abstract_or_body: str | None) -> NormalizedItem:
    return NormalizedItem(
        item_id="item-1",
        source="openalex",
        source_id="W123",
        item_type="paper",
        title="Interesting Paper",
        authors_or_author=["Dana"],
        published_at=date(2026, 3, 20),
        discovered_at=utc_now(),
        abstract_or_body=abstract_or_body,
        url="https://example.org/paper",
        doi=None,
        topic_ids=["ship_autonomy"],
        raw_hash="hash",
        raw_payload={"id": "W123"},
        identity_key="url:https://example.org/paper",
    )


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._payload
