from __future__ import annotations

import email.utils
import xml.etree.ElementTree as ET
from datetime import date
from urllib.parse import urlparse

from ..models import RawItem, TopicProfile
from ..utils import truncate_text, utc_now
from .base import SourceAdapter


class NewsRssAdapter(SourceAdapter):
    source_name = "news_rss"
    item_type = "news_article"
    default_base_url = "https://news.google.com/rss/search"

    def search(self, topic: TopicProfile, start_date: date, end_date: date) -> list[RawItem]:
        items: dict[str, RawItem] = {}

        if bool(self.settings.extra.get("use_search_feed", True)):
            for keyword in topic.keywords:
                try:
                    payload = self._get_text(
                        self.settings.base_url or self.default_base_url,
                        params={
                            "q": self._build_query(keyword),
                            "hl": self.settings.extra.get("hl", "en-US"),
                            "gl": self.settings.extra.get("gl", "US"),
                            "ceid": self.settings.extra.get("ceid", "US:en"),
                        },
                    )
                    for item in self.parse_response(payload, topic.topic_id):
                        self._add_if_relevant(items, item, start_date, end_date)
                except Exception:
                    # Log or skip, but don't crash the entire source search
                    pass

        for feed_config in self._custom_feed_configs():
            try:
                payload = self._get_text(feed_config["url"], params={})
                for item in self.parse_response(
                    payload,
                    topic.topic_id,
                    fallback_source=feed_config.get("source_name"),
                ):
                    self._add_if_relevant(items, item, start_date, end_date)
            except Exception:
                # Log or skip, but don't crash the entire source search
                pass

        return list(items.values())

    def _custom_feed_configs(self) -> list[dict[str, str]]:
        raw_feeds = self.settings.extra.get("custom_rss_feeds", [])
        configs: list[dict[str, str]] = []
        if not isinstance(raw_feeds, list):
            return configs
        for entry in raw_feeds:
            if isinstance(entry, str) and entry.strip():
                configs.append({"url": entry.strip(), "source_name": ""})
                continue
            if not isinstance(entry, dict):
                continue
            url = str(entry.get("url") or "").strip()
            if not url:
                continue
            configs.append(
                {
                    "url": url,
                    "source_name": str(entry.get("source_name") or "").strip(),
                }
            )
        return configs

    def _add_if_relevant(
        self,
        items: dict[str, RawItem],
        item: RawItem,
        start_date: date,
        end_date: date,
    ) -> None:
        if item.published_at and not (start_date <= item.published_at <= end_date):
            return
        if not self._passes_domain_filters(item.url):
            return
        items[item.source_id] = item

    def _passes_domain_filters(self, url: str) -> bool:
        domain = self._extract_domain(url)
        blocked_domains = self._normalized_domain_list("blocked_domains")
        allowed_domains = self._normalized_domain_list("allowed_domains")

        if blocked_domains and self._domain_matches(domain, blocked_domains):
            return False
        if allowed_domains and not self._domain_matches(domain, allowed_domains):
            return False
        return True

    def _normalized_domain_list(self, key: str) -> list[str]:
        raw_values = self.settings.extra.get(key, [])
        if not isinstance(raw_values, list):
            return []
        return [self._normalize_domain(str(value)) for value in raw_values if str(value).strip()]

    def _build_query(self, keyword: str) -> str:
        days = int(self.settings.extra.get("window_days", 7))
        return f'"{keyword}" when:{days}d'

    @classmethod
    def parse_response(cls, payload: str, topic_id: str, fallback_source: str | None = None) -> list[RawItem]:
        root = ET.fromstring(payload)
        items: list[RawItem] = []
        channel = root.find("channel")
        if channel is None:
            return items
        channel_title = channel.findtext("title", default="").strip()
        for entry in channel.findall("item"):
            title = cls._clean_title(entry.findtext("title", default=""))
            link = entry.findtext("link", default="").strip()
            description = entry.findtext("description", default="").strip()
            source = entry.findtext("source", default="").strip() or fallback_source or channel_title
            pub_date = entry.findtext("pubDate", default="").strip()
            published = email.utils.parsedate_to_datetime(pub_date).date() if pub_date else None
            source_id = link or title
            items.append(
                RawItem(
                    source="news_rss",
                    source_id=source_id,
                    item_type="news_article",
                    title=title,
                    authors_or_author=[source] if source else [],
                    published_at=published,
                    discovered_at=utc_now(),
                    abstract_or_body=truncate_text(cls._strip_html(description), limit=1200),
                    url=link,
                    doi=None,
                    topic_id=topic_id,
                    raw_payload={
                        "title": title,
                        "link": link,
                        "description": description,
                        "source": source,
                        "pubDate": pub_date,
                    },
                )
            )
        return items

    @staticmethod
    def _extract_domain(url: str) -> str:
        parsed = urlparse(url.strip())
        return NewsRssAdapter._normalize_domain(parsed.netloc)

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        cleaned = domain.strip().casefold()
        if cleaned.startswith("www."):
            cleaned = cleaned[4:]
        return cleaned

    @staticmethod
    def _domain_matches(domain: str, patterns: list[str]) -> bool:
        if not domain:
            return False
        return any(domain == pattern or domain.endswith(f".{pattern}") for pattern in patterns)

    @staticmethod
    def _clean_title(title: str) -> str:
        cleaned = title.strip()
        if " - " not in cleaned:
            return cleaned
        headline, _, source = cleaned.rpartition(" - ")
        if source and len(source) <= 60:
            return headline
        return cleaned

    @staticmethod
    def _strip_html(value: str) -> str:
        import re

        return re.sub(r"<[^>]+>", " ", value).replace("\n", " ").strip()
