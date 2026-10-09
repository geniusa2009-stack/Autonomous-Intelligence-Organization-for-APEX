"""APEX opportunity ontology."""

from enum import StrEnum


class EntityType(StrEnum):
    OPPORTUNITY = "Opportunity"
    INSTITUTION = "Institution"
    PROGRAM = "Program"
    COUNTRY = "Country"
    DEADLINE = "Deadline"
    ELIGIBILITY_RULE = "EligibilityRule"
    FUNDING_ITEM = "FundingItem"
    FEE = "Fee"
    TEST = "Test"
    DOCUMENT_REQUIREMENT = "DocumentRequirement"
    RECOMMENDATION = "Recommendation"
    ESSAY = "Essay"
    INTERVIEW = "Interview"
    VISA_STEP = "VisaStep"
    SOURCE = "Source"
    CLAIM = "Claim"
    EVIDENCE = "Evidence"
    APPLICANT_STEP = "ApplicantStep"


class Relation(StrEnum):
    OFFERED_BY = "OFFERED_BY"
    FOR_PROGRAM = "FOR_PROGRAM"
    HAS_DEADLINE = "HAS_DEADLINE"
    HAS_ELIGIBILITY = "HAS_ELIGIBILITY"
    HAS_FUNDING = "HAS_FUNDING"
    HAS_FEE = "HAS_FEE"
    REQUIRES_TEST = "REQUIRES_TEST"
    REQUIRES_DOCUMENT = "REQUIRES_DOCUMENT"
    HAS_VISA_STEP = "HAS_VISA_STEP"
    ASSERTED_BY = "ASSERTED_BY"
    SUPPORTED_BY = "SUPPORTED_BY"
    FROM_SOURCE = "FROM_SOURCE"
    CONTRADICTS = "CONTRADICTS"
    PRECEDES = "PRECEDES"
    HAS_STEP = "HAS_STEP"
    OPEN_TO = "OPEN_TO"


PREDICATE_ENTITY = {
    "deadline": (EntityType.DEADLINE, Relation.HAS_DEADLINE),
    "decision_date": (EntityType.DEADLINE, Relation.HAS_DEADLINE),
    "eligibility": (EntityType.ELIGIBILITY_RULE, Relation.HAS_ELIGIBILITY),
    "country_eligibility": (EntityType.ELIGIBILITY_RULE, Relation.HAS_ELIGIBILITY),
    "age": (EntityType.ELIGIBILITY_RULE, Relation.HAS_ELIGIBILITY),
    "grade": (EntityType.ELIGIBILITY_RULE, Relation.HAS_ELIGIBILITY),
    "funding": (EntityType.FUNDING_ITEM, Relation.HAS_FUNDING),
    "scholarship_coverage": (EntityType.FUNDING_ITEM, Relation.HAS_FUNDING),
    "fee": (EntityType.FEE, Relation.HAS_FEE),
    "deposit": (EntityType.FEE, Relation.HAS_FEE),
    "test_minimum": (EntityType.TEST, Relation.REQUIRES_TEST),
    "test_requirement": (EntityType.TEST, Relation.REQUIRES_TEST),
    "application_requirement": (EntityType.DOCUMENT_REQUIREMENT, Relation.REQUIRES_DOCUMENT),
    "visa_logistics": (EntityType.VISA_STEP, Relation.HAS_VISA_STEP),
    "work_requirement": (EntityType.FUNDING_ITEM, Relation.HAS_FUNDING),
}
