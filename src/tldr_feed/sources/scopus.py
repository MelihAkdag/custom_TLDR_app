from __future__ import annotations

from datetime import date

from ..models import RawItem, TopicProfile
from .base import SourceAdapter


class ScopusAdapter(SourceAdapter):
    source_name = "scopus"

    def search(self, topic: TopicProfile, start_date: date, end_date: date) -> list[RawItem]:
        raise NotImplementedError(
            "Scopus is intentionally unimplemented in v1. Add institutional/API credentials before enabling it."
        )
