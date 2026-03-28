from __future__ import annotations

from ..models import SourceSettings
from .arxiv import ArxivAdapter
from .base import SourceAdapter
from .crossref import CrossrefAdapter
from .news_rss import NewsRssAdapter
from .openalex import OpenAlexAdapter


SOURCE_REGISTRY: dict[str, type[SourceAdapter]] = {
    "arxiv": ArxivAdapter,
    "openalex": OpenAlexAdapter,
    "crossref": CrossrefAdapter,
    "news_rss": NewsRssAdapter,
}


def build_adapter(name: str, settings: SourceSettings) -> SourceAdapter:
    adapter_class = SOURCE_REGISTRY[name]
    return adapter_class(settings)
