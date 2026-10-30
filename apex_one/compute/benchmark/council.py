"""Phase 15 — the real model council benchmark.

Every task has a deterministic, inspectable scorer and a ground truth computed in code (never "graded by vibes").
Results feed the CapabilityRouter: `artifacts/bench/council_scores.json` is overlaid onto the registry so routing
learns from MEASURED performance on APEX work, not from reputation.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

from bs4 import BeautifulSoup

from apex_one.compute.providers import ChatMessage
from apex_one.core.schemas.compute import CapabilityRequest

# --------------------------------------------------------------------------- ground truths
TODAY = date(2026, 10, 10)
DEADLINE = date(2026, 11, 1)
RESULT_DAYS = 10


def _latest_saturday() -> str:
    from apex_one.core.dates import latest_test_date

    return latest_test_date(DEADLINE, RESULT_DAYS, today=TODAY).isoformat()   # single source of truth


LATEST_SAT = _latest_saturday()

LONG_DOC_FACT = "The Labor Program supervisor must approve schedule changes by 20 January 2027."


def _long_doc() -> str:
    filler = ("Students participate in campus life, attend convocations, and join service projects that connect "
              "academic learning with community needs. Advising is available throughout the year. ")
    parts = [f"Section {i}. " + filler * 4 for i in range(1, 40)]
    parts.insert(27, "Section 27b. " + LONG_DOC_FACT + " " + filler)
    return "\n".join(parts)


@dataclass
class CouncilTask:
    name: str
    maps_to: list[str]                      # pipeline task names whose routing this benchmark informs
    build: Callable[[], list[ChatMessage]]
    score: Callable[[str], tuple[float, str]]
    json_mode: bool = False
    vision: bool = False
    max_tokens: int = 500


def _json(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(re.search(r"\{.*\}", text, re.S).group(0))  # type: ignore[union-attr]
    except Exception:
        return None


def s_reasoning(text: str) -> tuple[float, str]:
    d = _json(text) or {}
    return (100.0 if str(d.get("date")) == LATEST_SAT else 0.0), f"expected {LATEST_SAT}, got {d.get('date')}"


# Egyptian markers. Whole words only (prefix matching made «دي» hit «ديسمبر»); verb prefixes are matched only on
# words long enough to be inflected verbs.
DIALECT_WORDS = {"عشان", "علشان", "إزاي", "ازاي", "دلوقتي", "مش", "كده", "كدا", "يعني", "بتاع", "بتاعة", "بتاعك", "لسه",
                 "إنت", "انت", "انتي", "لازم", "تمام", "عايز", "عايزة", "عاوز", "ده", "دي", "دول", "بقى", "اللي", "فين",
                 "إمتى", "امتى", "ليه", "إيه", "ايه", "برضه", "أوي", "اوي", "خالص", "كمان", "يلا", "طب", "معلش", "خلي",
                 "خليك", "يخلص", "تخلص", "هتخلص", "بيقول", "هيقدم"}
VERB_PREFIXES = ("هت", "هي", "بت", "بي", "هن", "بن")
MSA = ["يرجى", "حيث أن", "حيث إن", "تجدر الإشارة", "الجدير بالذكر", "يتعين", "سوف"]
CHECKER_VERSION = 2
STORED_OUTPUT_CHARS = 1200


def s_egyptian(text: str) -> tuple[float, str]:
    bare = re.sub(r"[\u064B-\u0652\u0670\u0640]", "", text)   # drop diacritics/tatweel so «تذكّر» stays one word
    words = re.findall(r"[\u0621-\u064A\u0671-\u06D3]+", bare)   # letters only: «؟» / «،» are not part of words
    hits = sum(1 for w in words if w in DIALECT_WORDS or (len(w) >= 5 and w.startswith(VERB_PREFIXES)))
    msa = sum(1 for m in MSA if m in text)
    keeps = "15" in text or "١٥" in text
    score = min(100.0, hits * 25) - 30 * msa - (0 if keeps else 40)
    return max(0.0, score), f"dialect_markers={hits} msa={msa} number_kept={keeps}"


def s_mixing(text: str) -> tuple[float, str]:
    need = ["deadline", "deposit", "TOEFL"]
    present = [t for t in need if t.lower() in text.lower()]
    translit = any(x in text for x in ("ديدلاين", "ديبوزيت", "توفل"))
    arabic = len(re.findall(r"[؀-ۿ]+", text))
    score = 100.0 * len(present) / len(need) - (30 if translit else 0) - (0 if arabic >= 8 else 40)
    return max(0.0, score), f"latin_terms={present} transliterated={translit} arabic_words={arabic}"


EXTRACT_TEXT = ("Applicants from Egypt may apply. The international application deadline is February 1, 2027. "
                "The enrollment deposit is $200, refundable until May 1, 2027. A minimum IELTS score of 7.0 is required.")
EXTRACT_TRUTH = {"deadline": "2027-02-01", "deposit_usd": 200.0, "ielts_min": 7.0, "deposit_refund_until": "2027-05-01"}


def s_extract(text: str) -> tuple[float, str]:
    d = _json(text) or {}
    ok = 0
    for k, v in EXTRACT_TRUTH.items():
        try:
            ok += int(float(d.get(k)) == v) if isinstance(v, float) else int(str(d.get(k)) == v)
        except (TypeError, ValueError):
            pass
    return 100.0 * ok / len(EXTRACT_TRUTH), f"{ok}/{len(EXTRACT_TRUTH)} fields exact"


def s_fact_preservation(text: str) -> tuple[float, str]:
    from apex_one.research.evidence.normalize import find_dates, find_money, to_ascii_digits

    t = to_ascii_digits(text)
    dates = {d.isoformat() for d, *_ in find_dates(t)}
    money = {(c, a) for a, c, *_ in find_money(t)}
    ok_date = "2026-11-01" in dates and dates <= {"2026-11-01"}
    if not ok_date and "نوفمبر" in t and "2026" in t:
        return 50.0 * ok_date + 50.0 * (("USD", 50.0) in money and money <= {("USD", 50.0)}), (
            f"date reworded (not kept exactly as instructed); dates={sorted(dates)} money={sorted(money)}")
    ok_money = ("USD", 50.0) in money and money <= {("USD", 50.0)}
    return 50.0 * ok_date + 50.0 * ok_money, f"dates={sorted(dates)} money={sorted(money)}"


def s_html(text: str) -> tuple[float, str]:
    m = re.search(r"<section.*?</section>", text, re.S | re.I)
    if not m:
        return 0.0, "no <section>"
    soup = BeautifulSoup(m.group(0), "lxml")
    sec = soup.find("section")
    checks = {
        "rtl": (sec.get("dir") == "rtl") or "direction:rtl" in m.group(0).replace(" ", ""),
        "h2": soup.find("h2") is not None,
        "p": soup.find("p") is not None,
        "no_script": soup.find("script") is None,
        "no_gradient": "gradient" not in m.group(0).lower(),
        "bdi_or_ltr": soup.find("bdi") is not None or 'dir="ltr"' in m.group(0),
    }
    return 100.0 * sum(checks.values()) / len(checks), json.dumps(checks)


def s_critique(text: str) -> tuple[float, str]:
    low = text.lower()
    found = {"hierarchy": bool(re.search(r"hierarch|heading.*(same|equal|small)|size", low)),
             "contrast": "contrast" in low,
             "line_length": bool(re.search(r"line length|measure|characters per line|too wide", low)),
             "cards": bool(re.search(r"card", low))}
    return 100.0 * sum(found.values()) / len(found), json.dumps(found)


def s_long(text: str) -> tuple[float, str]:
    d = _json(text) or {}
    return (100.0 if str(d.get("date")) == "2027-01-20" else 0.0), f"got {d.get('date')}"


def _facts(text: str) -> tuple[set[str], set[tuple[str, float]], list[str]]:
    from apex_one.research.evidence.normalize import find_dates, find_money, to_ascii_digits

    t = to_ascii_digits(text)
    return ({d.isoformat() for d, *_ in find_dates(t)}, {(c, a) for a, c, *_ in find_money(t)},
            re.findall(r"\d+(?:\.\d+)?", t))


def s_english_writing(text: str) -> tuple[float, str]:
    """Plain-English factual rewrite: both facts kept exactly, no invented numbers, English, short (5 checks)."""
    dates, money, nums = _facts(text)
    latin = len(re.findall(r"[A-Za-z]", text))
    arabic = len(re.findall(r"[\u0600-\u06FF]", text))
    sentences = [x for x in re.split(r"(?<=[.!?])\s+", text.strip()) if x.strip()]
    checks = {"date_kept": "2026-11-01" in dates and dates <= {"2026-11-01"},
              "amount_kept": ("USD", 50.0) in money and money <= {("USD", 50.0)},
              "no_new_numbers": set(nums) <= {"1", "2026", "50", "50.00", "16"},
              "english": latin > 0 and arabic == 0,
              "short": 1 <= len(sentences) <= 3}
    if not checks["english"]:          # the wrong language fails the task outright, whatever else is right
        return 0.0, json.dumps(checks)
    return 100.0 * sum(checks.values()) / len(checks), json.dumps(checks)


def s_structured_editorial(text: str) -> tuple[float, str]:
    """Structured editorial writing: exactly three Markdown bullets carrying the three facts, nothing else (5 checks)."""
    lines = [x.strip() for x in text.strip().strip("`").splitlines() if x.strip() and x.strip() != "markdown"]
    bullets = [x for x in lines if re.match(r"^[-*] \S", x)]
    dates, money, nums = _facts(text)
    checks = {"three_bullets": len(bullets) == 3,
              "only_bullets": len(lines) == len(bullets),
              "date_kept": "2026-11-01" in dates and dates <= {"2026-11-01"},
              "amount_kept": ("USD", 50.0) in money and money <= {("USD", 50.0)},
              "ielts_kept_no_new_numbers": "6.5" in nums and set(nums) <= {"1", "2026", "50", "6.5"}}
    return 100.0 * sum(checks.values()) / len(checks), json.dumps(checks)


def tasks(calib_dir: Path | None = None) -> list[CouncilTask]:
    out = [
        CouncilTask("reasoning", ["mission.analyze", "opportunity.model"], lambda: [ChatMessage("user",
            f"Today is {TODAY.isoformat()}. The application deadline is {DEADLINE.isoformat()}. English test results "
            f"take {RESULT_DAYS} days to reach the college and must arrive on or before the deadline. Tests run only on "
            "Saturdays. What is the LATEST Saturday the student can take the test? Think carefully, then return ONLY "
            'JSON {"date": "YYYY-MM-DD"}.')], s_reasoning, json_mode=True, max_tokens=900),
        CouncilTask("egyptian_arabic", ["editorial.write", "editorial.critique"], lambda: [ChatMessage("user",
            "أعد كتابة الجملة دي بالعامية المصرية الطبيعية لطالب عنده 16 سنة، من غير ما تغيّر الرقم: "
            "'يرجى العلم بأنه يتعين على الطالب تقديم الأوراق قبل يوم 15 من الشهر.' اكتب الجملة بس.")], s_egyptian),
        CouncilTask("en_ar_mixing", ["editorial.write"], lambda: [ChatMessage("user",
            "اكتب جملتين بالعامية المصرية لطالب عن التحضير للتقديم، واستخدم الكلمات الإنجليزية deadline و deposit و "
            "TOEFL زي ما هي بالحروف الإنجليزية (متكتبهاش بالعربي).")], s_mixing),
        CouncilTask("structured_json", ["evidence.extract", "live.structured"], lambda: [ChatMessage("user",
            f"Extract facts from: \"{EXTRACT_TEXT}\" Return ONLY JSON with keys deadline (YYYY-MM-DD), deposit_usd "
            "(number), ielts_min (number), deposit_refund_until (YYYY-MM-DD).")], s_extract, json_mode=True),
        CouncilTask("fact_preservation", ["editorial.write"], lambda: [ChatMessage("user",
            "أعد صياغة الفقرة دي بالعامية المصرية بأسلوب أخف، وحافظ على التاريخ والمبلغ زي ما هما بالظبط ومتضيفش أي أرقام "
            "جديدة: 'آخر موعد للتقديم هو 1 نوفمبر 2026، ورسوم تأكيد المكان $50.'")], s_fact_preservation),
        CouncilTask("english_factual_writing", [], lambda: [ChatMessage("user",
            "Rewrite this for a 16-year-old student in plain, friendly English, in at most two sentences. Keep the date "
            "and the amount exactly and add no new numbers: 'Applicants are hereby notified that the application "
            "deadline is 1 November 2026 and that an enrolment deposit of USD 50 is payable.' Return only the "
            "rewritten text.")], s_english_writing),
        CouncilTask("structured_editorial", [], lambda: [ChatMessage("user",
            "Write a checklist for a student as exactly three Markdown bullet items ('- '), one short imperative "
            "sentence each, in English: submit the application before 1 November 2026; pay the USD 50 deposit; take "
            "IELTS and score at least 6.5. Keep the numbers exactly and add no others. Return only the list.")],
            s_structured_editorial),
        CouncilTask("html_css", ["design.html"], lambda: [ChatMessage("user",
            "Write ONE HTML <section> (no <script>, no gradients) for an Arabic right-to-left guide page: dir=\"rtl\", "
            "an <h2> heading, one <p> paragraph in Arabic, and wrap the English word deadline in <bdi dir=\"ltr\">. "
            "Return only the HTML.")], s_html, max_tokens=700),
        CouncilTask("design_criticism", ["design.reward"], lambda: [ChatMessage("user",
            "A rendered A4 page measures: heading 16px, body 16px, body text color #C9D0DA on white (contrast 1.6:1), "
            "average 140 characters per line, 9 rounded bordered cards with drop shadows. As a strict editorial art "
            "director, list the problems and the fixes in English.")], s_critique, max_tokens=600),
        CouncilTask("long_context", ["evidence.extract"], lambda: [ChatMessage("user",
            _long_doc() + "\n\nQuestion: by which date must the Labor Program supervisor approve schedule changes? "
            'Return ONLY JSON {"date": "YYYY-MM-DD"}.')], s_long, json_mode=True, max_tokens=300),
    ]
    if calib_dir is not None and (calib_dir / "good-01.png").exists():
        out.append(CouncilTask("visual_hierarchy", ["vision.council", "vision.judge"], lambda: [], lambda t: (0.0, ""),
                               vision=True))
    return out


def _pairwise_hierarchy(broker, model_id: str, calib_dir: Path, ws=None) -> tuple[float | None, str]:
    """PosterReward-style pairwise protocol: ask twice with swapped order; count only consistent correct answers."""
    from apex_one.vision.council import encode_png

    good, bad = encode_png(calib_dir / "good-01.png", 640), encode_png(calib_dir / "no_hierarchy-01.png", 640)
    answers = []
    for first, second, correct in ((good, bad, "A"), (bad, good, "B")):
        req = CapabilityRequest(task="bench.visual_hierarchy", vision=True, purpose="evaluation", model_id=model_id)
        res = broker.complete(req, [ChatMessage("user", "Image A is first, image B is second. Which page has the "
                                                        "clearer visual hierarchy (one obvious entry point, clear size "
                                                        'contrast)? Return ONLY JSON {"winner": "A" or "B"}.',
                                                images_b64_png=[first, second])],
                              json_mode=True, max_tokens=60, temperature=0.0, timeout=900)
        if not res.executed:
            fk = call_failure_kind(res)
            return None, f"ERROR {fk}" if fk else "no route"
        w = str((_json(res.text or "") or {}).get("winner", "")).upper()[:1]
        answers.append(w == correct)
    return (100.0 if all(answers) else 50.0 if any(answers) else 0.0), f"order-swapped answers correct={answers}"


def call_failure_kind(res) -> str | None:
    """FailureKind of the last failed attempt of a broker call (None when no attempt was made)."""
    calls = getattr(res, "calls", None) or []
    return next((c.failure_kind or "UNKNOWN_FAILURE" for c in reversed(calls) if c.outcome != "ok"), None)


def sample_state(score: float | None, failure_kind: str | None, floor: float) -> str:
    """PASSED / FAILED only for a real measurement; a failed call is ERROR, a call never made is SKIPPED."""
    if score is None:
        return "ERROR" if failure_kind else "SKIPPED"
    return "PASSED" if score >= floor else "FAILED"


def run_council(broker, model_ids: list[str], out_dir: Path, calib_dir: Path | None = None,
                only: list[str] | None = None, max_tokens: int | None = None, timeout: float = 900) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    scores_path = out_dir / "council_scores.json"
    data = json.loads(scores_path.read_text(encoding="utf-8")) if scores_path.exists() else {"models": {}, "runs": []}
    log = (out_dir / "council_runs.jsonl").open("a", encoding="utf-8")
    from apex_one.compute.router.capability import routing_config

    floor = float(routing_config().get("default_min_score", 50))
    for mid in model_ids:
        entry = data["models"].setdefault(mid, {})
        for t in tasks(calib_dir):
            if only and t.name not in only:
                continue
            t0 = time.perf_counter()
            fk = None
            if t.vision:
                score, detail = _pairwise_hierarchy(broker, mid, calib_dir)  # type: ignore[arg-type]
                fk = detail.split(" ", 1)[1] if detail.startswith("ERROR ") else None
                text = ""
            else:
                req = CapabilityRequest(task=f"bench.{t.name}", purpose="evaluation", model_id=mid)
                res = broker.complete(req, t.build(), json_mode=t.json_mode, max_tokens=max_tokens or t.max_tokens,
                                      temperature=0.0, timeout=timeout)
                text = res.text or ""
                if not res.executed:
                    fk = call_failure_kind(res)
                    score, detail = None, f"not executed: {res.decision.outcome.value}" + (f" ({fk})" if fk else "")
                elif not text.strip():
                    # reasoning models can spend the whole budget on hidden reasoning: NOT a wrong answer
                    score, detail = None, f"empty output at max_tokens={max_tokens or t.max_tokens} (NOT_MEASURED)"
                    fk = "EMPTY_OUTPUT"
                else:
                    score, detail = t.score(text)
            rec = {"model": mid, "task": t.name, "score": score, "state": sample_state(score, fk, floor),
                   "failure_kind": fk, "detail": detail, "latency_s": round(time.perf_counter() - t0, 1),
                   "max_tokens": None if t.vision else (max_tokens or t.max_tokens), "checker_version": CHECKER_VERSION,
                   "output": text[:STORED_OUTPUT_CHARS]}
            log.write(json.dumps(rec, ensure_ascii=False) + "\n")
            log.flush()
            if score is not None:
                entry[t.name] = score
    scores_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return rescore(out_dir)     # one aggregation path (capabilities = min of their measured tasks)


def rescore(out_dir: Path) -> dict[str, Any]:
    """Re-apply the CURRENT deterministic checkers to stored outputs (no re-inference) and rebuild the scores.
    Vision pairwise rows carry no text output and keep their measured score."""
    runs_path, scores_path = out_dir / "council_runs.jsonl", out_dir / "council_scores.json"
    rows = [json.loads(x) for x in runs_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    by_name = {t.name: t for t in tasks(None)}
    data = {"models": {}, "checker_version": CHECKER_VERSION,
            "note": "scores recomputed from stored outputs with the current checkers"}
    for r in rows:   # later runs of the same (model, task) win
        t = by_name.get(r["task"])
        score = r["score"]
        complete = len(r.get("output", "")) < STORED_OUTPUT_CHARS     # truncated outputs keep their live score
        if t is not None and not t.vision and r.get("output", "").strip() and score is not None and complete:
            score, r["detail"] = t.score(r["output"])
        elif t is not None and not t.vision and not r.get("output", "").strip():
            score = None                      # empty output: not measured (see run_council)
        entry = data["models"].setdefault(r["model"], {})
        if score is not None:
            entry[r["task"]] = score
    names = {t.name for t in tasks(Path("."))}
    alias = {t.name: t.maps_to for t in tasks(Path("."))}
    for entry in data["models"].values():
        # a capability fed by several measured tasks is only as good as its weakest one (min, never max):
        # editorial.write must not read 100 because fact preservation passed while Egyptian Arabic failed
        cap: dict[str, list[float]] = {}
        for name, maps in alias.items():
            if name in entry:
                for a in maps:
                    cap.setdefault(a, []).append(entry[name])
        for a, vals in cap.items():
            entry[a] = min(vals)
        # no cross-task "overall" is stored: models are measured on different task sets and an average would
        # hide a 0 (e.g. Egyptian Arabic) behind unrelated 100s
        entry["measured_tasks"] = len([k for k in entry if k in names])
    scores_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data
