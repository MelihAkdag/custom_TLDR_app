from __future__ import annotations

import json
import os
from urllib.parse import quote
from urllib.request import Request, urlopen

from ..models import NormalizedItem, SourceSettings
from ..utils import normalize_doi


class SemanticScholarEnricher:
    def __init__(self, settings: SourceSettings | None = None) -> None:
        self.settings = settings or SourceSettings(name="semantic_scholar")
        self.api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY") or str(self.settings.extra.get("api_key", "")).strip()
        self.base_url = self.settings.base_url or "https://api.semanticscholar.org/graph/v1"

    def enrich(self, item: NormalizedItem) -> NormalizedItem:
        if item.item_type != "paper":
            return item
        if item.abstract_or_body and item.doi:
            return item
        payload = self._lookup_payload(item)
        if not payload:
            return item
        abstract = payload.get("abstract") or item.abstract_or_body
        url = payload.get("url") or item.url
        doi = normalize_doi((payload.get("externalIds") or {}).get("DOI")) or item.doi
        return NormalizedItem(
            item_id=item.item_id,
            source=item.source,
            source_id=item.source_id,
            item_type=item.item_type,
            title=item.title,
            authors_or_author=item.authors_or_author,
            published_at=item.published_at,
            discovered_at=item.discovered_at,
            abstract_or_body=abstract,
            url=url,
            doi=doi,
            topic_ids=item.topic_ids,
            raw_hash=item.raw_hash,
            raw_payload=item.raw_payload,
            identity_key=item.identity_key,
        )

    def _lookup_payload(self, item: NormalizedItem) -> dict | None:
        headers = {"User-Agent": self.settings.user_agent}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        if item.doi:
            target = f"{self.base_url}/paper/DOI:{quote(item.doi, safe='')}"
            params = "?fields=title,abstract,url,externalIds"
        else:
            target = f"{self.base_url}/paper/search/match"
            params = f"?query={quote(item.title)}&fields=title,abstract,url,externalIds"
        request = Request(target + params, headers=headers)
        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return None
        if "data" in payload and isinstance(payload["data"], list):
            return payload["data"][0] if payload["data"] else None
        return payload
