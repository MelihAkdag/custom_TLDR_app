from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import URLError
from unittest.mock import patch
import ssl

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tldr_feed.models import SourceSettings, TopicProfile
from tldr_feed.sources.arxiv import ArxivAdapter
from tldr_feed.sources.base import SourceAdapter
from tldr_feed.sources.crossref import CrossrefAdapter
from tldr_feed.sources.openalex import OpenAlexAdapter


class SourceParsingTests(unittest.TestCase):
    def test_arxiv_parser_extracts_entries(self) -> None:
        payload = """
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1234.5678v1</id>
    <published>2026-03-18T12:00:00Z</published>
    <title>Edge AI for Sensors</title>
    <summary>Compact models for distributed sensors.</summary>
    <author><name>Alice Example</name></author>
    <author><name>Bob Example</name></author>
  </entry>
</feed>
""".strip()
        items = ArxivAdapter.parse_response(payload, "edge_ai")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_id, "1234.5678v1")
        self.assertEqual(items[0].authors_or_author, ["Alice Example", "Bob Example"])

    def test_openalex_parser_rebuilds_abstract(self) -> None:
        payload = {
            "results": [
                {
                    "id": "https://openalex.org/W1",
                    "title": "TinyML Systems",
                    "publication_date": "2026-03-20",
                    "doi": "https://doi.org/10.1000/TINY",
                    "abstract_inverted_index": {"TinyML": [0], "systems": [1], "scale": [2]},
                    "authorships": [{"author": {"display_name": "Alice Example"}}],
                    "primary_location": {"landing_page_url": "https://example.org/tinyml"},
                }
            ]
        }
        items = OpenAlexAdapter.parse_response(payload, "edge_ai")
        self.assertEqual(items[0].doi, "10.1000/tiny")
        self.assertEqual(items[0].abstract_or_body, "TinyML systems scale")

    def test_crossref_parser_strips_html(self) -> None:
        payload = {
            "message": {
                "items": [
                    {
                        "DOI": "10.1000/xyz",
                        "URL": "https://doi.org/10.1000/xyz",
                        "title": ["Hydrogen Study"],
                        "abstract": "<jats:p>Hydrogen output improved.</jats:p>",
                        "author": [{"given": "Ada", "family": "Lovelace"}],
                        "issued": {"date-parts": [[2026, 3, 21]]},
                    }
                ]
            }
        }
        items = CrossrefAdapter.parse_response(payload, "renewable_hydrogen")
        self.assertEqual(items[0].authors_or_author, ["Ada Lovelace"])
        self.assertEqual(items[0].abstract_or_body, "Hydrogen output improved.")


class DummyAdapter(SourceAdapter):
    source_name = "dummy"

    def search(self, topic: TopicProfile, start_date, end_date):
        return []


class SourceAdapterSslTests(unittest.TestCase):
    def test_ssl_context_disables_verification_when_source_requests_it(self) -> None:
        adapter = DummyAdapter(SourceSettings(name="dummy", extra={"verify_ssl": False}))

        context = adapter._build_ssl_context()

        self.assertFalse(context.check_hostname)

    def test_ssl_context_disables_verification_when_env_requests_it(self) -> None:
        adapter = DummyAdapter(SourceSettings(name="dummy"))

        with patch.dict("os.environ", {"TLDR_FEED_INSECURE_SSL": "true"}, clear=False):
            context = adapter._build_ssl_context()

        self.assertFalse(context.check_hostname)

    def test_ssl_context_uses_configured_ca_bundle(self) -> None:
        with NamedTemporaryFile() as handle:
            adapter = DummyAdapter(SourceSettings(name="dummy", extra={"ca_bundle": handle.name}))

            with patch("tldr_feed.sources.base.ssl.create_default_context") as mock_create_context:
                mock_create_context.return_value = object()

                context = adapter._build_ssl_context()

        self.assertIs(context, mock_create_context.return_value)
        mock_create_context.assert_called_once_with(cafile=handle.name)

    def test_ssl_context_uses_env_ca_bundle(self) -> None:
        with NamedTemporaryFile() as handle:
            adapter = DummyAdapter(SourceSettings(name="dummy"))

            with (
                patch.dict("os.environ", {"TLDR_FEED_CA_BUNDLE": handle.name}, clear=False),
                patch("tldr_feed.sources.base.ssl.create_default_context") as mock_create_context,
            ):
                mock_create_context.return_value = object()

                context = adapter._build_ssl_context()

        self.assertIs(context, mock_create_context.return_value)
        mock_create_context.assert_called_once_with(cafile=handle.name)

    def test_get_text_explains_ssl_failure(self) -> None:
        adapter = DummyAdapter(SourceSettings(name="dummy"))
        ssl_error = ssl.SSLCertVerificationError(
            1,
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed",
        )

        with patch("tldr_feed.sources.base.urlopen", side_effect=URLError(ssl_error)):
            with self.assertRaisesRegex(RuntimeError, "Configure TLDR_FEED_CA_BUNDLE"):
                adapter._get_text("https://example.org/feed", params={})
