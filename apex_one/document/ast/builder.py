"""Builds the Document AST from written nodes."""

from __future__ import annotations

from apex_one.core.schemas.document import DocNode, DocumentAST, NodeType
from apex_one.core.schemas.evidence import FactLock


def build_document_ast(nodes: list[DocNode], *, institution: str, cycle: str, synthetic: bool,
                       locks: list[FactLock], voice_version: str) -> DocumentAST:
    root = DocNode(semantic_type=NodeType.DOCUMENT, title_ar=f"دليل APEX: {institution}",
                   title_en=f"APEX Guide: {institution} {cycle}", children=nodes)
    return DocumentAST(title_ar=root.title_ar, title_en=root.title_en, synthetic=synthetic, root=root,
                       voice_version=voice_version, fact_lock_hashes={lk.slot: lk.lock_hash for lk in locks})


def ast_problems(ast: DocumentAST, locks: list[FactLock]) -> list[str]:
    """Structural invariants of a valid AST."""
    problems = []
    lock_claims = {lk.claim_id for lk in locks}
    for n in ast.pages():
        if not n.content:
            problems.append(f"{n.semantic_type}: empty node")
        if not n.first_fixation:
            problems.append(f"{n.semantic_type}: no first fixation")
        for b in n.content:
            for r in b.runs:
                if r.kind == "fact" and r.claim_id not in lock_claims:
                    problems.append(f"{n.semantic_type}: fact run bound to unlocked claim {r.claim_id}")
    for slot, h in ast.fact_lock_hashes.items():
        lk = next((x for x in locks if x.slot == slot), None)
        if lk is None or lk.lock_hash != h:
            problems.append(f"lock {slot} changed after AST creation")
    return problems
