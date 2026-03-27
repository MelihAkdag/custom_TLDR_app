from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tldr_feed.models import SourceSettings, TopicProfile
from tldr_feed.sources.linkedin_posts import LinkedInPostsAdapter
from tldr_feed.sources.news_rss import NewsRssAdapter


class FeedSourceTests(unittest.TestCase):
    def test_news_rss_parser_builds_news_items(self) -> None:
        payload = """
        <rss version="2.0">
          <channel>
            <item>
              <title>Autonomous ship pilot expands - Maritime News</title>
              <link>https://news.example.org/autonomous-ship-pilot</link>
              <description><![CDATA[<p>A weekly update on autonomous ship trials.</p>]]></description>
              <source url="https://news.example.org">Maritime News</source>
              <pubDate>Fri, 20 Mar 2026 10:00:00 GMT</pubDate>
            </item>
          </channel>
        </rss>
        """
        items = NewsRssAdapter.parse_response(payload, "ship_autonomy")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].item_type, "news_article")
        self.assertEqual(items[0].title, "Autonomous ship pilot expands")
        self.assertEqual(items[0].authors_or_author, ["Maritime News"])

    def test_news_rss_parser_uses_channel_title_for_custom_feed(self) -> None:
        payload = """
        <rss version="2.0">
          <channel>
            <title>gCaptain</title>
            <item>
              <title>Autonomous ship pilot expands</title>
              <link>https://gcaptain.com/autonomous-ship-pilot</link>
              <description><![CDATA[<p>A weekly update on autonomous ship trials.</p>]]></description>
              <pubDate>Fri, 20 Mar 2026 10:00:00 GMT</pubDate>
            </item>
          </channel>
        </rss>
        """
        items = NewsRssAdapter.parse_response(payload, "ship_autonomy")
        self.assertEqual(items[0].authors_or_author, ["gCaptain"])

    def test_news_rss_domain_filters_support_allowed_and_blocked_lists(self) -> None:
        adapter = NewsRssAdapter(
            SourceSettings(
                name="news_rss",
                extra={
                    "allowed_domains": ["gcaptain.com", "safety4sea.com"],
                    "blocked_domains": ["bad.example.com"],
                },
            )
        )
        self.assertTrue(adapter._passes_domain_filters("https://gcaptain.com/story"))
        self.assertTrue(adapter._passes_domain_filters("https://www.safety4sea.com/news/item"))
        self.assertFalse(adapter._passes_domain_filters("https://bad.example.com/post"))
        self.assertFalse(adapter._passes_domain_filters("https://other.example.org/post"))

    def test_news_rss_custom_feeds_are_loaded(self) -> None:
        class StubNewsAdapter(NewsRssAdapter):
            def __init__(self, settings: SourceSettings) -> None:
                super().__init__(settings)
                self.requested_urls: list[str] = []

            def _get_text(self, url: str, params: dict[str, object]) -> str:
                self.requested_urls.append(url)
                return """
                <rss version="2.0">
                  <channel>
                    <title>gCaptain</title>
                    <item>
                      <title>Autonomous ship pilot expands</title>
                      <link>https://gcaptain.com/autonomous-ship-pilot</link>
                      <description><![CDATA[<p>A weekly update on autonomous ship trials.</p>]]></description>
                      <pubDate>Fri, 20 Mar 2026 10:00:00 GMT</pubDate>
                    </item>
                  </channel>
                </rss>
                """

        adapter = StubNewsAdapter(
            SourceSettings(
                name="news_rss",
                extra={
                    "use_search_feed": False,
                    "custom_rss_feeds": [{"url": "https://gcaptain.com/feed/", "source_name": "gCaptain"}],
                    "allowed_domains": ["gcaptain.com"],
                },
            )
        )
        topic = TopicProfile(
            topic_id="ship_autonomy",
            display_name="Ship Autonomy",
            keywords=["autonomous ship"],
            include_terms=[],
            exclude_terms=[],
            sources=["news_rss"],
            min_relevance_score=2.0,
        )
        items = adapter.search(topic, date(2026, 3, 16), date(2026, 3, 22))
        self.assertEqual(adapter.requested_urls, ["https://gcaptain.com/feed/"])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].authors_or_author, ["gCaptain"])

    def test_linkedin_posts_parser_builds_social_posts(self) -> None:
        payload = {
            "elements": [
                {
                    "id": "123",
                    "author": "urn:li:organization:999",
                    "commentary": {"text": "Autonomous vessel trial with new collision avoidance data."},
                    "publishedAt": 1774000800000,
                    "urn": "urn:li:share:123",
                }
            ]
        }
        items = LinkedInPostsAdapter.parse_response(payload, "ship_autonomy", "urn:li:organization:999")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].item_type, "social_post")
        self.assertIn("Autonomous vessel trial", items[0].title)
        self.assertEqual(items[0].authors_or_author, ["urn:li:organization:999"])
        self.assertEqual(items[0].url, "https://www.linkedin.com/feed/update/urn:li:share:123/")
