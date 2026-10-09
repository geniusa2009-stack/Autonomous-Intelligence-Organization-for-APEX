"""Declarative APEX ONE state machine.

Top-level states, the allowed transitions between them, failure-specific recovery
re-entry points, and the explicit internal checks executed inside each state.
Hundreds of explicit checks — not hundreds of fake permanent agents.
"""

from __future__ import annotations

from enum import StrEnum


class S(StrEnum):
    NEW = "NEW"
    MISSION_ANALYSIS = "MISSION_ANALYSIS"
    COMPUTE_PLAN = "COMPUTE_PLAN"
    SOURCE_DISCOVERY = "SOURCE_DISCOVERY"
    SOURCE_EXPANSION = "SOURCE_EXPANSION"
    DOCUMENT_PARSE = "DOCUMENT_PARSE"
    EVIDENCE_EXTRACTION = "EVIDENCE_EXTRACTION"
    CONTRADICTION_SEARCH = "CONTRADICTION_SEARCH"
    FACT_RESOLUTION = "FACT_RESOLUTION"
    FACT_LOCK = "FACT_LOCK"
    OPPORTUNITY_MODEL = "OPPORTUNITY_MODEL"
    READER_MODEL = "READER_MODEL"
    CONTENT_ARCHITECTURE = "CONTENT_ARCHITECTURE"
    DRAFT = "DRAFT"
    VOICE_REVIEW = "VOICE_REVIEW"
    FACT_ALIGNMENT = "FACT_ALIGNMENT"
    DOCUMENT_AST = "DOCUMENT_AST"
    DESIGN_INTENT = "DESIGN_INTENT"
    CREATIVE_DIRECTIONS = "CREATIVE_DIRECTIONS"
    LAYOUT_SEARCH = "LAYOUT_SEARCH"
    LAYOUT_TOURNAMENT = "LAYOUT_TOURNAMENT"
    HTML_BUILD = "HTML_BUILD"
    RENDER = "RENDER"
    DETERMINISTIC_QA = "DETERMINISTIC_QA"
    VISION_QA = "VISION_QA"
    DESIGN_JURY = "DESIGN_JURY"
    MUTATION = "MUTATION"
    DOCUMENT_QA = "DOCUMENT_QA"
    RESEARCH_RECHECK = "RESEARCH_RECHECK"
    RELEASE_CANDIDATE = "RELEASE_CANDIDATE"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    FINAL = "FINAL"
    LEARN = "LEARN"


MAIN_PATH: tuple[S, ...] = (
    S.NEW, S.MISSION_ANALYSIS, S.COMPUTE_PLAN, S.SOURCE_DISCOVERY, S.SOURCE_EXPANSION,
    S.DOCUMENT_PARSE, S.EVIDENCE_EXTRACTION, S.CONTRADICTION_SEARCH, S.FACT_RESOLUTION,
    S.FACT_LOCK, S.OPPORTUNITY_MODEL, S.READER_MODEL, S.CONTENT_ARCHITECTURE, S.DRAFT,
    S.VOICE_REVIEW, S.FACT_ALIGNMENT, S.DOCUMENT_AST, S.DESIGN_INTENT, S.CREATIVE_DIRECTIONS,
    S.LAYOUT_SEARCH, S.LAYOUT_TOURNAMENT, S.HTML_BUILD, S.RENDER, S.DETERMINISTIC_QA,
    S.VISION_QA, S.DESIGN_JURY, S.MUTATION, S.DOCUMENT_QA, S.RESEARCH_RECHECK,
    S.RELEASE_CANDIDATE, S.HUMAN_APPROVAL, S.FINAL, S.LEARN,
)

# Forward edges = next state on the main path. Extra edges = loops / recovery.
_EXTRA_EDGES: dict[S, set[S]] = {
    S.SOURCE_EXPANSION: {S.SOURCE_DISCOVERY},
    S.FACT_RESOLUTION: {S.SOURCE_EXPANSION},                  # unresolved critical -> research more
    S.FACT_LOCK: {S.SOURCE_EXPANSION},
    S.VOICE_REVIEW: {S.DRAFT},                                # editorial loop
    S.FACT_ALIGNMENT: {S.DRAFT},
    S.DETERMINISTIC_QA: {S.LAYOUT_SEARCH, S.HTML_BUILD},      # geometry / RTL loops
    S.VISION_QA: {S.MUTATION},
    S.DESIGN_JURY: {S.MUTATION, S.DOCUMENT_QA},               # jury may accept directly
    S.MUTATION: {S.HTML_BUILD, S.LAYOUT_TOURNAMENT},
    S.DOCUMENT_QA: {S.CREATIVE_DIRECTIONS, S.CONTENT_ARCHITECTURE, S.LAYOUT_SEARCH},
    S.RESEARCH_RECHECK: {S.SOURCE_EXPANSION, S.FACT_ALIGNMENT},
    S.HUMAN_APPROVAL: {S.LEARN, S.CONTENT_ARCHITECTURE, S.CREATIVE_DIRECTIONS},  # rejection paths
    S.LEARN: set(),
}

TRANSITIONS: dict[S, frozenset[S]] = {}
for i, st in enumerate(MAIN_PATH):
    nxt = {MAIN_PATH[i + 1]} if i + 1 < len(MAIN_PATH) else set()
    TRANSITIONS[st] = frozenset(nxt | _EXTRA_EDGES.get(st, set()))

# RELEASE_CANDIDATE -> FINAL is NEVER a direct automatic edge: it must go through HUMAN_APPROVAL.
assert S.FINAL not in TRANSITIONS[S.RELEASE_CANDIDATE]

HUMAN_ONLY_TRANSITIONS: frozenset[tuple[S, S]] = frozenset({(S.HUMAN_APPROVAL, S.FINAL)})

TERMINAL: frozenset[S] = frozenset({S.LEARN})


class FailureKind(StrEnum):
    FACT = "FACT"
    RESEARCH = "RESEARCH"
    VOICE = "VOICE"
    RTL = "RTL"
    GEOMETRY = "GEOMETRY"
    AESTHETIC = "AESTHETIC"
    READER = "READER"
    RHYTHM = "RHYTHM"
    COMPUTE = "COMPUTE"
    LICENSE = "LICENSE"


# Failure-specific recovery: re-enter the narrowest loop that can fix the failure.
RECOVERY: dict[FailureKind, S | None] = {
    FailureKind.FACT: S.SOURCE_EXPANSION,          # research loop
    FailureKind.RESEARCH: S.SOURCE_EXPANSION,
    FailureKind.VOICE: S.DRAFT,                    # editorial loop
    FailureKind.RTL: S.HTML_BUILD,                 # bidi/layout loop
    FailureKind.GEOMETRY: S.LAYOUT_SEARCH,         # layout/compiler loop
    FailureKind.AESTHETIC: S.MUTATION,             # design mutation
    FailureKind.READER: S.CONTENT_ARCHITECTURE,    # IA / editorial redesign
    FailureKind.RHYTHM: S.CREATIVE_DIRECTIONS,     # art direction loop
    FailureKind.COMPUTE: None,                     # queue / wait — stay in state
    FailureKind.LICENSE: None,                     # block — human decision
}


# Explicit internal checks executed within each state (recorded in checks.jsonl).
CHECKS: dict[S, tuple[str, ...]] = {
    S.MISSION_ANALYSIS: (
        "mission.text_present", "mission.opportunity_named", "mission.type_classified",
        "mission.cycle_parsed", "mission.institution_extracted", "mission.privacy_classified",
        "mission.risk_classified", "mission.critical_predicates_listed", "policy.budget_is_zero",
        "policy.human_release_required",
    ),
    S.COMPUTE_PLAN: (
        "compute.registry_loaded", "compute.license_registry_loaded", "compute.firewall_armed",
        "compute.paid_fallback_disabled", "compute.providers_probed", "compute.local_fallback_known",
        "compute.design_routes_planned", "compute.quota_state_loaded", "plan.dag_acyclic",
        "plan.worker_count_scaled", "plan.retry_budgets_set", "plan.human_gates_set",
    ),
    S.SOURCE_DISCOVERY: (
        "research.route_available", "research.official_domain_hypothesis", "research.queries_generated",
        "research.results_deduplicated", "research.robots_respected", "research.sources_recorded",
    ),
    S.SOURCE_EXPANSION: (
        "research.official_source_present", "research.document_links_followed",
        "research.historical_cycle_sources_tagged", "research.third_party_sources_tagged",
        "research.authority_scored", "research.coverage_per_critical_predicate",
    ),
    S.DOCUMENT_PARSE: (
        "parse.html_blocks_extracted", "parse.pdf_pages_extracted", "parse.headings_preserved",
        "parse.content_hashed", "parse.text_cached", "parse.empty_documents_flagged",
    ),
    S.EVIDENCE_EXTRACTION: (
        "evidence.deadlines_extracted", "evidence.fees_extracted", "evidence.funding_extracted",
        "evidence.tests_extracted", "evidence.eligibility_extracted", "evidence.requirements_extracted",
        "evidence.quotes_attached", "evidence.locators_attached", "evidence.values_normalized",
        "evidence.criticality_assigned",
    ),
    S.CONTRADICTION_SEARCH: (
        "contradiction.slots_grouped", "contradiction.values_compared",
        "contradiction.cycle_staleness_checked", "contradiction.scope_differences_checked",
        "contradiction.units_compared",
    ),
    S.FACT_RESOLUTION: (
        "resolution.primary_source_search", "resolution.independent_verification",
        "resolution.contradiction_search_done", "resolution.freshness_check",
        "resolution.semantic_resolution", "resolution.no_unresolved_critical",
    ),
    S.FACT_LOCK: (
        "lock.only_verified_claims", "lock.every_critical_predicate_locked_or_reported",
        "lock.hashes_computed", "lock.bilingual_display_rendered", "lock.persisted",
    ),
    S.OPPORTUNITY_MODEL: (
        "opportunity.core_value", "opportunity.hidden_value", "opportunity.main_barrier",
        "opportunity.risks", "opportunity.fit", "opportunity.misunderstandings",
        "opportunity.action_plan", "opportunity.facts_cite_locks", "opportunity.opinions_labelled",
    ),
    S.READER_MODEL: (
        "reader.personas_selected", "reader.must_understand_slots", "reader.weak_english_considered",
        "reader.parent_considered", "reader.mobile_considered",
    ),
    S.CONTENT_ARCHITECTURE: (
        "ia.rhythm_plan", "ia.decision_critical_first", "ia.warning_placement",
        "ia.no_consecutive_same_rhythm", "ia.closing_action",
    ),
    S.DRAFT: (
        "draft.fact_slots_only", "draft.voice_patterns_retrieved", "draft.bilingual_terms_isolated",
        "draft.cta_present", "draft.facts_vs_opinion_separated",
    ),
    S.VOICE_REVIEW: (
        "voice.naturalness", "voice.egyptian_dialect", "voice.no_bureaucratic_msa",
        "voice.no_ai_cliches", "voice.jake_frequency", "voice.humor_placement",
        "voice.sentence_compression", "voice.bilingual_balance",
    ),
    S.FACT_ALIGNMENT: (
        "alignment.semantic_diff_clean", "alignment.no_unbound_numbers", "alignment.no_unbound_dates",
        "alignment.no_altered_money", "alignment.lock_hashes_intact",
    ),
    S.DOCUMENT_AST: (
        "ast.nodes_typed", "ast.importance_set", "ast.reading_modes_set",
        "ast.first_fixation_set", "ast.locked_refs_bound", "ast.rhythm_roles_set",
    ),
    S.DESIGN_INTENT: (
        "intent.per_page", "intent.density_targets", "intent.archetype_preferences",
        "intent.rationale_recorded",
    ),
    S.CREATIVE_DIRECTIONS: (
        "directions.multiple_generated", "directions.genome_invariants_respected",
        "directions.distinct_from_history",
    ),
    S.LAYOUT_SEARCH: (
        "layout.candidates_generated", "layout.design_routes_resolved", "layout.license_safe_engines",
        "layout.seeds_recorded",
    ),
    S.LAYOUT_TOURNAMENT: (
        "tournament.deterministic_prefilter", "tournament.specialist_scoring",
        "tournament.selection", "tournament.elitism", "tournament.convergence_checked",
    ),
    S.HTML_BUILD: (
        "html.compiled_from_ast", "html.fact_slots_bound", "html.bidi_isolation",
        "html.fonts_embedded", "html.print_css",
    ),
    S.RENDER: (
        "render.pages_screenshotted", "render.thumbnails", "render.grayscale", "render.blur",
        "render.zoom_crops", "render.mobile_preview", "render.pdf_printed",
    ),
    S.DETERMINISTIC_QA: (
        "qa.overflow", "qa.clipping", "qa.collision", "qa.margins", "qa.alignment", "qa.line_length",
        "qa.font_hierarchy", "qa.widows_orphans", "qa.page_bounds", "qa.contrast", "qa.whitespace",
        "qa.density", "qa.repetition", "qa.rtl_direction", "qa.ltr_isolation", "qa.currency",
        "qa.percent", "qa.dates", "qa.parentheses", "qa.mixed_runs", "qa.long_urls",
        "qa.dom_fact_integrity",
    ),
    S.VISION_QA: (
        "vision.first_fixation", "vision.hierarchy", "vision.arabic_natural", "vision.memorable",
        "vision.generic_ai_look", "vision.card_overuse", "vision.whitespace_intent",
        "vision.brand_belonging", "vision.history_similarity",
    ),
    S.DESIGN_JURY: (
        "jury.aesthetic", "jury.typography", "jury.layout", "jury.text_quality",
        "jury.artifact_detection", "jury.intent_fidelity", "jury.disagreement_resolution",
    ),
    S.MUTATION: ("mutation.failure_classified", "mutation.operators_selected", "mutation.rebuilt"),
    S.DOCUMENT_QA: (
        "doc.contact_sheet", "doc.rhythm", "doc.dark_light_distribution", "doc.density_distribution",
        "doc.hero_frequency", "doc.page_repetition", "doc.chapter_distinction", "doc.reader_lab",
    ),
    S.RESEARCH_RECHECK: (
        "recheck.locks_intact", "recheck.dom_values_match_locks", "recheck.freshness_still_valid",
    ),
    S.RELEASE_CANDIDATE: (
        "release.critical_gates", "release.license_guard", "release.artifacts_complete",
        "release.no_secrets", "release.pdf_valid",
    ),
    S.HUMAN_APPROVAL: ("human.gate_pending",),
    S.FINAL: ("final.human_approved",),
    S.LEARN: ("learn.approval_memory", "learn.design_memory", "learn.failure_memory"),
}


def total_check_count() -> int:
    return sum(len(v) for v in CHECKS.values())
