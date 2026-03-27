from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path

from .content_extraction import LandingPageAbstractFetcher
from .models import AppConfig, NormalizedItem, RawItem, RunRecord, SourceSettings, TopicProfile
from .relevance import score_item_relevance
from .reporting import MarkdownJsonReportWriter
from .sources import SOURCE_REGISTRY, build_adapter
from .sources.semantic_scholar import SemanticScholarEnricher
from .storage import Storage
from .summarization import AzureOpenAISummarizer, DeterministicSummarizer, Summarizer
from .utils import build_identity_key, make_item_id, normalize_doi, stable_json_hash, unique_preserve_order


def collect_items(
    config: AppConfig,
    storage: Storage,
    requested_week: str,
    start_date: date,
    end_date: date,
) -> RunRecord:
    run = storage.create_run(requested_week=requested_week, window_start=start_date, window_end=end_date)
    source_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"fetched": 0, "filtered_out": 0, "new_items": 0, "existing_items": 0}
    )
    warnings: list[str] = []
    errors: list[str] = []

    enricher = None
    semantic_scholar_settings = config.sources.get("semantic_scholar")
    if semantic_scholar_settings and semantic_scholar_settings.enabled:
        enricher = SemanticScholarEnricher(semantic_scholar_settings)
    landing_page_settings = config.sources.get(
        "landing_page",
        SourceSettings(name="landing_page", enabled=True, timeout_seconds=20),
    )
    landing_page_fetcher = (
        LandingPageAbstractFetcher(landing_page_settings) if landing_page_settings.enabled else None
    )

    for topic in config.topics:
        for source_name in topic.sources:
            settings = config.sources.get(source_name, SourceSettings(name=source_name))
            if not settings.enabled:
                continue
            adapter_class = SOURCE_REGISTRY.get(source_name)
            if adapter_class is None:
                warnings.append(f"Topic {topic.topic_id} references unknown source {source_name}.")
                continue
            adapter = build_adapter(source_name, settings)
            try:
                raw_items = adapter.search(topic, start_date, end_date)
                source_stats[source_name]["fetched"] += len(raw_items)
                for raw_item in raw_items:
                    relevance_score = score_item_relevance(raw_item, topic)
                    raw_item.raw_payload = {**raw_item.raw_payload, "_relevance_score": relevance_score}
                    if not _matches_topic_filters(raw_item, topic, relevance_score):
                        source_stats[source_name]["filtered_out"] += 1
                        continue
                    normalized = normalize_raw_item(raw_item)
                    if enricher is not None and normalized.item_type == "paper" and (
                        not normalized.abstract_or_body or not normalized.doi
                    ):
                        normalized = enricher.enrich(normalized)
                    if landing_page_fetcher is not None and normalized.item_type == "paper" and not normalized.abstract_or_body:
                        normalized = landing_page_fetcher.enrich(normalized)
                    item_id, is_new = storage.upsert_item(normalized)
                    storage.attach_item_to_run(run.run_id, item_id, source_name, is_new)
                    if is_new:
                        source_stats[source_name]["new_items"] += 1
                    else:
                        source_stats[source_name]["existing_items"] += 1
            except NotImplementedError as exc:
                message = f"{source_name} for topic {topic.topic_id}: {exc}"
                warnings.append(message)
                errors.append(message)
            except Exception as exc:
                errors.append(f"{source_name} for topic {topic.topic_id}: {exc}")

    status = "success" if not errors else "partial"
    storage.finalize_run(
        run.run_id,
        status=status,
        source_stats=dict(source_stats),
        warnings=warnings,
        errors=errors,
    )
    return storage.get_run(run.run_id)


def summarize_run(storage: Storage, run_id: str, summarizer: Summarizer | None = None) -> dict[str, int]:
    summarizer = summarizer or AzureOpenAISummarizer()
    created = 0
    skipped = 0
    for item in storage.list_items_for_run(run_id):
        if storage.get_summary(item.item_id or "") is not None:
            skipped += 1
            continue
        summary = summarizer.summarize(item)
        storage.save_summary(summary)
        created += 1
    return {"created": created, "skipped": skipped}


def write_report(
    storage: Storage,
    config: AppConfig,
    run_id: str,
    output_dir: str | Path = "reports",
) -> dict[str, str]:
    writer = MarkdownJsonReportWriter()
    run = storage.get_run(run_id)
    records = storage.list_run_items_with_summaries(run_id)
    return writer.write(Path(output_dir), config, run, records)


def normalize_raw_item(raw_item: RawItem) -> NormalizedItem:
    normalized_doi = normalize_doi(raw_item.doi)
    identity_key = build_identity_key(raw_item.title, normalized_doi, raw_item.url)
    raw_hash = stable_json_hash(raw_item.raw_payload)
    return NormalizedItem(
        item_id=make_item_id(identity_key),
        source=raw_item.source,
        source_id=raw_item.source_id,
        item_type=raw_item.item_type,
        title=raw_item.title,
        authors_or_author=unique_preserve_order(raw_item.authors_or_author),
        published_at=raw_item.published_at,
        discovered_at=raw_item.discovered_at,
        abstract_or_body=raw_item.abstract_or_body,
        url=raw_item.url,
        doi=normalized_doi,
        topic_ids=[raw_item.topic_id],
        raw_hash=raw_hash,
        raw_payload=raw_item.raw_payload,
        identity_key=identity_key,
    )


def _matches_topic_filters(raw_item: RawItem, topic: TopicProfile, relevance_score: float) -> bool:
    haystack = " ".join(part for part in [raw_item.title, raw_item.abstract_or_body or ""] if part).casefold()
    if topic.include_terms and not any(term.casefold() in haystack for term in topic.include_terms):
        return False
    if topic.exclude_terms and any(term.casefold() in haystack for term in topic.exclude_terms):
        return False
    return relevance_score >= topic.min_relevance_score
