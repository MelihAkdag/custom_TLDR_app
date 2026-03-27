from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Iterable, TypeVar
from urllib.parse import urlparse


T = TypeVar("T")


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def to_iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def to_iso_date(value: date | None) -> str | None:
    return value.isoformat() if value else None


def previous_completed_week(reference: date | None = None) -> tuple[str, date, date]:
    reference = reference or date.today()
    current_weekday = reference.isoweekday()
    end = reference - timedelta(days=current_weekday)
    start = end - timedelta(days=6)
    iso_year, iso_week, _ = end.isocalendar()
    return f"{iso_year}-W{iso_week:02d}", start, end


def week_to_range(week_value: str) -> tuple[str, date, date]:
    cleaned = week_value.strip().upper()
    year_part, week_part = cleaned.split("-W", maxsplit=1)
    year = int(year_part)
    week = int(week_part)
    start = date.fromisocalendar(year, week, 1)
    end = date.fromisocalendar(year, week, 7)
    return f"{year}-W{week:02d}", start, end


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def stable_json_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    cleaned = doi.strip().lower()
    cleaned = re.sub(r"^https?://(dx\.)?doi\.org/", "", cleaned)
    return cleaned or None


def canonicalize_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return url.strip()
    normalized = parsed._replace(query="", fragment="")
    return normalized.geturl().rstrip("/")


def canonicalize_title(title: str) -> str:
    lowered = title.casefold()
    lowered = re.sub(r"\s+", " ", lowered)
    lowered = re.sub(r"[^\w\s]", "", lowered)
    return lowered.strip()


def build_identity_key(title: str, doi: str | None, url: str | None) -> str:
    normalized_doi = normalize_doi(doi)
    if normalized_doi:
        return f"doi:{normalized_doi}"
    normalized_url = canonicalize_url(url)
    if normalized_url:
        return f"url:{normalized_url}"
    return f"title:{canonicalize_title(title)}"


def make_item_id(identity_key: str) -> str:
    return hashlib.sha256(identity_key.encode("utf-8")).hexdigest()


def unique_preserve_order(values: Iterable[T]) -> list[T]:
    seen: set[T] = set()
    unique: list[T] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def truncate_text(value: str | None, limit: int = 1400) -> str | None:
    if not value:
        return None
    compact = re.sub(r"\s+", " ", value).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def strip_html(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"<[^>]+>", " ", value).replace("\n", " ").strip()
