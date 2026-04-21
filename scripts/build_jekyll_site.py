#!/usr/bin/env python3
"""
Prepares Jekyll site content from the reports/ directory.

For each week directory found under reports/{year}/{week}/:
  - Copies news.md and papers.md with Jekyll front matter prepended
  - Copies wordcloud PNG images
Generates jekyll/index.md listing all available reports.

Run this before `bundle exec jekyll build` inside the jekyll/ directory.
"""
from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
JEKYLL_DIR = PROJECT_ROOT / "jekyll"
JEKYLL_REPORTS_DIR = JEKYLL_DIR / "reports"


def week_window(year: int, week: int) -> tuple[str, str]:
    start = date.fromisocalendar(year, week, 1)
    end = date.fromisocalendar(year, week, 7)
    return str(start), str(end)


def extract_window(text: str) -> tuple[str | None, str | None]:
    m = re.search(r"Window:\s*`(\d{4}-\d{2}-\d{2})`\s*to\s*`(\d{4}-\d{2}-\d{2})`", text)
    return (m.group(1), m.group(2)) if m else (None, None)


def write_with_front_matter(src: Path, dst: Path, front_matter: dict) -> None:
    content = src.read_text(encoding="utf-8")
    lines = ["---"]
    for key, value in front_matter.items():
        if isinstance(value, str):
            escaped = value.replace('"', '\\"')
            lines.append(f'{key}: "{escaped}"')
        else:
            lines.append(f"{key}: {value}")
    lines += ["---", ""]
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(lines) + content, encoding="utf-8")


def build_index(entries: list[dict]) -> str:
    rows = []
    for e in sorted(entries, key=lambda x: (x["year"], x["week"]), reverse=True):
        year, week = e["year"], e["week"]
        base = f"/custom_TLDR_app/reports/{year}/{week}"
        news_cell = f'<a href="{base}/news/">News</a>' if e["has_news"] else "&mdash;"
        papers_cell = f'<a href="{base}/papers/">Papers</a>' if e["has_papers"] else "&mdash;"
        rows.append(
            f"| {year} | {week} | {e['start']} &rarr; {e['end']} "
            f"| {news_cell} | {papers_cell} |"
        )

    table = "\n".join(
        [
            "| Year | Week | Dates | News | Papers |",
            "|------|------|-------|------|--------|",
        ]
        + rows
    )

    return f"""---
layout: default
title: "TLDR Weekly Reports"
---

<h1 class="index-heading">Weekly Reports</h1>
<p class="index-description">Curated AI-summarised maritime research and news, published every week.</p>

{table}
"""


def main() -> None:
    if JEKYLL_REPORTS_DIR.exists():
        shutil.rmtree(JEKYLL_REPORTS_DIR)
    JEKYLL_REPORTS_DIR.mkdir(parents=True)

    entries: list[dict] = []

    for year_dir in sorted(REPORTS_DIR.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        year = int(year_dir.name)

        for week_dir in sorted(year_dir.iterdir()):
            if not week_dir.is_dir() or not week_dir.name.isdigit():
                continue
            week = int(week_dir.name)

            try:
                start_str, end_str = week_window(year, week)
            except ValueError:
                start_str, end_str = "unknown", "unknown"

            has_news = has_papers = False

            for report_type, filename in (("news", "news.md"), ("papers", "papers.md")):
                src = week_dir / filename
                if not src.exists():
                    continue

                text = src.read_text(encoding="utf-8")
                w_start, w_end = extract_window(text)
                if w_start:
                    start_str, end_str = w_start, w_end

                dst = JEKYLL_REPORTS_DIR / str(year) / str(week) / filename
                write_with_front_matter(
                    src,
                    dst,
                    {
                        "layout": "report",
                        "title": f"Week {week} ({year}) — {report_type.capitalize()}",
                        "week": week,
                        "year": year,
                        "report_type": report_type,
                        "window_start": start_str,
                        "window_end": end_str,
                        "permalink": f"/reports/{year}/{week}/{report_type}/",
                    },
                )
                if report_type == "news":
                    has_news = True
                else:
                    has_papers = True

            for img in week_dir.glob("*.png"):
                dst_img = JEKYLL_REPORTS_DIR / str(year) / str(week) / img.name
                dst_img.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(img, dst_img)

            if has_news or has_papers:
                entries.append(
                    {
                        "year": year,
                        "week": week,
                        "start": start_str,
                        "end": end_str,
                        "has_news": has_news,
                        "has_papers": has_papers,
                    }
                )

    (JEKYLL_DIR / "index.md").write_text(build_index(entries), encoding="utf-8")
    print(f"Prepared {len(entries)} weekly reports for Jekyll.")


if __name__ == "__main__":
    main()
