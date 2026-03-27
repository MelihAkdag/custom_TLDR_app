from __future__ import annotations

from datetime import date

from ..models import RawItem, TopicProfile
from ..utils import normalize_doi, utc_now
from .base import SourceAdapter


class OpenAlexAdapter(SourceAdapter):
    source_name = "openalex"
    default_base_url = "https://api.openalex.org/works"

    def search(self, topic: TopicProfile, start_date: date, end_date: date) -> list[RawItem]:
        results: dict[str, RawItem] = {}
        for keyword in topic.keywords:
            payload = self._get_json(
                self.settings.base_url or self.default_base_url,
                params={
                    "search": keyword,
                    "filter": f"from_publication_date:{start_date.isoformat()},to_publication_date:{end_date.isoformat()}",
                    "per-page": self.settings.max_results,
                },
            )
            for item in self.parse_response(payload, topic.topic_id):
                results[item.source_id] = item
        return list(results.values())

    @classmethod
    def parse_response(cls, payload: dict, topic_id: str) -> list[RawItem]:
        items: list[RawItem] = []
        for result in payload.get("results", []):
            title = str(result.get("title") or "").strip()
            identifier = str(result.get("id") or title)
            authors = [
                authorship.get("author", {}).get("display_name", "").strip()
                for authorship in result.get("authorships", [])
                if authorship.get("author", {}).get("display_name")
            ]
            abstract = cls._reconstruct_abstract(result.get("abstract_inverted_index"))
            doi = normalize_doi(result.get("doi"))
            primary_location = result.get("primary_location") or {}
            url = primary_location.get("landing_page_url") or result.get("doi") or identifier
            items.append(
                RawItem(
                    source="openalex",
                    source_id=identifier,
                    item_type="paper",
                    title=title,
                    authors_or_author=authors,
                    published_at=date.fromisoformat(result["publication_date"])
                    if result.get("publication_date")
                    else None,
                    discovered_at=utc_now(),
                    abstract_or_body=abstract,
                    url=url,
                    doi=doi,
                    topic_id=topic_id,
                    raw_payload=result,
                )
            )
        return items

    @staticmethod
    def _reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
        if not inverted_index:
            return None
        positions: dict[int, str] = {}
        for word, indices in inverted_index.items():
            for index in indices:
                positions[index] = word
        return " ".join(positions[index] for index in sorted(positions))
