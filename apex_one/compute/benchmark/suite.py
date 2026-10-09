"""ONE Compute model benchmark: small, deterministic-scored probes of APEX-relevant skills.

Results replace prior-estimate capabilities over time (stored in artifacts/bench/model_scores.json).
Runs only against routes the firewall allows; nothing is paid.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from apex_one.compute.broker import ComputeBroker
from apex_one.compute.providers import ChatMessage
from apex_one.core.schemas.compute import CapabilityRequest


@dataclass
class BenchTask:
    task_id: str
    prompt: str
    scorer: Callable[[str], float]
    json_mode: bool = False


def _score_date(text: str) -> float:
    return 100.0 if "2027-01-15" in text else 0.0


def _score_json_fee(text: str) -> float:
    try:
        data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))  # type: ignore[union-attr]
        return 100.0 if float(data.get("amount")) == 65 and str(data.get("currency")).upper() == "USD" else 30.0
    except Exception:
        return 0.0


def _score_dialect(text: str) -> float:
    markers = ["عشان", "إزاي", "دلوقتي", "مش", "كده", "يعني", "علشان", "لسه"]
    hits = sum(1 for m in markers if m in text)
    bureaucratic = sum(1 for m in ["يرجى", "حيث أن", "تجدر الإشارة"] if m in text)
    return max(0.0, min(100.0, hits * 25 - bureaucratic * 40))


BENCH_TASKS = [
    BenchTask("normalize_date", "Normalize this deadline to ISO format only: 'January 15th, 2027 (postmarked)'.", _score_date),
    BenchTask("extract_fee", 'Return JSON {"amount": number, "currency": "USD"} for: "The application fee is US$65."',
              _score_json_fee, json_mode=True),
    BenchTask("egyptian_rewrite", "أعد كتابة الجملة بالعامية المصرية الطبيعية: 'يرجى العلم بأن آخر موعد للتقديم هو 15 يناير.'",
              _score_dialect),
]


def run_model_benchmark(broker: ComputeBroker, out_path: Path, purpose: str = "research") -> dict:
    results: dict[str, dict] = {}
    for t in BENCH_TASKS:
        req = CapabilityRequest(task=f"bench.{t.task_id}", purpose=purpose)
        res = broker.complete(req, [ChatMessage("user", t.prompt)], json_mode=t.json_mode, max_tokens=300)
        results[t.task_id] = {
            "outcome": res.decision.outcome.value,
            "model": res.model_id,
            "score": t.scorer(res.text) if res.executed and res.text is not None else None,
            "status": "MEASURED" if res.executed else "NOT_MEASURED",
        }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results
