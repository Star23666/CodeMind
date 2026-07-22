from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class LexicalDocument:
    key: str
    text: str


def rough_tokens(value: str) -> list[str]:
    lowered = value.casefold()
    tokens: list[str] = []
    current: list[str] = []
    cjk_chars: list[str] = []
    for char in lowered:
        if char.isascii() and char.isalnum():
            current.append(char)
            continue
        if current:
            tokens.append("".join(current))
            current = []
        if "\u4e00" <= char <= "\u9fff":
            cjk_chars.append(char)
    if current:
        tokens.append("".join(current))
    tokens.extend(
        "".join(cjk_chars[index : index + 2])
        for index in range(max(len(cjk_chars) - 1, 0))
    )
    return tokens


def keyword_overlap(query: str, text: str) -> float:
    query_tokens = set(rough_tokens(query))
    text_tokens = set(rough_tokens(text))
    if not query_tokens or not text_tokens:
        return 0.0
    return len(query_tokens & text_tokens) / len(query_tokens)


def bm25_rank(
    query: str,
    documents: Iterable[LexicalDocument],
    *,
    top_k: int,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[tuple[str, float]]:
    items = list(documents)
    if not items or top_k <= 0:
        return []

    query_tokens = list(dict.fromkeys(rough_tokens(query)))
    if not query_tokens:
        return []
    tokenized = [rough_tokens(item.text) for item in items]
    average_length = sum(len(tokens) for tokens in tokenized) / len(tokenized)
    average_length = max(average_length, 1.0)
    document_frequency = Counter(
        token for tokens in tokenized for token in set(tokens) if token in query_tokens
    )
    scores: list[tuple[str, float]] = []
    document_count = len(items)
    for item, tokens in zip(items, tokenized, strict=True):
        frequencies = Counter(tokens)
        length_ratio = len(tokens) / average_length
        score = 0.0
        for token in query_tokens:
            frequency = frequencies[token]
            if frequency == 0:
                continue
            frequency_in_documents = document_frequency[token]
            inverse_document_frequency = math.log(
                1.0
                + (document_count - frequency_in_documents + 0.5)
                / (frequency_in_documents + 0.5)
            )
            denominator = frequency + k1 * (1.0 - b + b * length_ratio)
            score += inverse_document_frequency * frequency * (k1 + 1.0) / denominator
        if score > 0:
            scores.append((item.key, score))
    scores.sort(key=lambda item: item[1], reverse=True)
    return scores[:top_k]


def reciprocal_rank_fusion(
    rankings: Iterable[Iterable[str]],
    *,
    rank_constant: int = 60,
) -> dict[str, float]:
    ranking_lists = [list(dict.fromkeys(ranking)) for ranking in rankings]
    if not ranking_lists:
        return {}
    scores: defaultdict[str, float] = defaultdict(float)
    for ranking in ranking_lists:
        for rank, key in enumerate(ranking, start=1):
            scores[key] += 1.0 / (rank_constant + rank)
    maximum = len(ranking_lists) / (rank_constant + 1)
    return {
        key: min(1.0, score / maximum) if maximum else 0.0
        for key, score in scores.items()
    }
