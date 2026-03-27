from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .models import NormalizedItem, RunRecord, SummaryRecord
from .utils import (
    ensure_directory,
    make_item_id,
    parse_date,
    parse_iso_datetime,
    to_iso_date,
    to_iso_datetime,
    unique_preserve_order,
    utc_now,
)


class Storage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        ensure_directory(self.db_path.parent)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def close(self) -> None:
        self.connection.close()

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                requested_week TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                source_stats_json TEXT NOT NULL,
                warnings_json TEXT NOT NULL,
                errors_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS items (
                item_id TEXT PRIMARY KEY,
                identity_key TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                item_type TEXT NOT NULL,
                title TEXT NOT NULL,
                authors_json TEXT NOT NULL,
                published_at TEXT,
                discovered_at TEXT NOT NULL,
                abstract_or_body TEXT,
                url TEXT NOT NULL,
                doi TEXT,
                topic_ids_json TEXT NOT NULL,
                raw_hash TEXT NOT NULL,
                raw_payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS run_items (
                run_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                source TEXT NOT NULL,
                is_new INTEGER NOT NULL,
                PRIMARY KEY (run_id, item_id)
            );

            CREATE TABLE IF NOT EXISTS summaries (
                item_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                metadata_markdown TEXT NOT NULL,
                source_excerpt TEXT,
                short_summary TEXT NOT NULL,
                generated_at TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def create_run(self, requested_week: str, window_start: date, window_end: date) -> RunRecord:
        run_id = uuid.uuid4().hex
        started_at = utc_now()
        run = RunRecord(
            run_id=run_id,
            requested_week=requested_week,
            window_start=window_start,
            window_end=window_end,
            started_at=started_at,
            completed_at=None,
            status="running",
            source_stats={},
            warnings=[],
            errors=[],
        )
        self.connection.execute(
            """
            INSERT INTO runs (
                run_id, requested_week, window_start, window_end, started_at,
                completed_at, status, source_stats_json, warnings_json, errors_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                run.requested_week,
                to_iso_date(run.window_start),
                to_iso_date(run.window_end),
                to_iso_datetime(run.started_at),
                None,
                run.status,
                json.dumps(run.source_stats),
                json.dumps(run.warnings),
                json.dumps(run.errors),
            ),
        )
        self.connection.commit()
        return run

    def finalize_run(
        self,
        run_id: str,
        *,
        status: str,
        source_stats: dict[str, dict[str, int]],
        warnings: list[str],
        errors: list[str],
    ) -> None:
        self.connection.execute(
            """
            UPDATE runs
            SET completed_at = ?, status = ?, source_stats_json = ?, warnings_json = ?, errors_json = ?
            WHERE run_id = ?
            """,
            (
                to_iso_datetime(utc_now()),
                status,
                json.dumps(source_stats, sort_keys=True),
                json.dumps(warnings),
                json.dumps(errors),
                run_id,
            ),
        )
        self.connection.commit()

    def get_run(self, run_id: str) -> RunRecord:
        row = self.connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown run_id: {run_id}")
        return RunRecord(
            run_id=row["run_id"],
            requested_week=row["requested_week"],
            window_start=parse_date(row["window_start"]) or date.today(),
            window_end=parse_date(row["window_end"]) or date.today(),
            started_at=parse_iso_datetime(row["started_at"]) or utc_now(),
            completed_at=parse_iso_datetime(row["completed_at"]),
            status=row["status"],
            source_stats=json.loads(row["source_stats_json"]),
            warnings=json.loads(row["warnings_json"]),
            errors=json.loads(row["errors_json"]),
        )

    def upsert_item(self, item: NormalizedItem) -> tuple[str, bool]:
        existing = self.connection.execute(
            "SELECT * FROM items WHERE identity_key = ?",
            (item.identity_key,),
        ).fetchone()
        now = to_iso_datetime(utc_now())
        if existing:
            merged_topics = unique_preserve_order(json.loads(existing["topic_ids_json"]) + item.topic_ids)
            updated_item = self._merge_item(existing, item)
            self.connection.execute(
                """
                UPDATE items
                SET topic_ids_json = ?, source = ?, source_id = ?, item_type = ?, title = ?, authors_json = ?,
                    published_at = ?, discovered_at = ?, abstract_or_body = ?, url = ?, doi = ?, raw_hash = ?,
                    raw_payload_json = ?, updated_at = ?
                WHERE item_id = ?
                """,
                (
                    json.dumps(merged_topics),
                    updated_item.source,
                    updated_item.source_id,
                    updated_item.item_type,
                    updated_item.title,
                    json.dumps(updated_item.authors_or_author),
                    to_iso_date(updated_item.published_at),
                    to_iso_datetime(updated_item.discovered_at),
                    updated_item.abstract_or_body,
                    updated_item.url,
                    updated_item.doi,
                    updated_item.raw_hash,
                    json.dumps(updated_item.raw_payload, sort_keys=True),
                    now,
                    existing["item_id"],
                ),
            )
            self.connection.commit()
            return str(existing["item_id"]), False

        item_id = item.item_id or make_item_id(item.identity_key)
        self.connection.execute(
            """
            INSERT INTO items (
                item_id, identity_key, source, source_id, item_type, title, authors_json,
                published_at, discovered_at, abstract_or_body, url, doi, topic_ids_json,
                raw_hash, raw_payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                item.identity_key,
                item.source,
                item.source_id,
                item.item_type,
                item.title,
                json.dumps(item.authors_or_author),
                to_iso_date(item.published_at),
                to_iso_datetime(item.discovered_at),
                item.abstract_or_body,
                item.url,
                item.doi,
                json.dumps(item.topic_ids),
                item.raw_hash,
                json.dumps(item.raw_payload, sort_keys=True),
                now,
                now,
            ),
        )
        self.connection.commit()
        return item_id, True

    def _merge_item(self, existing: sqlite3.Row, new_item: NormalizedItem) -> NormalizedItem:
        existing_authors = json.loads(existing["authors_json"])
        abstract_or_body = existing["abstract_or_body"]
        if new_item.abstract_or_body and (
            not abstract_or_body or len(new_item.abstract_or_body) > len(abstract_or_body)
        ):
            abstract_or_body = new_item.abstract_or_body
        return NormalizedItem(
            source=str(existing["source"] or new_item.source),
            source_id=str(existing["source_id"] or new_item.source_id),
            item_type=str(existing["item_type"] or new_item.item_type),
            title=str(existing["title"] or new_item.title),
            authors_or_author=existing_authors or new_item.authors_or_author,
            published_at=parse_date(existing["published_at"]) or new_item.published_at,
            discovered_at=parse_iso_datetime(existing["discovered_at"]) or new_item.discovered_at,
            abstract_or_body=abstract_or_body,
            url=str(existing["url"] or new_item.url),
            doi=str(existing["doi"] or new_item.doi) if (existing["doi"] or new_item.doi) else None,
            topic_ids=unique_preserve_order(json.loads(existing["topic_ids_json"]) + new_item.topic_ids),
            raw_hash=new_item.raw_hash,
            raw_payload=new_item.raw_payload or json.loads(existing["raw_payload_json"]),
            identity_key=str(existing["identity_key"]),
            item_id=str(existing["item_id"]),
        )

    def attach_item_to_run(self, run_id: str, item_id: str, source: str, is_new: bool) -> None:
        self.connection.execute(
            """
            INSERT INTO run_items (run_id, item_id, source, is_new)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(run_id, item_id) DO UPDATE SET
                source = excluded.source,
                is_new = CASE
                    WHEN run_items.is_new = 1 OR excluded.is_new = 1 THEN 1
                    ELSE 0
                END
            """,
            (run_id, item_id, source, 1 if is_new else 0),
        )
        self.connection.commit()

    def list_items_for_run(self, run_id: str) -> list[NormalizedItem]:
        rows = self.connection.execute(
            """
            SELECT i.*
            FROM items i
            JOIN run_items ri ON ri.item_id = i.item_id
            WHERE ri.run_id = ?
            ORDER BY COALESCE(i.published_at, substr(i.discovered_at, 1, 10)) DESC, i.title ASC
            """,
            (run_id,),
        ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def get_item(self, item_id: str) -> NormalizedItem:
        row = self.connection.execute("SELECT * FROM items WHERE item_id = ?", (item_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown item_id: {item_id}")
        return self._row_to_item(row)

    def _row_to_item(self, row: sqlite3.Row) -> NormalizedItem:
        return NormalizedItem(
            item_id=str(row["item_id"]),
            source=str(row["source"]),
            source_id=str(row["source_id"]),
            item_type=str(row["item_type"]),
            title=str(row["title"]),
            authors_or_author=json.loads(row["authors_json"]),
            published_at=parse_date(row["published_at"]),
            discovered_at=parse_iso_datetime(row["discovered_at"]) or utc_now(),
            abstract_or_body=row["abstract_or_body"],
            url=str(row["url"]),
            doi=row["doi"],
            topic_ids=json.loads(row["topic_ids_json"]),
            raw_hash=str(row["raw_hash"]),
            raw_payload=json.loads(row["raw_payload_json"]),
            identity_key=str(row["identity_key"]),
        )

    def save_summary(self, summary: SummaryRecord) -> None:
        self.connection.execute(
            """
            INSERT OR REPLACE INTO summaries (
                item_id, provider, metadata_markdown, source_excerpt, short_summary, generated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                summary.item_id,
                summary.provider,
                summary.metadata_markdown,
                summary.source_excerpt,
                summary.short_summary,
                to_iso_datetime(summary.generated_at),
            ),
        )
        self.connection.commit()

    def get_summary(self, item_id: str) -> SummaryRecord | None:
        row = self.connection.execute("SELECT * FROM summaries WHERE item_id = ?", (item_id,)).fetchone()
        if row is None:
            return None
        return SummaryRecord(
            item_id=str(row["item_id"]),
            provider=str(row["provider"]),
            metadata_markdown=str(row["metadata_markdown"]),
            source_excerpt=row["source_excerpt"],
            short_summary=str(row["short_summary"]),
            generated_at=parse_iso_datetime(row["generated_at"]) or utc_now(),
        )

    def list_run_items_with_summaries(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT i.*, s.provider, s.metadata_markdown, s.source_excerpt, s.short_summary, s.generated_at, ri.is_new
            FROM items i
            JOIN run_items ri ON ri.item_id = i.item_id
            LEFT JOIN summaries s ON s.item_id = i.item_id
            WHERE ri.run_id = ?
            ORDER BY COALESCE(i.published_at, substr(i.discovered_at, 1, 10)) DESC, i.title ASC
            """,
            (run_id,),
        ).fetchall()
        records: list[dict[str, Any]] = []
        for row in rows:
            records.append(
                {
                    "item": self._row_to_item(row),
                    "summary": self.get_summary(str(row["item_id"])),
                    "is_new": bool(row["is_new"]),
                }
            )
        return records
