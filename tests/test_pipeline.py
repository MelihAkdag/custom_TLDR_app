from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import tldr_feed.pipeline as pipeline_module
from tldr_feed.models import AppConfig, RawItem, SourceSettings, TopicProfile
from tldr_feed.pipeline import collect_items, normalize_raw_item, summarize_run, write_report
from tldr_feed.sources import SOURCE_REGISTRY
from tldr_feed.sources.base import SourceAdapter
from tldr_feed.storage import Storage
from tldr_feed.summarization import DeterministicSummarizer
from tldr_feed.utils import utc_now


class FakePrimaryAdapter(SourceAdapter):
    source_name = "fake_primary"

    def search(self, topic: TopicProfile, start_date: date, end_date: date) -> list[RawItem]:
        return [
            RawItem(
                source=self.source_name,
                source_id="paper-a",
                item_type="paper",
                title="Shared Paper",
                authors_or_author=["Alice"],
                published_at=date(2026, 3, 18),
                discovered_at=utc_now(),
                abstract_or_body="A shared paper about edge AI deployment.",
                url="https://example.org/shared-paper",
                doi="10.1000/shared",
                topic_id=topic.topic_id,
                raw_payload={"source": self.source_name, "id": "paper-a"},
            ),
            RawItem(
                source=self.source_name,
                source_id="paper-b",
                item_type="paper",
                title="Edge AI Deployment Study",
                authors_or_author=["Bob"],
                published_at=date(2026, 3, 19),
                discovered_at=utc_now(),
                abstract_or_body="A unique paper about edge AI deployment in embedded systems.",
                url="https://example.org/unique-paper",
                doi=None,
                topic_id=topic.topic_id,
                raw_payload={"source": self.source_name, "id": "paper-b"},
            ),
        ]


class FakeSecondaryAdapter(SourceAdapter):
    source_name = "fake_secondary"

    def search(self, topic: TopicProfile, start_date: date, end_date: date) -> list[RawItem]:
        return [
            RawItem(
                source=self.source_name,
                source_id="shared-copy",
                item_type="paper",
                title="Shared Paper",
                authors_or_author=["Alice", "Carol"],
                published_at=date(2026, 3, 18),
                discovered_at=utc_now(),
                abstract_or_body="Expanded abstract for the shared paper about edge AI deployment.",
                url="https://mirror.example.org/shared-paper",
                doi="10.1000/shared",
                topic_id=topic.topic_id,
                raw_payload={"source": self.source_name, "id": "shared-copy"},
            )
        ]


class BrokenAdapter(SourceAdapter):
    source_name = "broken_source"

    def search(self, topic: TopicProfile, start_date: date, end_date: date) -> list[RawItem]:
        raise RuntimeError("boom")


class FakeNewsAdapter(SourceAdapter):
    source_name = "fake_news"

    def search(self, topic: TopicProfile, start_date: date, end_date: date) -> list[RawItem]:
        return [
            RawItem(
                source=self.source_name,
                source_id="news-a",
                item_type="news_article",
                title="Edge AI Trial Expands",
                authors_or_author=["Maritime News"],
                published_at=date(2026, 3, 20),
                discovered_at=utc_now(),
                abstract_or_body="A new edge AI deployment trial expands embedded collision avoidance testing.",
                url="https://news.example.org/edge-ai-trial",
                doi=None,
                topic_id=topic.topic_id,
                raw_payload={"source": self.source_name, "id": "news-a"},
            )
        ]


class FakeLanguageAdapter(SourceAdapter):
    source_name = "fake_language"

    def search(self, topic: TopicProfile, start_date: date, end_date: date) -> list[RawItem]:
        return [
            RawItem(
                source=self.source_name,
                source_id="english-item",
                item_type="paper",
                title="Autonomous ship collision avoidance study",
                authors_or_author=["Alice"],
                published_at=date(2026, 3, 20),
                discovered_at=utc_now(),
                abstract_or_body="A maritime vessel navigation study with collision avoidance results.",
                url="https://example.org/english",
                doi=None,
                topic_id=topic.topic_id,
                raw_payload={"id": "english-item", "language": "en"},
            ),
            RawItem(
                source=self.source_name,
                source_id="explicit-ru-item",
                item_type="paper",
                title="Autonomous ship structural model",
                authors_or_author=["Bob"],
                published_at=date(2026, 3, 20),
                discovered_at=utc_now(),
                abstract_or_body="A paper that would otherwise match the ship autonomy topic.",
                url="https://example.org/explicit-ru",
                doi=None,
                topic_id=topic.topic_id,
                raw_payload={"id": "explicit-ru-item", "language": "ru"},
            ),
            RawItem(
                source=self.source_name,
                source_id="cyrillic-item",
                item_type="paper",
                title="Автономне судно та уникнення зіткнень",
                authors_or_author=["Carol"],
                published_at=date(2026, 3, 20),
                discovered_at=utc_now(),
                abstract_or_body="Autonomous ship collision avoidance for maritime vessel operations.",
                url="https://example.org/cyrillic",
                doi=None,
                topic_id=topic.topic_id,
                raw_payload={"id": "cyrillic-item"},
            ),
            RawItem(
                source=self.source_name,
                source_id="news-ru-item",
                item_type="news_article",
                title="Autonomous ship program expands",
                authors_or_author=["Global Maritime Daily"],
                published_at=date(2026, 3, 20),
                discovered_at=utc_now(),
                abstract_or_body="A Russian-language news article about autonomous ship development.",
                url="https://example.org/news-ru",
                doi=None,
                topic_id=topic.topic_id,
                raw_payload={"id": "news-ru-item", "language": "ru"},
            ),
        ]


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_registry = dict(SOURCE_REGISTRY)
        SOURCE_REGISTRY["fake_primary"] = FakePrimaryAdapter
        SOURCE_REGISTRY["fake_secondary"] = FakeSecondaryAdapter
        SOURCE_REGISTRY["broken_source"] = BrokenAdapter
        SOURCE_REGISTRY["fake_news"] = FakeNewsAdapter
        SOURCE_REGISTRY["fake_language"] = FakeLanguageAdapter

    def tearDown(self) -> None:
        SOURCE_REGISTRY.clear()
        SOURCE_REGISTRY.update(self._original_registry)

    def test_normalize_prefers_doi_then_url_then_title(self) -> None:
        item = normalize_raw_item(
            RawItem(
                source="x",
                source_id="1",
                item_type="paper",
                title="Example Title",
                authors_or_author=[],
                published_at=date(2026, 3, 18),
                discovered_at=utc_now(),
                abstract_or_body=None,
                url="https://example.org/paper",
                doi="10.1000/ABC",
                topic_id="topic",
                raw_payload={"id": 1},
            )
        )
        self.assertEqual(item.identity_key, "doi:10.1000/abc")

    def test_collect_summarize_report_and_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            import_dir = tmp_path / "imports" / "linkedin"
            import_dir.mkdir(parents=True)
            with (import_dir / "posts.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["url", "title", "author", "published_at", "body"])
                writer.writeheader()
                writer.writerow(
                    {
                        "url": "https://www.linkedin.com/posts/example-edge-ai",
                        "title": "Edge AI field notes",
                        "author": "Dana",
                        "published_at": "2026-03-20",
                        "body": "Edge AI deployment lessons from field testing.",
                    }
                )

            config = AppConfig(
                topics=[
                    TopicProfile(
                        topic_id="edge_ai",
                        display_name="Edge AI",
                        keywords=["edge ai"],
                        include_terms=[],
                        exclude_terms=[],
                        sources=["fake_primary", "fake_secondary", "fake_news", "linkedin_import"],
                        min_relevance_score=2.0,
                    )
                ],
                sources={
                    "fake_primary": SourceSettings(name="fake_primary"),
                    "fake_secondary": SourceSettings(name="fake_secondary"),
                    "fake_news": SourceSettings(name="fake_news"),
                    "linkedin_import": SourceSettings(name="linkedin_import", extra={"import_dir": str(import_dir)}),
                },
                config_dir=str(tmp_path / "config"),
            )
            storage = Storage(tmp_path / "state.db")
            try:
                first_run = collect_items(config, storage, "2026-W12", date(2026, 3, 16), date(2026, 3, 22))
                first_items = storage.list_items_for_run(first_run.run_id)
                self.assertEqual(len(first_items), 4)
                summarize_stats = summarize_run(storage, first_run.run_id, summarizer=DeterministicSummarizer())
                self.assertEqual(summarize_stats["created"], 4)
                outputs = write_report(storage, config, first_run.run_id, output_dir=tmp_path / "reports")
                
                paper_md = Path(outputs["paper"]).read_text(encoding="utf-8")
                news_md = Path(outputs["news_article"]).read_text(encoding="utf-8")
                social_md = Path(outputs["social_post"]).read_text(encoding="utf-8")

                self.assertIn("Shared Paper", paper_md)
                self.assertIn("Edge AI Trial Expands", news_md)
                self.assertIn("LinkedIn Posts", social_md)
                
                # Verify structure of one of them
                self.assertIn("**Metadata**", paper_md)
                self.assertIn("**AI Summary**", paper_md)
                self.assertIn("<a id=", paper_md)
                self.assertIn("---", paper_md)

                second_run = collect_items(config, storage, "2026-W12", date(2026, 3, 16), date(2026, 3, 22))
                self.assertEqual(second_run.source_stats["fake_primary"]["existing_items"], 2)
                self.assertEqual(second_run.source_stats["fake_secondary"]["existing_items"], 1)
                self.assertEqual(second_run.source_stats["fake_news"]["existing_items"], 1)
            finally:
                storage.close()

    def test_source_failure_is_non_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = AppConfig(
                topics=[
                    TopicProfile(
                        topic_id="edge_ai",
                        display_name="Edge AI",
                        keywords=["edge ai"],
                        include_terms=[],
                        exclude_terms=[],
                        sources=["fake_primary", "broken_source"],
                        min_relevance_score=2.0,
                    )
                ],
                sources={
                    "fake_primary": SourceSettings(name="fake_primary"),
                    "broken_source": SourceSettings(name="broken_source"),
                },
                config_dir=str(tmp_path / "config"),
            )
            storage = Storage(tmp_path / "state.db")
            try:
                run = collect_items(config, storage, "2026-W12", date(2026, 3, 16), date(2026, 3, 22))
                self.assertEqual(run.status, "partial")
                self.assertEqual(len(storage.list_items_for_run(run.run_id)), 2)
                self.assertTrue(any("broken_source" in error for error in run.errors))
            finally:
                storage.close()

    def test_include_and_exclude_terms_filter_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = AppConfig(
                topics=[
                    TopicProfile(
                        topic_id="edge_ai",
                        display_name="Edge AI",
                        keywords=["edge ai"],
                        include_terms=["deployment"],
                        exclude_terms=["job posting"],
                        sources=["fake_primary"],
                        min_relevance_score=2.0,
                    )
                ],
                sources={"fake_primary": SourceSettings(name="fake_primary")},
                config_dir=str(tmp_path / "config"),
            )
            storage = Storage(tmp_path / "state.db")
            try:
                run = collect_items(config, storage, "2026-W12", date(2026, 3, 16), date(2026, 3, 22))
                items = storage.list_items_for_run(run.run_id)
                self.assertEqual(len(items), 2)
                self.assertEqual({item.title for item in items}, {"Shared Paper", "Edge AI Deployment Study"})
            finally:
                storage.close()

    def test_landing_page_fallback_populates_missing_abstract(self) -> None:
        class StubFetcher:
            def enrich(self, item):
                item.abstract_or_body = "Recovered abstract from landing page."
                return item

        class MissingAbstractAdapter(SourceAdapter):
            source_name = "missing_abstract"

            def search(self, topic: TopicProfile, start_date: date, end_date: date) -> list[RawItem]:
                return [
                    RawItem(
                        source=self.source_name,
                        source_id="paper-c",
                        item_type="paper",
                        title="Autonomous Ships Navigation",
                        authors_or_author=["Eve"],
                        published_at=date(2026, 3, 20),
                        discovered_at=utc_now(),
                        abstract_or_body=None,
                        url="https://example.org/paper-c",
                        doi=None,
                        topic_id=topic.topic_id,
                        raw_payload={"source": self.source_name, "id": "paper-c"},
                    )
                ]

        original_fetcher = pipeline_module.LandingPageAbstractFetcher
        pipeline_module.LandingPageAbstractFetcher = lambda settings: StubFetcher()
        SOURCE_REGISTRY["missing_abstract"] = MissingAbstractAdapter
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                config = AppConfig(
                    topics=[
                        TopicProfile(
                            topic_id="maritime_ai",
                            display_name="Maritime AI",
                            keywords=["autonomous ships"],
                            include_terms=[],
                            exclude_terms=[],
                            sources=["missing_abstract"],
                            min_relevance_score=2.0,
                        )
                    ],
                    sources={"missing_abstract": SourceSettings(name="missing_abstract")},
                    config_dir=str(tmp_path / "config"),
                )
                storage = Storage(tmp_path / "state.db")
                try:
                    run = collect_items(config, storage, "2026-W12", date(2026, 3, 16), date(2026, 3, 22))
                    items = storage.list_items_for_run(run.run_id)
                    self.assertEqual(items[0].abstract_or_body, "Recovered abstract from landing page.")
                finally:
                    storage.close()
        finally:
            SOURCE_REGISTRY.pop("missing_abstract", None)
            pipeline_module.LandingPageAbstractFetcher = original_fetcher

    def test_allowed_paper_languages_filters_only_non_english_papers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = AppConfig(
                topics=[
                    TopicProfile(
                        topic_id="ship_autonomy",
                        display_name="Ship Autonomy",
                        keywords=["autonomous ship"],
                        include_terms=[],
                        exclude_terms=[],
                        allowed_paper_languages=["en"],
                        sources=["fake_language"],
                        min_relevance_score=2.0,
                    )
                ],
                sources={"fake_language": SourceSettings(name="fake_language")},
                config_dir=str(tmp_path / "config"),
            )
            storage = Storage(tmp_path / "state.db")
            try:
                run = collect_items(config, storage, "2026-W12", date(2026, 3, 16), date(2026, 3, 22))
                items = storage.list_items_for_run(run.run_id)
                self.assertEqual(len(items), 2)
                self.assertEqual(
                    {item.title for item in items},
                    {
                        "Autonomous ship collision avoidance study",
                        "Autonomous ship program expands",
                    },
                )
                self.assertEqual(run.source_stats["fake_language"]["filtered_out"], 2)
            finally:
                storage.close()
