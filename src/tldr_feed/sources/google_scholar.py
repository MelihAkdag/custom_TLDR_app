from __future__ import annotations

from datetime import date

from ..models import RawItem, TopicProfile
from .base import SourceAdapter


class GoogleScholarAdapter(SourceAdapter):
    source_name = "google_scholar"

    def search(self, topic: TopicProfile, start_date: date, end_date: date) -> list[RawItem]:
        raise NotImplementedError(
            "Google Scholar is intentionally unimplemented in v1. Add a supported access method before enabling it."
        )
