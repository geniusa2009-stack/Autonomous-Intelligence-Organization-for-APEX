"""ONE Opportunity Intelligence: understand the opportunity, don't just summarise it.

Facts reference FactLock slots ({{slot}}); inferences and APEX opinions are labelled as such.
Every rule fires only when the locks it depends on exist — nothing is assumed.
"""

from __future__ import annotations

from datetime import date

from apex_one.core.schemas.evidence import FactLock
from apex_one.core.schemas.opportunity import Insight, OpportunityModel


class OpportunityModeler:
    def __init__(self, locks: list[FactLock], open_slots: list[str], today: date | None = None):
        self.locks = {lk.slot: lk for lk in locks}
        self.open_slots = open_slots
        self.today = today or date.today()

    def has(self, *slots: str) -> bool:
        return all(s in self.locks for s in slots)

    def refs(self, *slots: str) -> list[str]:
        return [self.locks[s].claim_id for s in slots if s in self.locks]

    def fact(self, en: str, ar: str, *slots: str) -> Insight:
        return Insight(text_en=en, text_ar=ar, kind="fact", claim_refs=self.refs(*slots))

    def infer(self, en: str, ar: str, *slots: str, kind: str = "inference") -> Insight:
        return Insight(text_en=en, text_ar=ar, kind=kind, claim_refs=self.refs(*slots), confidence=0.8)

    def build(self, name: str) -> OpportunityModel:
        m = OpportunityModel(opportunity_name=name)
        L = self.has
        if L("scholarship_coverage.tuition"):
            m.core_value.append(self.fact("Tuition coverage: {{scholarship_coverage.tuition|en}} for admitted students.",
                                          "الـ [[tuition]] متغطية بنسبة {{scholarship_coverage.tuition}} لكل طالب بيتقبل.",
                                          "scholarship_coverage.tuition"))
        if L("fee.application") and self.locks["fee.application"].value.amount == 0:
            m.core_value.append(self.fact("No application fee.", "التقديم نفسه ببلاش، مفيش [[application fee]].",
                                          "fee.application"))
        if L("work_requirement.hours_per_week"):
            m.hidden_value.append(self.infer(
                "On-campus work ({{work_requirement.hours_per_week|en}} h/week) builds real experience and income.",
                "شغل جوه الكامبس {{work_requirement.hours_per_week}} ساعات في الأسبوع: خبرة حقيقية وفلوس في إيدك.",
                "work_requirement.hours_per_week"))
        if L("test_requirement.sat_act") and self.locks["test_requirement.sat_act"].value.canonical == "false":
            m.hidden_value.append(self.fact("SAT/ACT are not required (test-optional).",
                                            "الـ [[SAT]] والـ [[ACT]] {{test_requirement.sat_act?مطلوبين|مش مطلوبين}}.",
                                            "test_requirement.sat_act"))
        if L("eligibility.financial_need"):
            m.main_barrier.append(self.fact("Applicants must demonstrate financial need.",
                                            "{{eligibility.financial_need}}.", "eligibility.financial_need"))
        if L("test_minimum.toefl_ibt"):
            m.main_barrier.append(self.fact("English proficiency minimum (TOEFL iBT {{test_minimum.toefl_ibt|en}}).",
                                            "لازم توصل للحد الأدنى في الإنجليزي: [[TOEFL iBT]] {{test_minimum.toefl_ibt}}.",
                                            "test_minimum.toefl_ibt"))
            m.academic_risk.append(self.infer("The English test is the longest preparation step.",
                                              "امتحان الإنجليزي غالباً أطول خطوة في التحضير.", "test_minimum.toefl_ibt",
                                              kind="apex_opinion"))
        if L("eligibility.academic"):
            m.eligibility_risk.append(self.fact("Academic timing condition (official wording).",
                                                "شرط إتمام الدراسة الثانوية في ميعاده (بالنص الرسمي).",
                                                "eligibility.academic"))
        if L("country_eligibility.international"):
            m.eligibility_risk.append(self.fact("Open to applicants from all countries, Egypt included.",
                                                "{{country_eligibility.international}}، ومصر منهم.",
                                                "country_eligibility.international"))
        if L("funding.student_contribution_per_year"):
            lk = self.locks["funding.student_contribution_per_year"]
            ar = ("هتساهم بحوالي {{funding.student_contribution_per_year}} في السنة (رقم تقديري من المصدر)."
                  if lk.hedge else "هتساهم بـ{{funding.student_contribution_per_year}} في السنة.")
            m.financial_risk.append(self.fact(
                "Expected student contribution: {{funding.student_contribution_per_year|en}} per year"
                + (" (estimated)" if lk.hedge else "") + ".", ar, "funding.student_contribution_per_year"))
            if L("scholarship_coverage.tuition"):
                m.likely_misunderstanding.append(self.infer(
                    "Full tuition coverage is not the same as zero cost.",
                    "تغطية الـ [[tuition]] بالكامل مش معناها إن التكلفة صفر.",
                    "scholarship_coverage.tuition", "funding.student_contribution_per_year"))
        if L("deposit.enrollment"):
            m.financial_risk.append(self.fact("Enrollment deposit: {{deposit.enrollment|en}}.",
                                              "الـ [[deposit]] لتأكيد مكانك: {{deposit.enrollment}}.", "deposit.enrollment"))
        if L("test_requirement.sat_act", "test_minimum.toefl_ibt") and \
                self.locks["test_requirement.sat_act"].value.canonical == "false":
            m.likely_misunderstanding.append(self.infer(
                "Test-optional applies to SAT/ACT, not to the English requirement.",
                "[[test-optional]] للـ [[SAT]] بس، مش للإنجليزي.", "test_requirement.sat_act", "test_minimum.toefl_ibt"))
        if L("deadline.application"):
            d = date.fromisoformat(self.locks["deadline.application"].value.canonical)
            days = (d - self.today).days
            if days < 0:
                m.timing_risk.append(self.infer("The application deadline for this cycle has passed.",
                                                "ميعاد التقديم للدورة دي عدّى.", "deadline.application"))
            elif days < 120:
                m.timing_risk.append(self.infer("Less than four months remain before the deadline.",
                                                "فاضل أقل من أربع شهور على آخر ميعاد.", "deadline.application"))
            else:
                m.timing_risk.append(self.infer("There is time, but English testing and documents take months.",
                                                "فيه وقت، بس الامتحانات والورق بياخدوا شهور.", "deadline.application"))
        # fit (APEX opinion, grounded in locks)
        if L("scholarship_coverage.tuition", "eligibility.financial_need"):
            m.best_fit_student.append(self.infer("Strong students who genuinely need full financial support.",
                                                 "طالب شاطر ومحتاج دعم مادي حقيقي.", "eligibility.financial_need",
                                                 kind="apex_opinion"))
        if L("work_requirement.hours_per_week"):
            m.best_fit_student.append(self.infer("Students happy to work on campus while studying.",
                                                 "طالب مش عنده مشكلة يشتغل وهو بيدرس.",
                                                 "work_requirement.hours_per_week", kind="apex_opinion"))
            m.poor_fit_student.append(self.infer("Students who cannot commit weekly work hours.",
                                                 "طالب مش هيقدر يلتزم بساعات شغل كل أسبوع.",
                                                 "work_requirement.hours_per_week", kind="apex_opinion"))
        if L("funding.student_contribution_per_year"):
            m.poor_fit_student.append(self.infer("Families with no way to cover the yearly contribution.",
                                                 "أسرة مش هتقدر خالص تغطي المساهمة السنوية.",
                                                 "funding.student_contribution_per_year", kind="apex_opinion"))
        m.competitive_signal.append(Insight(
            text_en="Admission selectivity is not established by verified sources.",
            text_ar="نسبة القبول مش متأكدين منها من مصدر رسمي، فمش هنخمّن.", kind="inference", confidence=1.0))
        m.decision_critical_questions += [
            Insight(text_en="Can I reach the English minimum before the deadline?", text_ar="هقدر أوصل لحد الإنجليزي قبل الميعاد؟",
                    kind="inference", claim_refs=self.refs("test_minimum.toefl_ibt", "deadline.application")),
            Insight(text_en="Can my family cover the remaining yearly cost?", text_ar="أسرتي هتقدر تغطي المصاريف الباقية؟",
                    kind="inference", claim_refs=self.refs("funding.student_contribution_per_year")),
        ]
        # action plan ordered by locked dates
        steps = [("test_minimum.toefl_ibt", "Book and prepare the English test.", "احجز امتحان الإنجليزي وابدأ تذاكر.")]
        if L("deadline.application"):
            steps.append(("deadline.application", "Submit the application by {{deadline.application|en}}.",
                          "قدّم قبل {{deadline.application}}."))
        if L("deadline.financial_documents"):
            steps.append(("deadline.financial_documents", "Send financial documents by {{deadline.financial_documents|en}}.",
                          "ابعت الورق المالي قبل {{deadline.financial_documents}}."))
        if L("decision_date.decision"):
            steps.append(("decision_date.decision", "Decisions arrive by {{decision_date.decision|en}}.",
                          "النتيجة بتطلع قبل {{decision_date.decision}}."))
        if L("deadline.enrollment_deposit"):
            steps.append(("deadline.enrollment_deposit", "Pay the deposit by {{deadline.enrollment_deposit|en}}.",
                          "ادفع الـ [[deposit]] قبل {{deadline.enrollment_deposit}}."))
        for slot, en, ar in steps:
            if slot in self.locks:
                m.student_action_plan.append(self.fact(en, ar, slot))
        m.open_questions = list(self.open_slots)
        return m
