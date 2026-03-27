from __future__ import annotations

import re

from .models import RawItem, TopicProfile

STOP_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def score_item_relevance(raw_item: RawItem, topic: TopicProfile) -> float:
    title = raw_item.title.casefold()
    body = (raw_item.abstract_or_body or "").casefold()
    title_tokens = set(_tokenize(title))
    body_tokens = set(_tokenize(body))
    score = 0.0

    for keyword in topic.keywords:
        normalized = keyword.casefold().strip()
        if not normalized:
            continue
        if normalized in title:
            score += 4.0
            continue
        if normalized in body:
            score += 2.5
            continue

        keyword_tokens = [token for token in _tokenize(normalized) if token not in STOP_WORDS]
        if not keyword_tokens:
            continue
        title_hits = sum(token in title_tokens for token in keyword_tokens)
        body_hits = sum(token in body_tokens for token in keyword_tokens)
        coverage = (2 * title_hits + body_hits) / (3 * len(keyword_tokens))
        if coverage >= 0.75:
            score += 2.5
        elif coverage >= 0.5:
            score += 1.5
        elif coverage > 0:
            score += 0.5

    for include_term in topic.include_terms:
        normalized = include_term.casefold().strip()
        if not normalized:
            continue
        if normalized in title:
            score += 1.5
        elif normalized in body:
            score += 1.0

    return score


def _tokenize(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.casefold())
