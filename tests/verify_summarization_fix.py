import os
import sqlite3
from pathlib import Path
from datetime import date, datetime
from tldr_feed.storage import Storage
from tldr_feed.models import NormalizedItem, SummaryRecord, RunRecord
from tldr_feed.summarization import Summarizer
from tldr_feed.pipeline import summarize_run

class MockSummarizer(Summarizer):
    def __init__(self, name):
        self._name = name
    @property
    def provider_name(self) -> str:
        return "mock"
    @property
    def full_provider_name(self) -> str:
        return self._name
    def _request_summary(self, prompt: str) -> str:
        return f"Summary by {self._name}"

def test_summarization_retriggering():
    db_path = Path("/tmp/test_storage.db")
    if db_path.exists():
        db_path.unlink()
    
    storage = Storage(db_path)
    
    # Create a dummy item
    item = NormalizedItem(
        item_id="test_item",
        identity_key="test_key",
        source="test",
        source_id="test_id",
        item_type="paper",
        title="Test Title",
        authors_or_author=["Author"],
        published_at=date(2026, 3, 28),
        discovered_at=datetime.utcnow(),
        abstract_or_body="This is a test abstract.",
        url="http://example.com",
        doi="10.1000/1",
        topic_ids=["test_topic"],
        raw_hash="hash",
        raw_payload={}
    )
    storage.upsert_item(item)
    
    # Create a run and attach item
    run = storage.create_run("2026-W13", date(2026, 3, 23), date(2026, 3, 29))
    storage.attach_item_to_run(run.run_id, "test_item", "test", True)
    
    # 1. Summarize with Model A
    summarizer_a = MockSummarizer("model_a")
    result_a = summarize_run(storage, run.run_id, summarizer_a)
    print(f"First run (Model A): {result_a}")
    summary = storage.get_summary("test_item")
    print(f"Stored summary provider: {summary.provider}")
    assert summary.provider == "model_a"
    assert result_a["created"] == 1
    
    # 2. Run again with Model A - should skip
    result_a_skip = summarize_run(storage, run.run_id, summarizer_a)
    print(f"Second run (Model A): {result_a_skip}")
    assert result_a_skip["skipped"] == 1
    assert result_a_skip["created"] == 0
    
    # 3. Summarize with Model B - should re-summarize
    summarizer_b = MockSummarizer("model_b")
    result_b = summarize_run(storage, run.run_id, summarizer_b)
    print(f"Third run (Model B): {result_b}")
    summary = storage.get_summary("test_item")
    print(f"Stored summary provider: {summary.provider}")
    assert summary.provider == "model_b"
    assert result_b["created"] == 1
    assert result_b["skipped"] == 0

    print("Verification successful!")

if __name__ == "__main__":
    # Add src to sys.path to import tldr_feed
    import sys
    sys.path.append(str(Path("/Users/melihakdag/Projects/custom_TLDR_app/src")))
    test_summarization_retriggering()
