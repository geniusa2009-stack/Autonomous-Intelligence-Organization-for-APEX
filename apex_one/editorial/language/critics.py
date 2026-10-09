"""Editorial critics: NaturalnessCritic, EgyptianDialectCritic, JakeController, HumorController,
BilingualEditor, CompressionEditor, ClaimLanguageGuard, FactAlignmentEditor.

These are deterministic rule critics. Their combined score is reported as a deterministic proxy for
editorial quality; human or model judgement of style is a separate metric that stays NOT_MEASURED
unless a real judge ran.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from apex_one.core.schemas.common import Metric
from apex_one.core.schemas.document import DocNode, DocumentAST, NodeType
from apex_one.core.schemas.evidence import FactLock
from apex_one.core.schemas.quality import QAIssue
from apex_one.document.ast.runs import runs_text
from apex_one.editorial.fact_guard.semantic_diff import semantic_diff
from apex_one.editorial.voice.genome import VoiceGenome

AR_WORD = re.compile(r"[؀-ۿ]+")
EN_WORD = re.compile(r"[A-Za-z][A-Za-z\-']+")
NARRATIVE = {NodeType.OPENING, NodeType.APEX_TAKE, NodeType.CLOSING, NodeType.BREATH}
CERTAINTY = ["مضمون", "أكيد هتتقبل", "100% هتتقبل", "guaranteed", "you will be accepted"]


@dataclass
class EditorialReview:
    issues: list[QAIssue] = field(default_factory=list)
    metrics: dict[str, Metric] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return any(i.severity in ("critical", "major") for i in self.issues)


def node_texts(node: DocNode, types: tuple[str, ...] = ("text", "term")) -> list[tuple[str, str]]:
    out = []
    for b in node.content:
        txt = "".join(r.text for r in b.runs if r.kind in types)
        if txt.strip():
            out.append((b.role, txt))
    return out


def review_document(ast: DocumentAST, voice: VoiceGenome, locks: list[FactLock],
                    allowed_years: set[int] | None = None) -> EditorialReview:
    rules = voice.rules
    rv = EditorialReview()
    nodes = ast.pages()

    # --- NaturalnessCritic: clichés, rejected phrases, repeated openings
    cliches = rules.get("ai_cliches_ar", []) + rules.get("ai_cliches_en", []) + voice.rejected + voice.learned_rejections
    cliche_hits = 0
    openings: dict[str, int] = {}
    for n in nodes:
        for role, txt in node_texts(n):
            for c in cliches:
                if c.lower() in txt.lower():
                    cliche_hits += 1
                    rv.issues.append(QAIssue(check="voice.no_ai_cliches", severity="major", page=n.node_id,
                                             message=f"cliché/rejected phrase: {c}"))
            if role == "paragraph":
                first = " ".join(txt.split()[:2])
                openings[first] = openings.get(first, 0) + 1
    repeats = sum(v - 1 for v in openings.values() if v > 1)

    # --- EgyptianDialectCritic + bureaucratic MSA
    markers = rules.get("dialect_markers", [])
    bureaucratic = rules.get("bureaucratic_msa_markers", [])
    narrative_words = narrative_markers = msa_hits = 0
    for n in nodes:
        for _, txt in node_texts(n):
            words = AR_WORD.findall(txt)
            if n.semantic_type in NARRATIVE:
                narrative_words += len(words)
                narrative_markers += sum(1 for w in words if any(w.startswith(m.rstrip("ـ")) for m in markers))
            for b in bureaucratic:
                if b in txt:
                    msa_hits += 1
                    rv.issues.append(QAIssue(check="voice.no_bureaucratic_msa", severity="major", page=n.node_id,
                                             message=f"bureaucratic MSA: {b}"))
    ratio = narrative_markers / narrative_words if narrative_words else 0.0
    if narrative_words and ratio < rules.get("limits", {}).get("min_dialect_marker_ratio", 0.04):
        rv.issues.append(QAIssue(check="voice.egyptian_dialect", severity="major",
                                 message=f"dialect marker ratio {ratio:.3f} too low (reads like MSA)"))

    # --- JakeController
    jake = rules.get("jake", {})
    phrase = jake.get("phrase", "يا جيك")
    positions = [i for i, n in enumerate(nodes) for _, t in node_texts(n) if phrase in t]
    if len(positions) > jake.get("max_per_document", 3):
        rv.issues.append(QAIssue(check="voice.jake_frequency", severity="major",
                                 message=f"'{phrase}' used {len(positions)} times"))
    for a, b in zip(positions, positions[1:]):
        if b - a < jake.get("min_sections_between", 3):
            rv.issues.append(QAIssue(check="voice.jake_frequency", severity="minor",
                                     message=f"'{phrase}' repeated within {b - a} sections"))
    for i in positions:
        if nodes[i].semantic_type.value in jake.get("forbidden_in", []):
            rv.issues.append(QAIssue(check="voice.jake_frequency", severity="major", page=nodes[i].node_id,
                                     message=f"'{phrase}' in forbidden section {nodes[i].semantic_type}"))

    # --- HumorController
    humor = rules.get("humor", {})
    humor_blocks = [(n, b) for n in nodes for b in n.content if b.data.get("humor")]
    for n, _ in humor_blocks:
        if n.semantic_type.value in humor.get("forbidden_in", []):
            rv.issues.append(QAIssue(check="voice.humor_placement", severity="critical", page=n.node_id,
                                     message=f"humor inside {n.semantic_type}"))
    if len(humor_blocks) > humor.get("max_per_document", 3):
        rv.issues.append(QAIssue(check="voice.humor_placement", severity="minor", message="too much humor"))

    # --- BilingualEditor + CompressionEditor
    lim = rules.get("limits", {})
    long_sent = 0
    for n in nodes:
        for role, txt in node_texts(n):
            ar, en = len(AR_WORD.findall(txt)), len(EN_WORD.findall(txt))
            if ar and en / (ar + en) > lim.get("max_english_word_ratio", 0.22) and role in ("paragraph", "lead"):
                rv.issues.append(QAIssue(check="voice.bilingual_balance", severity="minor", page=n.node_id,
                                         message=f"English ratio {en / (ar + en):.2f} in {role}"))
            for s in re.split(r"[.!?؟]", txt):
                if len(s.split()) > lim.get("max_sentence_words_ar", 28):
                    long_sent += 1
                    rv.issues.append(QAIssue(check="voice.sentence_compression", severity="minor", page=n.node_id,
                                             message=f"sentence of {len(s.split())} words"))
        # unisolated Latin inside Arabic text runs
        for b in n.content:
            for r in b.runs:
                if r.kind == "text" and r.lang == "ar" and EN_WORD.search(r.text):
                    rv.issues.append(QAIssue(check="draft.bilingual_terms_isolated", severity="minor", page=n.node_id,
                                             message=f"Latin text inside Arabic run (compiler will isolate): {r.text[:40]}"))

    # --- ClaimLanguageGuard: hedges and certainty words
    hedged = {lk.slot for lk in locks if lk.hedge}
    for n in nodes:
        for b in n.content:
            full = runs_text(b.runs)
            for c in CERTAINTY:
                if c.lower() in full.lower():
                    rv.issues.append(QAIssue(check="claim_language.certainty", severity="critical", page=n.node_id,
                                             message=f"certainty language near facts: {c}"))
            for r in b.runs:
                if r.slot in hedged and not re.search(r"حوالي|تقريب|estimated|about|تقديري", full):
                    rv.issues.append(QAIssue(check="claim_language.hedge_missing", severity="critical", page=n.node_id,
                                             message=f"{r.slot} is hedged in the source but presented as exact"))

    # --- FactAlignmentEditor: semantic diff over the fully rendered text
    fact_violations = 0
    for n in nodes:
        for b in n.content:
            for v in semantic_diff(runs_text(b.runs), locks, allowed_years=allowed_years or set()):
                fact_violations += 1
                rv.issues.append(QAIssue(check="alignment.semantic_diff_clean", severity="critical", page=n.node_id,
                                         message=v.message, data={"raw": v.raw, "kind": v.kind}))

    # --- metrics (deterministic proxy)
    penalty = (8 * cliche_hits + 10 * msa_hits + 3 * repeats + 1.5 * long_sent
               + 10 * sum(1 for i in rv.issues if i.check in ("voice.jake_frequency", "voice.humor_placement")
                          and i.severity != "minor")
               + (15 if narrative_words and ratio < lim.get("min_dialect_marker_ratio", 0.04) else 0))
    rv.metrics["editorial.quality"] = Metric.measured(
        "editorial.quality", max(0.0, 100 - penalty),
        method="deterministic critic proxy (clichés, MSA markers, dialect ratio, Jake/humor rules, compression)",
        evidence=[f"dialect_ratio={ratio:.3f}", f"cliches={cliche_hits}", f"msa={msa_hits}", f"long={long_sent}"])
    rv.metrics["editorial.human_or_model_judgement"] = Metric.not_measured(
        "editorial.human_or_model_judgement", "no $0 language judge executed; human review at release gate")
    total_fact_runs = sum(1 for n in nodes for b in n.content for r in b.runs if r.kind == "fact")
    rv.metrics["fact.text_alignment"] = Metric.measured(
        "fact.text_alignment", 100.0 if fact_violations == 0 else 0.0, method="semantic diff vs fact locks",
        evidence=[f"fact_runs={total_fact_runs}", f"violations={fact_violations}"])
    return rv
