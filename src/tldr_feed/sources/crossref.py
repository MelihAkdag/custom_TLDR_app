from __future__ import annotations

from datetime import date

from ..models import RawItem, TopicProfile
from ..utils import normalize_doi, strip_html, utc_now
from .base import SourceAdapter


class CrossrefAdapter(SourceAdapter):
    source_name = "crossref"
    default_base_url = "https://api.crossref.org/works"

    def search(self, topic: TopicProfile, start_date: date, end_date: date) -> list[RawItem]:
        results: dict[str, RawItem] = {}
        for keyword in topic.keywords:
            payload = self._get_json(
                self.settings.base_url or self.default_base_url,
                params={
                    "query.bibliographic": keyword,
                    "filter": f"from-pub-date:{start_date.isoformat()},until-pub-date:{end_date.isoformat()}",
                    "rows": self.settings.max_results,
                },
            )
            for item in self.parse_response(payload, topic.topic_id):
                results[item.source_id] = item
        return list(results.values())

    @classmethod
    def parse_response(cls, payload: dict, topic_id: str) -> list[RawItem]:
        items: list[RawItem] = []
        for result in payload.get("message", {}).get("items", []):
            titles = result.get("title") or []
            title = str(titles[0]).strip() if titles else ""
            authors = []
            for author in result.get("author", []):
                full_name = " ".join(
                    part
                    for part in [author.get("given", "").strip(), author.get("family", "").strip()]
                    if part
                )
                if full_name:
                    authors.append(full_name)
            doi = normalize_doi(result.get("DOI"))
            published_at = cls._extract_date(result)
            items.append(
                RawItem(
                    source="crossref",
                    source_id=doi or str(result.get("URL") or title),
                    item_type="paper",
                    title=title,
                    authors_or_author=authors,
                    published_at=published_at,
                    discovered_at=utc_now(),
                    abstract_or_body=strip_html(result.get("abstract")),
                    url=str(result.get("URL") or ""),
                    doi=doi,
                    topic_id=topic_id,
                    raw_payload=result,
                )
            )
        return items

    @staticmethod
    def _extract_date(result: dict) -> date | None:
        for key in ("published-print", "published-online", "issued", "created"):
            date_parts = result.get(key, {}).get("date-parts", [])
            if not date_parts or not date_parts[0]:
                continue
            values = date_parts[0]
            year = int(values[0])
            month = int(values[1]) if len(values) > 1 else 1
            day = int(values[2]) if len(values) > 2 else 1
            return date(year, month, day)
        return None
