"""Rule-based evidence extraction (native, deterministic) + quote-verified model extraction.

Every Claim carries Evidence with the exact quote and a locator. Model-extracted claims are kept
ONLY if their quote literally occurs in the parsed source (anti-hallucination).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from apex_one.core.schemas.evidence import (
    CRITICAL_PREDICATES,
    Claim,
    Criticality,
    Evidence,
    NormalizedValue,
    Source,
)
from apex_one.research.documents.parsers import ParsedDocument
from apex_one.research.evidence.normalize import (
    bool_value,
    date_value,
    find_dates,
    find_money,
    find_percents,
    money_value,
    number_value,
    percent_value,
    text_value,
    to_ascii_digits,
)

SENT_SPLIT = re.compile(r"(?<=[.!?؟])\s+(?=[A-Z؀-ۿ0-9\"'(])")
DEADLINE_KW = re.compile(r"\b(deadline|due|apply by|submit(?:ted)? by|must be (?:received|submitted)|postmarked|"
                         r"closes?|no later than)\b|آخر موعد|موعد التقديم", re.I)
NOTIFY_KW = re.compile(r"\b(notif(?:y|ied|ication)|decisions? (?:are |will be )?released)\b", re.I)
DOMESTIC_KW = re.compile(r"\b(domestic|u\.s\. citizens|us citizens|permanent residents)\b", re.I)
HEDGE_KW = re.compile(r"\b(subject to change|tentative|tba|to be announced|estimated|approximately|may change)\b", re.I)

REQUIREMENT_ITEMS = {
    "transcripts": re.compile(r"transcript", re.I),
    "recommendation_letters": re.compile(r"recommendation|reference letter", re.I),
    "essay": re.compile(r"\bessay|personal statement", re.I),
    "financial_statement": re.compile(r"financial statement|bank statement|proof of (?:funds|finances)", re.I),
    "passport": re.compile(r"passport", re.I),
    "application_form": re.compile(r"application form|common app|online application", re.I),
    "interview": re.compile(r"interview", re.I),
    "english_test_scores": re.compile(r"english (?:proficiency|test) scores?|toefl|ielts|duolingo", re.I),
}
COUNT_RX = {
    "recommendation_letters": re.compile(r"\b(one|two|three|four|\d)\s+(?:\w+\s+)?(?:recommendation letters?|letters? of "
                                         r"recommendation|recommendations?|reference letters?)"),
    "essay": re.compile(r"\b(one|two|three|\d)\s+(?:\w+\s+)?(?:essays?|personal statements?)"),
}
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
TEST_RX = {
    "toefl_ibt": re.compile(r"TOEFL(?:\s*iBT)?[^.\d]{0,40}?(\d{2,3})\b", re.I),
    "ielts": re.compile(r"IELTS[^.\d]{0,40}?(\d(?:\.\d)?)\b", re.I),
    "duolingo": re.compile(r"Duolingo(?: English Test)?[^.\d]{0,40}?(\d{2,3})\b", re.I),
    "sat": re.compile(r"\bSAT\b[^.\d]{0,30}?(\d{3,4})\b"),
}


@dataclass
class Extraction:
    claims: list[Claim] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)

    def extend(self, other: "Extraction") -> None:
        self.claims += other.claims
        self.evidence += other.evidence


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT_SPLIT.split(text) if s.strip()]


def _crit(predicate: str) -> Criticality:
    return Criticality.CRITICAL if predicate in CRITICAL_PREDICATES else Criticality.IMPORTANT


class RuleEvidenceExtractor:
    """Deterministic extractor for decision-critical predicates."""

    name = "rule-v1"

    def __init__(self, subject: str):
        self.subject = subject

    def extract(self, source: Source, doc: ParsedDocument) -> Extraction:
        out = Extraction()
        for block in doc.blocks:
            if block.tag in ("h1", "h2", "h3", "h4"):
                continue
            for sent in sentences(block.text):
                for predicate, qualifier, value in self._rules(sent, block.locator):
                    ev = Evidence(source_id=source.source_id, quote=sent[:600], locator=block.locator,
                                  extractor=self.name)
                    claim = Claim(subject=self.subject, predicate=predicate, qualifier=qualifier, value=value,
                                  criticality=_crit(predicate), evidence_ids=[ev.evidence_id],
                                  source_ids=[source.source_id], confidence=0.6)
                    if HEDGE_KW.search(sent):
                        claim.notes.append("hedged language in source (subject to change/tentative/estimated)")
                    out.claims.append(claim)
                    out.evidence.append(ev)
        return out

    # -------------------------------------------------------------------------------------------
    def _rules(self, s: str, locator: str) -> list[tuple[str, str, NormalizedValue]]:
        found: list[tuple[str, str, NormalizedValue]] = []
        low = to_ascii_digits(s).lower()
        scope = "domestic" if DOMESTIC_KW.search(s) else ""

        def q(*parts: str) -> str:
            return " ".join(p for p in (*parts, scope) if p)

        # ---- dates: deadlines & notifications
        dates = find_dates(s)
        if dates and (DEADLINE_KW.search(s) or NOTIFY_KW.search(s)):
            if NOTIFY_KW.search(s) and not DEADLINE_KW.search(s):
                kind, pred = "decision", "decision_date"
            elif re.search(r"deposit", low):
                kind, pred = "enrollment deposit", "deadline"
            elif re.search(r"financial (?:statement|aid|documents)|css profile|bank statement", low):
                kind, pred = "financial documents", "deadline"
            elif re.search(r"scholarship", low) and "application" not in low:
                kind, pred = "scholarship", "deadline"
            elif re.search(r"early (?:decision|action)", low):
                kind, pred = "early application", "deadline"
            else:
                kind, pred = "application", "deadline"
            d, raw, _ = dates[0]
            found.append((pred, q(kind), date_value(d, raw)))

        # ---- money
        money = find_money(s)
        if re.search(r"no application fee|application fee (?:is )?waived for all|free to apply|"
                     r"there is no (?:fee|charge) to apply", low):
            found.append(("fee", q("application"), money_value(0, "USD", "no application fee")))
        for amt, cur, raw, pos in money:
            ctx = low[max(0, pos - 90): pos + 60]
            if "application fee" in ctx:
                found.append(("fee", q("application"), money_value(amt, cur, raw)))
            elif "deposit" in ctx:
                found.append(("deposit", q("enrollment"), money_value(amt, cur, raw)))
            elif re.search(r"student contribution|contribute|you (?:will )?pay|out[- ]of[- ]pocket|remaining cost", ctx):
                qual = "student contribution per year" if re.search(r"per year|annual|each year|a year", ctx) \
                    else "student contribution"
                found.append(("funding", q(qual), money_value(amt, cur, raw)))
            elif "room and board" in ctx or "housing and meals" in ctx:
                found.append(("fee", q("room and board"), money_value(amt, cur, raw)))
            elif "health insurance" in ctx:
                found.append(("fee", q("health insurance"), money_value(amt, cur, raw)))
            elif "tuition" in ctx and not re.search(r"cover|scholarship|free|promise", ctx):
                found.append(("fee", q("tuition"), money_value(amt, cur, raw)))

        # ---- funding coverage
        if re.search(r"tuition", low) and re.search(r"cover|full|free|no tuition|promise|scholarship", low):
            pcts = find_percents(s)
            if pcts:
                found.append(("scholarship_coverage", q("tuition"), percent_value(pcts[0][0], pcts[0][1])))
            elif re.search(r"full(?:y)? (?:cover|tuition)|no tuition|tuition[- ]free|covers? (?:the )?full", low):
                found.append(("scholarship_coverage", q("tuition"), percent_value(100, "full tuition")))
        if re.search(r"need[- ]based", low) and re.search(r"aid|scholarship|funding", low):
            found.append(("funding", q("aid type"), text_value("need-based")))

        # ---- tests
        if re.search(r"test[- ]optional|not required to submit (?:the )?(?:sat|act)|(?:sat|act)[^.]{0,30}(?:not required|optional)", low):
            found.append(("test_requirement", q("sat act"), bool_value(False, "test-optional")))
        elif re.search(r"\b(sat|act)\b[^.]{0,40}\brequired\b", low) and "not required" not in low:
            found.append(("test_requirement", q("sat act"), bool_value(True, "SAT/ACT required")))
        for test, rx in TEST_RX.items():
            m = rx.search(to_ascii_digits(s))
            if m and re.search(r"minimum|at least|required|score of|or higher|or above|need", low):
                found.append(("test_minimum", q(test.replace("_", " ")), number_value(float(m.group(1)), m.group(0))))

        # ---- eligibility
        if re.search(r"open to (?:all )?international|students from (?:all|any) countr|all nationalities|"
                     r"regardless of (?:citizenship|nationality)", low):
            found.append(("country_eligibility", q("international"), text_value("open to all countries")))
        m = re.search(r"citizens of ([A-Z][^.,;]+)", s)
        if m and "eligib" in low:
            found.append(("country_eligibility", q("citizenship"), text_value(m.group(1))))
        if re.search(r"must (?:have )?(?:graduat|complet|finish)\w* (?:from )?(?:secondary|high) school", low) or \
                re.search(r"complet\w* (?:secondary|high) school by", low):
            found.append(("eligibility", q("academic"), text_value(s)))
        if re.search(r"demonstrat\w* (?:financial )?need|family income", low) and \
                re.search(r"must|eligib|require|only", low):
            found.append(("eligibility", q("financial need"), text_value("must demonstrate financial need")))
        m = re.search(r"\bages? (\d{2})\s*(?:-|to|–)\s*(\d{2})", low)
        if m:
            found.append(("age", q("range"), text_value(f"{m.group(1)}-{m.group(2)}")))
        m = re.search(r"\bgrades? (\d{1,2})\s*(?:-|to|–|and)\s*(\d{1,2})", low)
        if m and re.search(r"eligib|open to|must", low):
            found.append(("grade", q("range"), text_value(f"{m.group(1)}-{m.group(2)}")))

        # ---- requirements (one claim per required item)
        if re.search(r"requir|submit|must (?:send|provide|include)|you will need|checklist", low) or \
                re.search(r"requirement|checklist|documents", locator, re.I):
            for key, rx in REQUIREMENT_ITEMS.items():
                if rx.search(s):
                    count_rx = COUNT_RX.get(key)
                    cnt = count_rx.search(low) if count_rx else None
                    if cnt:
                        tok = cnt.group(1)
                        n = WORDNUM.get(tok) or (int(tok) if tok.isdigit() else None)
                        if n:
                            found.append(("application_requirement", key.replace("_", " "), number_value(n, cnt.group(0))))
                            continue
                    found.append(("application_requirement", key.replace("_", " "), bool_value(True, s[:120])))

        # ---- visa / logistics
        if re.search(r"\bi-20\b|\bf-1\b|student visa|visa interview", low):
            if re.search(r"i-20", low) and re.search(r"after|once|upon", low):
                found.append(("visa_logistics", q("i20 timing"), text_value(s)))
            elif re.search(r"f-1", low):
                found.append(("visa_logistics", q("visa type"), text_value("F-1 student visa")))

        # ---- work programme (hidden value / obligation)
        m = re.search(r"(\d{1,2})\s*(?:to\s*\d{1,2}\s*)?hours (?:per|a|each) week", low)
        if m and re.search(r"work|labor|job|employment", low):
            found.append(("work_requirement", q("hours per week"), number_value(float(m.group(1)), m.group(0))))
        return found


class ModelEvidenceExtractor:
    """Uses the ComputeBroker (if a $0 route exists). Quotes must exist verbatim in the source."""

    PROMPT = (
        "Extract decision-critical facts for an opportunity guide from the SOURCE TEXT. Return JSON "
        '{"claims":[{"predicate":one of [deadline,fee,deposit,funding,scholarship_coverage,test_minimum,'
        'test_requirement,eligibility,country_eligibility,age,grade,application_requirement,visa_logistics],'
        '"qualifier":"short scope","value":"exact value","quote":"EXACT sentence copied from the source"}]}. '
        "Never infer. Never paraphrase quotes."
    )

    def __init__(self, broker, subject: str, purpose: str = "production"):
        self.broker = broker
        self.subject = subject
        self.purpose = purpose

    def extract(self, source: Source, doc: ParsedDocument, workspace=None) -> tuple[Extraction, str | None]:
        from apex_one.compute.providers import ChatMessage
        from apex_one.core.schemas.compute import CapabilityRequest, Level

        req = CapabilityRequest(task="evidence.extract", min_reasoning=Level.MEDIUM, structured_output=True,
                                purpose=self.purpose)
        text = doc.text[:12000]
        res = self.broker.complete(req, [ChatMessage("system", self.PROMPT), ChatMessage("user", text)],
                                   json_mode=True, workspace=workspace, max_tokens=1500)
        out = Extraction()
        if not res.executed or not res.text:
            return out, None
        try:
            data = json.loads(re.search(r"\{.*\}", res.text, re.S).group(0))  # type: ignore[union-attr]
        except Exception:
            return out, res.model_id
        haystack = re.sub(r"\s+", " ", doc.text)
        for c in data.get("claims", [])[:80]:
            quote = re.sub(r"\s+", " ", str(c.get("quote", ""))).strip()
            if len(quote) < 12 or quote not in haystack:
                continue  # hallucinated or paraphrased quote => dropped
            sub = RuleEvidenceExtractor(self.subject)._rules(quote, "model")
            for predicate, qualifier, value in sub:
                ev = Evidence(source_id=source.source_id, quote=quote, locator="model-located",
                              extractor=f"model:{res.model_id}")
                out.evidence.append(ev)
                out.claims.append(Claim(subject=self.subject, predicate=predicate, qualifier=qualifier, value=value,
                                        criticality=_crit(predicate), evidence_ids=[ev.evidence_id],
                                        source_ids=[source.source_id], confidence=0.55))
        return out, res.model_id
