"""SourceAuthorityJudge + cycle-year detection + official-domain hypothesis."""

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlparse

from apex_one.core.schemas.evidence import SourceKind

FORUM_HINTS = ("reddit.", "quora.", "forum", "talk", "stackexchange", "facebook.", "tiktok.", "/t/")
AGGREGATOR_HINTS = ("roundup", "scholarships.com", "scholarshipportal", "top-", "best-", "blog", "medium.com")


def domain_of(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def classify(url: str, official_domains: list[str], content_type: str = "text/html") -> tuple[SourceKind, float]:
    host = domain_of(url)
    if url.startswith("file://"):
        return SourceKind.UNKNOWN, 0.3
    if any(host == d or host.endswith("." + d) for d in official_domains):
        return (SourceKind.OFFICIAL_DOCUMENT, 0.95) if "pdf" in content_type else (SourceKind.OFFICIAL, 0.95)
    if host.endswith(".gov") or ".gov." in host or host.endswith("state.gov"):
        return SourceKind.GOVERNMENT, 0.85
    low = url.lower()
    if any(h in low for h in FORUM_HINTS):
        return SourceKind.FORUM, 0.15
    if any(h in low for h in AGGREGATOR_HINTS):
        return SourceKind.AGGREGATOR, 0.35
    if host.endswith(".edu"):
        return SourceKind.THIRD_PARTY, 0.5
    return SourceKind.THIRD_PARTY, 0.3


CYCLE_RX = [
    re.compile(r"\b(?:fall|autumn|spring|entry|intake|class of)\s+(20\d\d)\b", re.I),
    re.compile(r"\b(20\d\d)\s+(?:entry|intake|admissions?)\b", re.I),
    re.compile(r"\b(20\d\d)\s*[-–/]\s*(20\d\d)\b"),
]


def detect_cycle_year(text: str) -> int | None:
    for rx in CYCLE_RX:
        m = rx.search(text)
        if m:
            groups = [g for g in m.groups() if g]
            return int(groups[-1]) if len(groups) == 2 else int(groups[0])
    return None


def infer_official_domains(urls: list[str], institution: str) -> list[str]:
    """Hypothesise the institution's official domain(s) from discovered URLs.

    Academic roots (.edu, .ac.xx) containing an institution token are strong evidence; any other root
    must contain ALL institution tokens in its registrable label. A human can always override.
    """
    stop = ("college", "university", "of", "the", "and", "school", "institute")
    tokens = [t for t in re.findall(r"[a-z]+", institution.lower()) if t not in stop]
    if not tokens:
        return []
    counts: Counter[str] = Counter()
    for u in urls:
        host = domain_of(u)
        parts = host.split(".")
        academic = len(parts) >= 3 and parts[-2] == "ac"
        root = ".".join(parts[-3:]) if academic else ".".join(parts[-2:])
        label = root.split(".")[0]
        if (root.endswith(".edu") or academic) and any(t in label for t in tokens):
            counts[root] += 3
        elif [t for t in label.split("-") if t not in stop] == tokens:
            counts[root] += 1
    academic_hits = [d for d in counts if d.endswith(".edu") or ".ac." in d]
    ranked = [d for d, _ in counts.most_common()]
    return (academic_hits or ranked)[:2]
