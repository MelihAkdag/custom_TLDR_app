from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(slots=True)
class TopicProfile:
    topic_id: str
    display_name: str
    keywords: list[str]
    include_terms: list[str] = field(default_factory=list)
    exclude_terms: list[str] = field(default_factory=list)
    allowed_paper_languages: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    min_relevance_score: float = 2.0


@dataclass(slots=True)
class SourceSettings:
    name: str
    enabled: bool = True
    base_url: str | None = None
    timeout_seconds: int = 20
    max_results: int = 20
    user_agent: str = "tldr-feed/0.1"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EmailSettings:
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    email_from: str
    email_to: list[str]


@dataclass(slots=True)
class AppConfig:
    topics: list[TopicProfile]
    sources: dict[str, SourceSettings]
    config_dir: str
    email: EmailSettings | None = None


@dataclass(slots=True)
class RawItem:
    source: str
    source_id: str
    item_type: str
    title: str
    authors_or_author: list[str]
    published_at: date | None
    discovered_at: datetime
    abstract_or_body: str | None
    url: str
    doi: str | None
    topic_id: str
    raw_payload: dict[str, Any]


@dataclass(slots=True)
class NormalizedItem:
    source: str
    source_id: str
    item_type: str
    title: str
    authors_or_author: list[str]
    published_at: date | None
    discovered_at: datetime
    abstract_or_body: str | None
    url: str
    doi: str | None
    topic_ids: list[str]
    raw_hash: str
    raw_payload: dict[str, Any]
    identity_key: str
    relevance_score: float = 0.0
    item_id: str | None = None


@dataclass(slots=True)
class SummaryRecord:
    item_id: str
    provider: str
    metadata_markdown: str
    source_excerpt: str | None
    short_summary: str
    generated_at: datetime


@dataclass(slots=True)
class RunRecord:
    run_id: str
    requested_week: str
    window_start: date
    window_end: date
    started_at: datetime
    completed_at: datetime | None
    status: str
    source_stats: dict[str, dict[str, int]]
    warnings: list[str]
    errors: list[str]
