from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Any

from ..models import RawItem, TopicProfile
from ..utils import parse_date, stable_json_hash, truncate_text, utc_now
from .base import SourceAdapter


class LinkedInImportAdapter(SourceAdapter):
    source_name = "linkedin_import"

    def search(self, topic: TopicProfile, start_date: date, end_date: date) -> list[RawItem]:
        import_dir = Path(self.settings.extra.get("import_dir", "imports/linkedin"))
        if not import_dir.exists():
            return []
        items: list[RawItem] = []
        for path in sorted(import_dir.iterdir()):
            if not path.is_file():
                continue
            items.extend(self._load_path(path, topic, start_date, end_date))
        return items

    def _load_path(self, path: Path, topic: TopicProfile, start_date: date, end_date: date) -> list[RawItem]:
        suffix = path.suffix.casefold()
        if suffix == ".csv":
            return self._from_csv(path, topic, start_date, end_date)
        if suffix == ".json":
            return self._from_json(path, topic, start_date, end_date)
        if suffix in {".txt", ".urls"}:
            return self._from_url_list(path, topic, start_date, end_date)
        return []

    def _from_csv(self, path: Path, topic: TopicProfile, start_date: date, end_date: date) -> list[RawItem]:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return [
                item
                for row in reader
                if (item := self._build_item(row, topic, start_date, end_date, path)) is not None
            ]

    def _from_json(self, path: Path, topic: TopicProfile, start_date: date, end_date: date) -> list[RawItem]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            entries = payload.get("posts", [])
        else:
            entries = payload
        return [
            item
            for entry in entries
            if isinstance(entry, dict)
            and (item := self._build_item(entry, topic, start_date, end_date, path)) is not None
        ]

    def _from_url_list(self, path: Path, topic: TopicProfile, start_date: date, end_date: date) -> list[RawItem]:
        records: list[RawItem] = []
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            item = self._build_item(
                {"url": line, "title": "LinkedIn post", "body": None},
                topic,
                start_date,
                end_date,
                path,
            )
            if item is not None:
                records.append(item)
        return records

    def _build_item(
        self,
        row: dict[str, Any],
        topic: TopicProfile,
        start_date: date,
        end_date: date,
        source_path: Path,
    ) -> RawItem | None:
        title = str(row.get("title") or row.get("headline") or "LinkedIn post").strip()
        body = str(row.get("body") or row.get("text") or row.get("content") or "").strip() or None
        author = str(row.get("author") or row.get("creator") or "").strip()
        url = str(row.get("url") or row.get("link") or "").strip()
        if not url:
            return None
        published_at = parse_date(str(row.get("published_at") or row.get("date") or "").strip() or None)
        if published_at is None:
            published_at = date.fromtimestamp(source_path.stat().st_mtime)
        if not (start_date <= published_at <= end_date):
            return None
        explicit_topics = [str(value).strip() for value in row.get("topic_ids", [])] if isinstance(row.get("topic_ids"), list) else []
        haystack = " ".join(part for part in [title, body or "", url] if part).casefold()
        keyword_match = any(keyword.casefold() in haystack for keyword in topic.keywords)
        if explicit_topics and topic.topic_id not in explicit_topics:
            return None
        if not explicit_topics and not keyword_match:
            return None
        return RawItem(
            source="linkedin_import",
            source_id=str(row.get("id") or stable_json_hash({"path": str(source_path), "url": url})),
            item_type="social_post",
            title=title,
            authors_or_author=[author] if author else [],
            published_at=published_at,
            discovered_at=utc_now(),
            abstract_or_body=truncate_text(body, limit=1200),
            url=url,
            doi=None,
            topic_id=topic.topic_id,
            raw_payload={"source_path": str(source_path), **row},
        )
