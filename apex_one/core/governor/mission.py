"""MissionAnalyzer: classify the mission, its risk and its privacy class (deterministic)."""

from __future__ import annotations

import re

from apex_one.core.schemas.mission import (
    Mission,
    OpportunityType,
    PrivacyClass,
    RiskClass,
    RiskProfile,
)

TYPE_RULES = [
    (OpportunityType.SCHOLARSHIP, r"scholarship|منحة|grant"),
    (OpportunityType.EXCHANGE_PROGRAM, r"exchange|yes program|flex|تبادل"),
    (OpportunityType.FELLOWSHIP, r"fellowship|زمالة"),
    (OpportunityType.COMPETITION, r"competition|olympiad|contest|challenge|مسابقة|أولمبياد"),
    (OpportunityType.SUMMER_PROGRAM, r"summer|camp|صيفي"),
    (OpportunityType.UNIVERSITY_ADMISSION, r"college|university|institute of technology|جامعة|كلية"),
    (OpportunityType.SCHOOL, r"school|academy|مدرسة"),
]
CRITICAL_BY_TYPE = {
    OpportunityType.UNIVERSITY_ADMISSION: ["deadline", "fee", "funding", "scholarship_coverage", "deposit",
                                           "test_requirement", "test_minimum", "eligibility", "country_eligibility",
                                           "application_requirement", "visa_logistics"],
    OpportunityType.SCHOLARSHIP: ["deadline", "eligibility", "country_eligibility", "funding",
                                  "scholarship_coverage", "application_requirement", "age", "grade"],
    OpportunityType.SCHOOL: ["deadline", "fee", "funding", "age", "grade", "eligibility", "test_requirement"],
    OpportunityType.COMPETITION: ["deadline", "eligibility", "age", "grade", "fee", "country_eligibility"],
    OpportunityType.EXCHANGE_PROGRAM: ["deadline", "eligibility", "age", "grade", "funding", "country_eligibility",
                                       "visa_logistics"],
    OpportunityType.FELLOWSHIP: ["deadline", "eligibility", "funding", "country_eligibility", "application_requirement"],
    OpportunityType.SUMMER_PROGRAM: ["deadline", "fee", "funding", "age", "grade", "eligibility"],
    OpportunityType.OTHER: ["deadline", "eligibility", "fee", "funding"],
}
MUST_LOCK = {"deadline": "deadline.application"}
PRIVATE_HINTS = r"@|\+20|\b01[0125]\d{8}\b|my (gpa|grades|passport|phone|address)|national id|الرقم القومي"


class MissionAnalyzer:
    def analyze(self, text: str) -> tuple[Mission, RiskProfile, PrivacyClass]:
        t = text.strip()
        low = t.lower()
        cyc = re.search(r"\b(fall|spring|summer|winter|autumn)\s+(20\d\d)\b", t, re.I)
        year = re.search(r"\b(20\d\d)\b", t)
        cycle = f"{cyc.group(1).title()} {cyc.group(2)}" if cyc else (year.group(1) if year else None)
        cycle_year = int(cyc.group(2)) if cyc else (int(year.group(1)) if year else None)
        name = re.sub(r"^\s*(create|make|build|write)\s+(an?\s+)?apex\s+guide\s+(for|about)\s+", "", t, flags=re.I)
        name = re.sub(r"\s*\(.*?\)\s*", " ", name).strip().rstrip(".")
        institution = re.sub(r"\b(fall|spring|summer|winter|autumn)\s+20\d\d\b|\b20\d\d\b", "", name, flags=re.I).strip(" -–,")
        otype = OpportunityType.OTHER
        for ty, rx in TYPE_RULES:
            if re.search(rx, low):
                otype = ty
                break
        risk = RiskProfile(risk_class=RiskClass.HIGH_FACTUAL, critical_predicates=CRITICAL_BY_TYPE[otype],
                           rationale=["opportunity guides drive irreversible student decisions (deadlines, money)",
                                      f"type={otype.value}"])
        privacy = PrivacyClass.PRIVATE_STUDENT_DATA if re.search(PRIVATE_HINTS, low) else PrivacyClass.PUBLIC
        mission = Mission(text=t, opportunity_name=name or t, opportunity_type=otype, institution=institution or name,
                          cycle=cycle, cycle_year=cycle_year)
        return mission, risk, privacy
