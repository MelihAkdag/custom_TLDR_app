from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..models import RawItem, TopicProfile
from ..utils import stable_json_hash, truncate_text, utc_now
from .base import SourceAdapter


class LinkedInPostsAdapter(SourceAdapter):
    source_name = "linkedin_posts"
    default_base_url = "https://api.linkedin.com/rest/posts"

    def search(self, topic: TopicProfile, start_date: date, end_date: date) -> list[RawItem]:
        access_token = os.getenv(str(self.settings.extra.get("access_token_env", "LINKEDIN_ACCESS_TOKEN")).strip())
        if not access_token:
            raise RuntimeError("LinkedIn access token is missing. Set LINKEDIN_ACCESS_TOKEN or configure access_token_env.")

        author_urns = self._author_urns()
        if not author_urns:
            raise RuntimeError("No LinkedIn author URNs configured. Add organization_urns or person_urns in sources.yaml.")

        items: dict[str, RawItem] = {}
        for author_urn in author_urns:
            payload = self._fetch_author_posts(access_token, author_urn)
            for item in self.parse_response(payload, topic.topic_id, author_urn):
                if item.published_at and not (start_date <= item.published_at <= end_date):
                    continue
                items[item.source_id] = item
        return list(items.values())

    def _author_urns(self) -> list[str]:
        values: list[str] = []
        for key in ("organization_urns", "person_urns", "author_urns"):
            raw = self.settings.extra.get(key, [])
            if isinstance(raw, list):
                values.extend(str(value).strip() for value in raw if str(value).strip())
        return values

    def _fetch_author_posts(self, access_token: str, author_urn: str) -> dict:
        query = urlencode(
            {
                "q": "author",
                "author": author_urn,
                "count": self.settings.max_results,
                "sortBy": "LAST_MODIFIED",
            }
        )
        request = Request(
            f"{self.settings.base_url or self.default_base_url}?{query}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "LinkedIn-Version": str(self.settings.extra.get("linkedin_version", "202601")),
                "X-Restli-Protocol-Version": "2.0.0",
                "User-Agent": self.settings.user_agent,
            },
        )
        with urlopen(request, timeout=self.settings.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    @classmethod
    def parse_response(cls, payload: dict, topic_id: str, author_urn: str) -> list[RawItem]:
        items: list[RawItem] = []
        for element in payload.get("elements", []):
            source_id = str(element.get("id") or element.get("urn") or stable_json_hash(element))
            commentary = cls._extract_commentary(element)
            title = cls._extract_title(element, commentary)
            published_at = cls._extract_date(element)
            author = str(element.get("author") or author_urn)
            items.append(
                RawItem(
                    source="linkedin_posts",
                    source_id=source_id,
                    item_type="social_post",
                    title=title,
                    authors_or_author=[author] if author else [],
                    published_at=published_at,
                    discovered_at=utc_now(),
                    abstract_or_body=truncate_text(commentary, limit=1200),
                    url=cls._build_post_url(element, source_id),
                    doi=None,
                    topic_id=topic_id,
                    raw_payload=element,
                )
            )
        return items

    @staticmethod
    def _extract_commentary(element: dict) -> str | None:
        commentary = element.get("commentary") or element.get("content") or {}
        if isinstance(commentary, str):
            return commentary.strip() or None
        if not isinstance(commentary, dict):
            return None
        candidates = [
            commentary.get("text"),
            commentary.get("description"),
            commentary.get("title"),
            ((commentary.get("article") or {}) if isinstance(commentary.get("article"), dict) else {}).get("description"),
            ((commentary.get("media") or {}) if isinstance(commentary.get("media"), dict) else {}).get("title"),
        ]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return None

    @staticmethod
    def _extract_title(element: dict, commentary: str | None) -> str:
        content = element.get("content") or {}
        if isinstance(content, dict):
            for candidate in (
                content.get("title"),
                ((content.get("article") or {}) if isinstance(content.get("article"), dict) else {}).get("title"),
            ):
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
        if commentary:
            clipped = commentary.strip().splitlines()[0]
            return truncate_text(clipped, limit=120) or "LinkedIn post"
        return "LinkedIn post"

    @staticmethod
    def _extract_date(element: dict) -> date | None:
        for key in ("publishedAt", "createdAt", "lastModifiedAt"):
            value = element.get(key)
            parsed = LinkedInPostsAdapter._parse_datetime(value)
            if parsed is not None:
                return parsed.date()
        return None

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            # LinkedIn timestamps are typically milliseconds since epoch.
            scale = 1000 if value > 10_000_000_000 else 1
            return datetime.fromtimestamp(float(value) / scale, tz=UTC)
        if isinstance(value, str) and value:
            cleaned = value.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(cleaned)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        return None

    @staticmethod
    def _build_post_url(element: dict, source_id: str) -> str:
        if isinstance(element.get("permalink"), str) and element["permalink"].strip():
            return element["permalink"].strip()
        urn = str(element.get("urn") or source_id)
        if urn.startswith("urn:li:"):
            return f"https://www.linkedin.com/feed/update/{urn}/"
        return f"https://www.linkedin.com/feed/update/{source_id}/"
