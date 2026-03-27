from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .config import load_config, load_dotenv
from .pipeline import collect_items, summarize_run, write_report
from .storage import Storage
from .summarization import AzureOpenAISummarizer
from .utils import previous_completed_week, week_to_range


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Weekly research TLDR automation.")
    parser.add_argument("--config-dir", default="config", help="Directory containing topics.yaml and sources.yaml")
    parser.add_argument("--db", default="data/state.db", help="SQLite database path")

    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="Collect new items into the SQLite store.")
    collect.add_argument("--from", dest="from_date", help="Start date in YYYY-MM-DD")
    collect.add_argument("--to", dest="to_date", help="End date in YYYY-MM-DD")
    collect.add_argument("--week", help="ISO week in YYYY-WW or YYYY-W## format")

    summarize = subparsers.add_parser("summarize", help="Summarize collected items for a run.")
    summarize.add_argument("--run-id", required=True)

    report = subparsers.add_parser("report", help="Write Markdown and JSON reports for a run.")
    report.add_argument("--run-id", required=True)
    report.add_argument("--output-dir", default="reports")

    run_weekly = subparsers.add_parser("run-weekly", help="Collect, summarize, and report in one command.")
    run_weekly.add_argument("--week", help="ISO week in YYYY-WW or YYYY-W## format")
    run_weekly.add_argument("--output-dir", default="reports")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    load_dotenv(Path(".env"))
    config = load_config(args.config_dir)

    storage = Storage(args.db)
    try:
        if args.command == "collect":
            requested_week, start_date, end_date = _resolve_window(
                from_date=args.from_date,
                to_date=args.to_date,
                week=args.week,
            )
            run = collect_items(config, storage, requested_week, start_date, end_date)
            print(run.run_id)
            return

        if args.command == "summarize":
            stats = summarize_run(storage, args.run_id, summarizer=AzureOpenAISummarizer())
            print(stats)
            return

        if args.command == "report":
            outputs = write_report(storage, config, args.run_id, output_dir=args.output_dir)
            print(outputs)
            return

        if args.command == "run-weekly":
            requested_week, start_date, end_date = _resolve_window(week=args.week)
            run = collect_items(config, storage, requested_week, start_date, end_date)
            summarize_stats = summarize_run(storage, run.run_id, summarizer=AzureOpenAISummarizer())
            outputs = write_report(storage, config, run.run_id, output_dir=args.output_dir)
            print({"run_id": run.run_id, "summaries": summarize_stats, "reports": outputs})
            return
    finally:
        storage.close()


def _resolve_window(*, from_date: str | None = None, to_date: str | None = None, week: str | None = None):
    if week:
        return week_to_range(_normalize_week(week))
    if from_date and to_date:
        return (f"{from_date}:{to_date}", date.fromisoformat(from_date), date.fromisoformat(to_date))
    return previous_completed_week()


def _normalize_week(value: str) -> str:
    cleaned = value.strip().upper()
    if "-W" in cleaned:
        return cleaned
    if len(cleaned) == 7 and cleaned[4] == "-":
        return cleaned[:5] + "W" + cleaned[5:]
    return cleaned


if __name__ == "__main__":
    main()
