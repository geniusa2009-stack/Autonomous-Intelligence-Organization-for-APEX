"""Lexical retrieval over the knowledge graph (embedding hook optional)."""

from __future__ import annotations

import re

from apex_one.knowledge.graph import KGNode, KnowledgeGraph


def _tok(s: str) -> set[str]:
    return set(re.findall(r"[\w؀-ۿ]+", s.lower()))


def search(graph: KnowledgeGraph, query: str, k: int = 5) -> list[KGNode]:
    q = _tok(query)
    scored = [(len(q & _tok(n.label)) / (len(q) or 1), n) for n in graph.nodes.values()]
    return [n for s, n in sorted(scored, key=lambda x: -x[0]) if s > 0][:k]
