from __future__ import annotations

from ..models import SourceSettings
from .arxiv import ArxivAdapter
from .base import SourceAdapter
from .crossref import CrossrefAdapter
from .google_scholar import GoogleScholarAdapter
from .linkedin_import import LinkedInImportAdapter
from .linkedin_posts import LinkedInPostsAdapter
from .news_rss import NewsRssAdapter
from .openalex import OpenAlexAdapter
from .scopus import ScopusAdapter


SOURCE_REGISTRY: dict[str, type[SourceAdapter]] = {
    "arxiv": ArxivAdapter,
    "openalex": OpenAlexAdapter,
    "crossref": CrossrefAdapter,
    "linkedin_import": LinkedInImportAdapter,
    "linkedin_posts": LinkedInPostsAdapter,
    "news_rss": NewsRssAdapter,
    "google_scholar": GoogleScholarAdapter,
    "scopus": ScopusAdapter,
}


def build_adapter(name: str, settings: SourceSettings) -> SourceAdapter:
    adapter_class = SOURCE_REGISTRY[name]
    return adapter_class(settings)
