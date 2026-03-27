from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date

from ..models import RawItem, TopicProfile
from ..utils import parse_date, utc_now
from .base import SourceAdapter


class ArxivAdapter(SourceAdapter):
    source_name = "arxiv"
    default_base_url = "https://export.arxiv.org/api/query"

    def search(self, topic: TopicProfile, start_date: date, end_date: date) -> list[RawItem]:
        results: dict[str, RawItem] = {}
        for keyword in topic.keywords:
            payload = self._get_text(
                self.settings.base_url or self.default_base_url,
                params={
                    "search_query": f'all:"{keyword}"',
                    "start": 0,
                    "max_results": self.settings.max_results,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                },
            )
            for item in self.parse_response(payload, topic.topic_id):
                if item.published_at and not (start_date <= item.published_at <= end_date):
                    continue
                results[item.source_id] = item
        return list(results.values())

    @classmethod
    def parse_response(cls, payload: str, topic_id: str) -> list[RawItem]:
        namespace = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(payload)
        items: list[RawItem] = []
        for entry in root.findall("atom:entry", namespace):
            identifier = entry.findtext("atom:id", default="", namespaces=namespace).strip()
            title = " ".join(entry.findtext("atom:title", default="", namespaces=namespace).split())
            summary = " ".join(entry.findtext("atom:summary", default="", namespaces=namespace).split())
            authors = [
                author.findtext("atom:name", default="", namespaces=namespace).strip()
                for author in entry.findall("atom:author", namespace)
            ]
            published = entry.findtext("atom:published", default="", namespaces=namespace)[:10] or None
            doi = None
            for link in entry.findall("atom:link", namespace):
                if link.attrib.get("title") == "doi":
                    doi = link.attrib.get("href")
                    break
            source_id = identifier.rsplit("/", maxsplit=1)[-1] if identifier else title
            items.append(
                RawItem(
                    source="arxiv",
                    source_id=source_id,
                    item_type="paper",
                    title=title,
                    authors_or_author=[author for author in authors if author],
                    published_at=parse_date(published),
                    discovered_at=utc_now(),
                    abstract_or_body=summary or None,
                    url=identifier,
                    doi=doi,
                    topic_id=topic_id,
                    raw_payload={"id": identifier, "title": title, "summary": summary},
                )
            )
        return items
