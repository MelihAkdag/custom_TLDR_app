from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tldr_feed.models import NormalizedItem
from tldr_feed.summarization import AzureOpenAISummarizer, DeterministicSummarizer
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

            self.assertEqual(payload["max_completion_tokens"], 240)
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

            self.assertEqual(payload["max_tokens"], 240)
            self.assertEqual(payload["temperature"], 0.2)
            self.assertNotIn("max_completion_tokens", payload)
        finally:
            _restore_env(previous)


_AZURE_ENV_KEYS = [
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_DEPLOYMENT",
]


def _restore_env(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
