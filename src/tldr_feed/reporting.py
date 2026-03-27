from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections import defaultdict
from pathlib import Path
from typing import Any

from .models import AppConfig, NormalizedItem, RunRecord, SummaryRecord
from .utils import ensure_directory, to_iso_date


class ReportWriter(ABC):
    @abstractmethod
    def write(
        self,
        output_root: Path,
        config: AppConfig,
        run: RunRecord,
        items_with_summaries: list[dict[str, Any]],
    ) -> dict[str, str]:
        raise NotImplementedError


class MarkdownJsonReportWriter(ReportWriter):
    def write(
        self,
        output_root: Path,
        config: AppConfig,
        run: RunRecord,
        items_with_summaries: list[dict[str, Any]],
    ) -> dict[str, str]:
        iso_year, iso_week = run.window_end.isocalendar()[:2]
        target_dir = ensure_directory(output_root / str(iso_year) / f"{iso_week:02d}")
        markdown_path = target_dir / "weekly_report.md"
        json_path = target_dir / "weekly_report.json"

        markdown_path.write_text(
            self._build_markdown(config, run, items_with_summaries),
            encoding="utf-8",
        )
        json_path.write_text(
            json.dumps(self._build_json_payload(config, run, items_with_summaries), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return {"markdown": str(markdown_path), "json": str(json_path)}

    def _build_markdown(
        self,
        config: AppConfig,
        run: RunRecord,
        items_with_summaries: list[dict[str, Any]],
    ) -> str:
        grouped = self._group_by_topic(config, items_with_summaries)
        lines = [
            "# Weekly TLDR Report",
            "",
            f"- Run ID: `{run.run_id}`",
            f"- Week: `{run.requested_week}`",
            f"- Window: `{run.window_start.isoformat()}` to `{run.window_end.isoformat()}`",
            f"- Status: `{run.status}`",
            f"- Sources queried: {', '.join(sorted(run.source_stats)) if run.source_stats else 'None'}",
            f"- New items found: {sum(stats.get('new_items', 0) for stats in run.source_stats.values())}",
        ]
        if run.errors:
            lines.extend(["", "## Partial Failures", ""])
            lines.extend([f"- {error}" for error in run.errors])
        if run.warnings:
            lines.extend(["", "## Warnings", ""])
            lines.extend([f"- {warning}" for warning in run.warnings])

        for topic in config.topics:
            topic_records = grouped.get(topic.topic_id, [])
            lines.extend(["", f"## {topic.display_name}", ""])
            if not topic_records:
                lines.append("No new items for this topic.")
                continue
            for item_type, label in [
                ("paper", "Papers"),
                ("news_article", "News"),
                ("social_post", "LinkedIn Posts"),
            ]:
                matches = [record for record in topic_records if record["item"].item_type == item_type]
                lines.extend(["", f"### {label}", ""])
                if not matches:
                    lines.append("None.")
                    continue
                for record in matches:
                    item: NormalizedItem = record["item"]
                    summary: SummaryRecord | None = record["summary"]
                    lines.append("---")
                    lines.append("")
                    lines.append(f"### {item.title}")
                    lines.append("")
                    if summary:
                        lines.append("**Metadata**")
                        lines.append("")
                        lines.append(summary.metadata_markdown)
                        lines.append("")
                        lines.append("**AI Summary**")
                        lines.append("")
                        lines.append(summary.short_summary)
                        lines.append("")
                        if summary.source_excerpt:
                            lines.append("**Abstract / Source Text**")
                            lines.append("")
                            lines.append(f"> {summary.source_excerpt}")
                            lines.append("")
                    else:
                        lines.append("- Summary: Not generated.")
                    lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _build_json_payload(
        self,
        config: AppConfig,
        run: RunRecord,
        items_with_summaries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        grouped = self._group_by_topic(config, items_with_summaries)
        topics_payload: list[dict[str, Any]] = []
        for topic in config.topics:
            topic_records = grouped.get(topic.topic_id, [])
            topics_payload.append(
                {
                    "topic_id": topic.topic_id,
                    "display_name": topic.display_name,
                    "items": [self._record_to_json(record) for record in topic_records],
                }
            )
        return {
            "run_id": run.run_id,
            "requested_week": run.requested_week,
            "window_start": to_iso_date(run.window_start),
            "window_end": to_iso_date(run.window_end),
            "status": run.status,
            "source_stats": run.source_stats,
            "warnings": run.warnings,
            "errors": run.errors,
            "topics": topics_payload,
        }

    def _group_by_topic(
        self,
        config: AppConfig,
        items_with_summaries: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        known_topics = {topic.topic_id for topic in config.topics}
        for record in items_with_summaries:
            item: NormalizedItem = record["item"]
            for topic_id in item.topic_ids:
                if topic_id in known_topics:
                    grouped[topic_id].append(record)
        return grouped

    def _record_to_json(self, record: dict[str, Any]) -> dict[str, Any]:
        item: NormalizedItem = record["item"]
        summary: SummaryRecord | None = record["summary"]
        return {
            "item_id": item.item_id,
            "source": item.source,
            "source_id": item.source_id,
            "item_type": item.item_type,
            "title": item.title,
            "authors_or_author": item.authors_or_author,
            "published_at": to_iso_date(item.published_at),
            "url": item.url,
            "doi": item.doi,
            "topic_ids": item.topic_ids,
            "abstract_or_body": item.abstract_or_body,
            "summary": {
                "provider": summary.provider,
                "metadata_markdown": summary.metadata_markdown,
                "source_excerpt": summary.source_excerpt,
                "short_summary": summary.short_summary,
            }
            if summary
            else None,
        }
