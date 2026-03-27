from __future__ import annotations

import json
import re
from html import unescape
from urllib.request import Request, urlopen

from .models import NormalizedItem, SourceSettings


class LandingPageAbstractFetcher:
    def __init__(self, settings: SourceSettings | None = None) -> None:
        self.settings = settings or SourceSettings(name="landing_page", timeout_seconds=20)

    def enrich(self, item: NormalizedItem) -> NormalizedItem:
        if item.item_type != "paper" or item.abstract_or_body or not item.url:
            return item
        if item.url.casefold().endswith(".pdf"):
            return item
        abstract = self._fetch_abstract(item.url)
        if not abstract:
            return item
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
            url=item.url,
            doi=item.doi,
            topic_ids=item.topic_ids,
            raw_hash=item.raw_hash,
            raw_payload=item.raw_payload,
            identity_key=item.identity_key,
        )

    def _fetch_abstract(self, url: str) -> str | None:
        request = Request(url, headers={"User-Agent": self.settings.user_agent})
        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                content_type = response.headers.get_content_type()
                if content_type and "html" not in content_type:
                    return None
                charset = response.headers.get_content_charset() or "utf-8"
                html_text = response.read(1_500_000).decode(charset, errors="replace")
        except Exception:
            return None
        return extract_abstract_from_html(html_text)


def extract_abstract_from_html(html_text: str) -> str | None:
    candidates = _extract_meta_candidates(html_text)
    for key in (
        "citation_abstract",
        "dc.description.abstract",
        "dc.description",
        "description",
        "og:description",
        "twitter:description",
    ):
        value = candidates.get(key)
        if _is_valid_abstract(value):
            return _clean_text(value)

    section_value = _extract_abstract_section(html_text)
    if _is_valid_abstract(section_value):
        return _clean_text(section_value)

    json_ld_value = _extract_json_ld_description(html_text)
    if _is_valid_abstract(json_ld_value):
        return _clean_text(json_ld_value)
    return None


def _extract_meta_candidates(html_text: str) -> dict[str, str]:
    pattern = re.compile(r"<meta\b(?P<attrs>[^>]*?)>", flags=re.IGNORECASE | re.DOTALL)
    candidates: dict[str, str] = {}
    for match in pattern.finditer(html_text):
        attrs = _parse_tag_attrs(match.group("attrs"))
        key = (attrs.get("name") or attrs.get("property") or attrs.get("itemprop") or "").casefold()
        content = attrs.get("content")
        if key and content:
            candidates.setdefault(key, content)
    return candidates


def _extract_json_ld_description(html_text: str) -> str | None:
    pattern = re.compile(
        r"<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>(?P<body>.*?)</script>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(html_text):
        payload = match.group("body").strip()
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        description = _find_description(parsed)
        if description:
            return description
    return None


def _find_description(payload: object) -> str | None:
    if isinstance(payload, dict):
        if isinstance(payload.get("description"), str):
            return payload["description"]
        for value in payload.values():
            found = _find_description(value)
            if found:
                return found
    if isinstance(payload, list):
        for entry in payload:
            found = _find_description(entry)
            if found:
                return found
    return None


def _extract_abstract_section(html_text: str) -> str | None:
    patterns = [
        r"<(?:section|div)[^>]*(?:id|class|data-test|data-testid)=[\"'][^\"']*abstract[^\"']*[\"'][^>]*>(?P<body>.*?)</(?:section|div)>",
        r"<p[^>]*(?:id|class)=[\"'][^\"']*abstract[^\"']*[\"'][^>]*>(?P<body>.*?)</p>",
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group("body")
    return None


def _parse_tag_attrs(value: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for key, _, attr_value in re.findall(
        r"([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*([\"'])(.*?)\2",
        value,
        flags=re.DOTALL,
    ):
        attrs[key.casefold()] = attr_value
    return attrs


def _is_valid_abstract(value: str | None) -> bool:
    if not value:
        return False
    cleaned = _clean_text(value)
    if len(cleaned) < 40:
        return False
    blocked_fragments = ("cookie", "javascript", "sign in", "rights reserved")
    return not any(fragment in cleaned.casefold() for fragment in blocked_fragments)


def _clean_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()
