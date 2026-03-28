from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections import defaultdict
from pathlib import Path
from typing import Any

from .models import AppConfig, NormalizedItem, RunRecord, SummaryRecord
from .sources import SOURCE_REGISTRY
from .utils import ensure_directory, to_iso_date

try:
    from wordcloud import WordCloud  # type: ignore
except ImportError:
    WordCloud = None

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
        json_path = target_dir / "weekly_report.json"

        json_path.write_text(
            json.dumps(self._build_json_payload(config, run, items_with_summaries), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        
        paths = {"json": str(json_path)}
        
        for item_type, filename, title in [
            ("paper", "papers.md", "Papers Report"),
            ("news_article", "news.md", "News Report"),
        ]:
            md_content = self._build_markdown_for_type(
                config, run, items_with_summaries, item_type, title, target_dir
            )
            md_path = target_dir / filename
            md_path.write_text(md_content, encoding="utf-8")
            paths[item_type] = str(md_path)
            
        return paths

    def _build_markdown_for_type(
        self,
        config: AppConfig,
        run: RunRecord,
        items_with_summaries: list[dict[str, Any]],
        item_type_filter: str,
        report_title: str,
        target_dir: Path,
    ) -> str:
        grouped = self._group_by_topic(config, items_with_summaries)
        type_sources = []
        type_new_items = 0
        for src, stats in run.source_stats.items():
            adapter_cls = SOURCE_REGISTRY.get(src)
            if adapter_cls and getattr(adapter_cls, "item_type", None) == item_type_filter:
                type_sources.append(src)
                type_new_items += stats.get("new_items", 0)

        lines = [
            f"# {report_title}",
            "",
            f"- Window: `{run.window_start.isoformat()}` to `{run.window_end.isoformat()}`",
            f"- Sources queried: {', '.join(sorted(type_sources)) if type_sources else 'None'}",
            f"- New items found: {type_new_items}",
        ]
        if run.errors:
            lines.extend(["", "## Partial Failures", ""])
            lines.extend([f"- {error}" for error in run.errors])
        if run.warnings:
            lines.extend(["", "## Warnings", ""])
            lines.extend([f"- {warning}" for warning in run.warnings])

        wordcloud_text_chunks = []
        for topic in config.topics:
            topic_records = grouped.get(topic.topic_id, [])
            matches = [record for record in topic_records if record["item"].item_type == item_type_filter]
            for record in matches:
                item = record["item"]
                if item.title:
                    wordcloud_text_chunks.append(str(item.title))
                if item.abstract_or_body:
                    wordcloud_text_chunks.append(str(item.abstract_or_body))

        we_have_text = len(wordcloud_text_chunks) > 0
        if we_have_text:
            full_text = " ".join(wordcloud_text_chunks)
            wc_filename = f"wordcloud_{item_type_filter}.png"
            wc_path = target_dir / wc_filename
            has_wordcloud = self._generate_wordcloud(full_text, wc_path)
            
            if has_wordcloud:
                lines.extend([
                    "",
                    "## Week's Trend",
                    "",
                    f"![Word Cloud]({wc_filename})",
                    ""
                ])

        toc_lines = ["", "## Table of Contents"]
        has_items_in_report = False

        for topic in config.topics:
            topic_records = grouped.get(topic.topic_id, [])
            matches = [record for record in topic_records if record["item"].item_type == item_type_filter]
            if matches:
                has_items_in_report = True
                toc_lines.extend(["", f"### {topic.display_name}"])
                for idx, record in enumerate(matches, 1):
                    item = record["item"]
                    safe_id = str(item.item_id).replace(":", "-").replace(".", "-").replace("/", "-")
                    toc_lines.append(f"{idx}. [{item.title}](#{safe_id})")

        if has_items_in_report:
            lines.extend(toc_lines)


        for topic in config.topics:
            topic_records = grouped.get(topic.topic_id, [])
            matches = [record for record in topic_records if record["item"].item_type == item_type_filter]
            
            lines.extend(["", f"## {topic.display_name}", ""])
            if not matches:
                lines.append("No new items for this topic.")
                continue

            for record in matches:
                item: NormalizedItem = record["item"]
                summary: SummaryRecord | None = record["summary"]
                safe_id = str(item.item_id).replace(":", "-").replace(".", "-").replace("/", "-")
                lines.append("<br>")
                lines.append("---")
                lines.append("<br>")
                lines.append("")
                lines.append(f"<a id=\"{safe_id}\"></a>")
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

    def _generate_wordcloud(self, text: str, output_path: Path) -> bool:
        if not text.strip():
            return False
        if WordCloud is None:
            return False
        try:
            wordcloud = WordCloud(
                width=800,
                height=400,
                background_color="white",
                max_words=100,
                collocations=False
            ).generate(text)
            wordcloud.to_file(str(output_path))
            return True
        except Exception:
            return False

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
        for topic_id in grouped:
            grouped[topic_id].sort(
                key=lambda r: r["item"].raw_payload.get("_relevance_score", 0.0), reverse=True
            )
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
