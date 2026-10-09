"""APEXEgyptianWriter: natural Egyptian Arabic + intelligent English, facts only through locks.

Native mode composes approved Voice Genome patterns deterministically (seeded). When a $0 model route
with strong Egyptian Arabic exists, narrative paragraphs may be polished by the model; the result is
accepted only if it preserves every fact slot and introduces no unbound number (else native text stays).
"""

from __future__ import annotations

import re
from typing import Any

from apex_one.core.schemas.document import Block, DocNode, NodeType, TextRun
from apex_one.core.schemas.evidence import FactLock
from apex_one.core.schemas.opportunity import Insight, OpportunityModel
from apex_one.document.ast.runs import MissingFact, parse_runs, runs_text
from apex_one.editorial.architect.architect import SectionPlan
from apex_one.editorial.voice.genome import VoiceGenome

STAT_LABELS = [
    ("deadline.application", "آخر ميعاد للتقديم"),
    ("scholarship_coverage.tuition", "تغطية الـ [[tuition]]"),
    ("fee.application", "رسوم التقديم"),
    ("funding.student_contribution_per_year", "مساهمتك في السنة"),
    ("test_minimum.toefl_ibt", "أقل درجة [[TOEFL iBT]]"),
    ("deposit.enrollment", "الـ [[deposit]]"),
]
REQUIREMENT_LABELS = {
    "application_requirement.application_form": "الـ [[application form]] أونلاين",
    "application_requirement.transcripts": "الـ [[transcripts]] الرسمية بتاعة الثانوي",
    "application_requirement.recommendation_letters": "جوابات توصية، عددها {{application_requirement.recommendation_letters}}",
    "application_requirement.essay": "[[essay]] شخصي",
    "application_requirement.financial_statement": "الـ [[International Student Financial Statement]]",
    "application_requirement.english_test_scores": "نتيجة امتحان الإنجليزي",
    "application_requirement.passport": "باسبور ساري",
    "application_requirement.interview": "[[interview]]",
}
TEST_LABELS = [("test_minimum.toefl_ibt", "[[TOEFL iBT]]"), ("test_minimum.ielts", "[[IELTS]]"),
               ("test_minimum.duolingo", "[[Duolingo English Test]]")]
DATE_LABELS = {
    "deadline.application": "آخر ميعاد للتقديم",
    "deadline.financial_documents": "آخر ميعاد للورق المالي",
    "decision_date.decision": "النتيجة",
    "deadline.enrollment_deposit": "آخر ميعاد للـ [[deposit]]",
    "deadline.early_application": "التقديم المبكر",
    "deadline.scholarship": "ميعاد المنحة",
}
OPEN_SLOT_AR = {
    "visa_logistics.visa_type": "نوع الفيزا (مصدر واحد بس، محتاج تأكيد)",
    "funding.aid_type": "نوع الدعم المادي بالتفصيل",
    "application_requirement.english_test_scores": "طريقة إرسال نتيجة الإنجليزي",
}


class APEXEgyptianWriter:
    def __init__(self, voice: VoiceGenome, locks: list[FactLock], opp: OpportunityModel, *, institution: str,
                 cycle: str, seed: int, synthetic: bool, broker=None, workspace=None,
                 avoid_variants: dict[str, set[int]] | None = None):
        self.voice, self.locks = voice, {lk.slot: lk for lk in locks}
        self.opp, self.institution, self.cycle, self.seed = opp, institution, cycle, seed
        self.synthetic, self.broker, self.ws = synthetic, broker, workspace
        self.avoid = avoid_variants or {}
        self.vars = {"institution": institution, "cycle": cycle}
        self.jake_used = 0
        self.section_index = 0
        self.last_jake_index: int | None = None
        self.log: list[dict[str, Any]] = []
        self.dropped: list[str] = []
        self.variants_used: dict[str, int] = {}

    # ---------------- helpers ----------------
    def runs(self, template: str, lang: str = "ar") -> list[TextRun] | None:
        try:
            return parse_runs(template, self.locks, self.vars, base_lang=lang)
        except MissingFact as e:
            self.dropped.append(f"{template[:60]}… (missing lock {e})")
            return None

    def block(self, role: str, template: str, lang: str = "ar", **data: Any) -> Block | None:
        r = self.runs(template, lang)
        return Block(role=role, runs=r, data=data) if r is not None else None

    def insight_block(self, ins: Insight, role: str = "list_item") -> Block | None:
        b = self.block(role, ins.text_ar, kind=ins.kind)
        if b is not None:
            b.data["opinion"] = ins.kind == "apex_opinion"
        return b

    def _jake(self, line: str, node_type: NodeType) -> str:
        rules = self.voice.rules.get("jake", {})
        if node_type.value in rules.get("forbidden_in", []) or self.jake_used >= rules.get("max_per_document", 3):
            return line
        if self.last_jake_index is not None and \
                self.section_index - self.last_jake_index < rules.get("min_sections_between", 3):
            return line
        if not self.voice.jake:
            return line
        self.jake_used += 1
        self.last_jake_index = self.section_index
        pattern = self.voice.jake[(self.seed + self.jake_used) % len(self.voice.jake)]
        out = pattern.replace("{line}", line.rstrip("."))
        return out if out.endswith((".", "!", "؟")) else out + "."

    def _variant(self, section: str) -> dict[str, Any]:
        idx, v = self.voice.variant(section, self.seed, self.avoid.get(section))
        self.variants_used[section] = idx
        return v

    # ---------------- sections ----------------
    def write(self, plan: list[SectionPlan]) -> list[DocNode]:
        nodes = []
        for i, sp in enumerate(plan):
            fn = getattr(self, f"_w_{sp.node_type.name.lower()}", None)
            node = DocNode(semantic_type=sp.node_type, importance=sp.importance, reading_mode=sp.reading_mode,
                           decision_impact=sp.decision_impact, visual_density=sp.density, emotion=sp.emotion,
                           scan_target_seconds=sp.scan_target_seconds, rhythm_role=sp.rhythm_role)
            if fn is None:
                continue
            self.section_index = i
            fn(node, sp)
            node.content = [b for b in node.content if b is not None]
            node.locked_claim_refs = sorted({r.claim_id for b in node.content for r in b.runs if r.claim_id})
            stats = [b for b in node.content if b.role in ("stat", "hero")]
            node.first_fixation = (stats[0] if stats else next((b for b in node.content if b.role == "heading"),
                                                               node.content[0] if node.content else Block(role="x"))).block_id
            nodes.append(node)
        return nodes

    def _heading(self, node: DocNode, text_ar: str, kicker: str = "") -> None:
        node.title_ar = text_ar
        if kicker:
            node.content.append(self.block("kicker", kicker))
        node.content.append(self.block("heading", text_ar))

    def _w_cover(self, node: DocNode, sp: SectionPlan) -> None:
        node.title_ar = self.institution
        node.title_en = f"{self.institution} — {self.cycle}"
        node.content += [
            self.block("kicker", "دليل APEX"),
            self.block("heading", self.institution, lang="en" if not re.search(r"[؀-ۿ]", self.institution) else "ar"),
            self.block("subtitle", f"دخول {self.cycle} • دليل كامل للطلاب المصريين"),
        ]
        if "deadline.application" in self.locks:
            node.content.append(self.block("stat", "{{deadline.application}}", label="آخر ميعاد"))
        if self.synthetic:
            node.content.append(self.block("notice", "نسخة اختبار اصطناعية: المؤسسة والأرقام كلها خيالية، مش بيانات حقيقية.",
                                           synthetic=True))

    def _w_opening(self, node: DocNode, sp: SectionPlan) -> None:
        v = self._variant("opening")
        self._heading(node, f"إيه هي {self.institution}؟", v.get("kicker", ""))
        body = list(v.get("body", []))
        if body:
            body[-1] = self._jake(body[-1], node.semantic_type)
        for p in body:
            node.content.append(self.block("paragraph", p))
        joke = next((j for j in self.voice.jokes if j.get("section") == "Opening"), None)
        if joke:
            node.content.append(self.block("aside", joke["text"], humor=True))

    def _w_opportunity_snapshot(self, node: DocNode, sp: SectionPlan) -> None:
        v = self._variant("snapshot")
        self._heading(node, "الفرصة في صفحة واحدة", v.get("kicker", ""))
        node.content.append(self.block("lead", v.get("lead", "")))
        for slot, label in STAT_LABELS:
            if slot in self.locks:
                lk = self.locks[slot]
                tpl = ("حوالي " if lk.hedge else "") + "{{" + slot + "}}"
                node.content.append(self.block("stat", tpl, label=label, hedge=lk.hedge))

    def _w_hero_fact(self, node: DocNode, sp: SectionPlan) -> None:
        v = self._variant("hero_coverage")
        node.title_ar = "الرقم اللي بيفرق"
        node.content += [self.block("kicker", v.get("kicker", "")),
                         self.block("hero", "{{scholarship_coverage.tuition}}"),
                         self.block("paragraph", v.get("line", "")),
                         self.block("note", v.get("sub", ""))]

    def _w_funding_chapter(self, node: DocNode, sp: SectionPlan) -> None:
        v = self._variant("funding")
        self._heading(node, "مين بيدفع إيه؟", v.get("kicker", ""))
        node.content.append(self.block("lead", v.get("intro", "")))
        node.content.append(self.block("subheading", v.get("covered_label", "متغطي")))
        node.content += [self.insight_block(i) for i in self.opp.core_value]
        node.content.append(self.block("subheading", v.get("you_pay_label", "عليك إنت")))
        node.content += [self.insight_block(i) for i in self.opp.financial_risk]
        if "scholarship_coverage.tuition" in self.locks:
            node.content.append(self.block("figure", "{{scholarship_coverage.tuition}}", viz="bar-fraction",
                                           value=self.locks["scholarship_coverage.tuition"].value.amount,
                                           label="نسبة تغطية الـ [[tuition]]"))

    def _w_warning(self, node: DocNode, sp: SectionPlan) -> None:
        node.title_ar = "تحذير مهم"
        for key in ("tuition_not_everything", "test_optional_not_english", "financial_need_required"):
            w = self.voice.warnings.get(key)
            if not w:
                continue
            t, b = self.block("heading", w["title"]), self.block("warning", w["body"])
            if t is not None and b is not None:
                node.content += [self.block("kicker", "خلي بالك"), t, b]
                break

    def _w_eligibility_chapter(self, node: DocNode, sp: SectionPlan) -> None:
        v = self._variant("eligibility")
        self._heading(node, "مين يقدر يقدّم؟", v.get("kicker", ""))
        node.content.append(self.block("lead", v.get("intro", "")))
        for i in self.opp.eligibility_risk + [x for x in self.opp.main_barrier if "financial" in x.text_en.lower()]:
            node.content.append(self.insight_block(i))
        if "eligibility.academic" in self.locks:
            node.content.append(self.block("lead", "النص الرسمي للشرط ده:"))
            node.content.append(self.block("quote", "{{eligibility.academic|en}}", lang="en", official=True))

    def _w_breath(self, node: DocNode, sp: SectionPlan) -> None:
        v = self._variant("breath")
        node.title_ar = "استراحة"
        node.content.append(self.block("pullquote", v.get("quote", "")))
        joke = next((j for j in self.voice.jokes if j.get("section") == "Breath"), None)
        if joke:
            node.content.append(self.block("aside", joke["text"], humor=True))

    def _w_application_journey(self, node: DocNode, sp: SectionPlan) -> None:
        v = self._variant("journey")
        self._heading(node, "هتحتاج تجهز إيه؟", v.get("kicker", ""))
        node.content.append(self.block("lead", v.get("intro", "")))
        for slot, label in REQUIREMENT_LABELS.items():
            if slot in self.locks:
                node.content.append(self.block("list_item", label, check=True))
        tests = [(s, lab) for s, lab in TEST_LABELS if s in self.locks]
        if tests:
            node.content.append(self.block("subheading", "الحد الأدنى للإنجليزي (واحد منهم يكفي)"))
            for s, lab in tests:
                node.content.append(self.block("stat", "{{" + s + "}}", label=lab))
        w = self.voice.warnings.get("test_optional_not_english")
        if w:
            node.content.append(self.block("note", w["title"]))

    def _w_timeline(self, node: DocNode, sp: SectionPlan) -> None:
        v = self._variant("timeline")
        self._heading(node, "المواعيد المهمة", v.get("kicker", ""))
        node.content.append(self.block("lead", v.get("intro", "")))
        dates = sorted([lk for lk in self.locks.values() if lk.value.type.value == "date"],
                       key=lambda lk: lk.value.canonical)
        for lk in dates:
            label = DATE_LABELS.get(lk.slot, lk.slot)
            node.content.append(self.block("step", "{{" + lk.slot + "}}", label=label,
                                           critical=lk.slot == "deadline.application"))

    def _w_apex_take(self, node: DocNode, sp: SectionPlan) -> None:
        v = self._variant("apex_take")
        self._heading(node, "رأينا بصراحة", v.get("kicker", "رأي APEX"))
        node.content.append(self.block("label", "ده رأي APEX، مش معلومة رسمية.", opinion=True))
        node.content.append(self.block("subheading", v.get("fit_intro", "")))
        node.content += [self.insight_block(i) for i in self.opp.best_fit_student]
        node.content.append(self.block("subheading", v.get("poor_fit_intro", "")))
        node.content += [self.insight_block(i) for i in self.opp.poor_fit_student]
        line = self._jake("القرار مش بس إنك تتقبل، القرار إنك تكون مرتاح هناك أربع سنين.", node.semantic_type)
        node.content.append(self.block("paragraph", line, opinion=True))

    def _w_checklist(self, node: DocNode, sp: SectionPlan) -> None:
        v = self._variant("checklist")
        self._heading(node, "خطتك من النهارده", v.get("kicker", ""))
        node.content.append(self.block("lead", v.get("intro", "")))
        node.content += [self.insight_block(i, role="list_item") for i in self.opp.student_action_plan]
        for b in node.content:
            if b is not None and b.role == "list_item":
                b.data["check"] = True
        if self.voice.ctas:
            node.content.append(self.block("cta", self.voice.ctas[self.seed % len(self.voice.ctas)]))

    def _w_closing(self, node: DocNode, sp: SectionPlan) -> None:
        v = self._variant("closing")
        self._heading(node, "الخلاصة", v.get("kicker", ""))
        node.content.append(self.block("paragraph", self._jake(v.get("line", ""), node.semantic_type)))
        if self.voice.ctas:
            node.content.append(self.block("cta", self.voice.ctas[(self.seed + 1) % len(self.voice.ctas)]))
        if self.opp.open_questions:
            node.content.append(self.block("subheading", "حاجات لسه بنتأكد منها"))
            for s in self.opp.open_questions[:5]:
                node.content.append(self.block("list_item", OPEN_SLOT_AR.get(s, "معلومة محتاجة تأكيد من مصدر رسمي تاني"),
                                               open_question=s))

    # ---------------- optional model polish ----------------
    def polish_with_model(self, nodes: list[DocNode], purpose: str = "production") -> int:
        """Ask a $0 model to make narrative paragraphs more natural. Strictly validated."""
        if self.broker is None:
            return 0
        from apex_one.compute.providers import ChatMessage
        from apex_one.core.schemas.compute import CapabilityRequest, Level
        from apex_one.editorial.fact_guard.semantic_diff import semantic_diff

        accepted = 0
        for node in nodes:
            if node.semantic_type not in (NodeType.OPENING, NodeType.APEX_TAKE, NodeType.CLOSING):
                continue
            for b in node.content:
                if b.role != "paragraph" or any(r.kind == "fact" for r in b.runs):
                    continue
                original = runs_text(b.runs)
                req = CapabilityRequest(task="editorial.write", min_egyptian_arabic=Level.MEDIUM, purpose=purpose)
                res = self.broker.complete(req, [
                    ChatMessage("system", "أعد صياغة الجملة بالعامية المصرية الطبيعية، بدون أرقام جديدة وبدون مبالغة. "
                                          "اكتب الجملة فقط."),
                    ChatMessage("user", original)], workspace=self.ws, max_tokens=200)
                if not res.executed or not res.text:
                    continue
                text = res.text.strip().strip('"')
                if semantic_diff(text, list(self.locks.values())) or len(text) > 3 * len(original):
                    self.log.append({"block": b.block_id, "rejected_model_text": text[:200]})
                    continue
                b.runs = [TextRun(kind="text", text=text, lang="ar")]
                b.data["polished_by"] = res.model_id
                accepted += 1
        return accepted
