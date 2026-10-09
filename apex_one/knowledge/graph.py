"""Knowledge graph: relational storage, graph-like traversal."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, select

from apex_one.knowledge.ontology import PREDICATE_ENTITY, EntityType, Relation


@dataclass
class KGNode:
    node_id: str
    entity_type: EntityType
    label: str
    data: dict[str, Any] = field(default_factory=dict)


class KnowledgeGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, KGNode] = {}
        self.out: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self.inc: dict[str, list[tuple[str, str]]] = defaultdict(list)

    def add_node(self, node_id: str, etype: EntityType, label: str, **data: Any) -> KGNode:
        n = self.nodes.get(node_id)
        if n is None:
            n = self.nodes[node_id] = KGNode(node_id, etype, label, dict(data))
        else:
            n.data.update(data)
        return n

    def add_edge(self, src: str, rel: Relation | str, dst: str) -> None:
        if (str(rel), dst) not in self.out[src]:
            self.out[src].append((str(rel), dst))
            self.inc[dst].append((str(rel), src))

    def neighbors(self, node_id: str, rel: str | None = None, direction: str = "out") -> list[KGNode]:
        edges = self.out[node_id] if direction == "out" else self.inc[node_id]
        return [self.nodes[d] for r, d in edges if rel is None or r == rel]

    def of_type(self, etype: EntityType) -> list[KGNode]:
        return [n for n in self.nodes.values() if n.entity_type == etype]

    def path(self, a: str, b: str, max_depth: int = 6) -> list[str] | None:
        seen, q = {a}, deque([[a]])
        while q:
            p = q.popleft()
            if p[-1] == b:
                return p
            if len(p) > max_depth:
                continue
            for _, d in self.out[p[-1]] + self.inc[p[-1]]:
                if d not in seen:
                    seen.add(d)
                    q.append(p + [d])
        return None

    def provenance(self, node_id: str) -> list[KGNode]:
        """Fact node -> claims -> evidence -> sources."""
        out = []
        for claim in self.neighbors(node_id, Relation.ASSERTED_BY):
            for ev in self.neighbors(claim.node_id, Relation.SUPPORTED_BY):
                out += self.neighbors(ev.node_id, Relation.FROM_SOURCE)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": [{"id": n.node_id, "type": n.entity_type.value, "label": n.label, "data": n.data}
                          for n in self.nodes.values()],
                "edges": [{"src": s, "rel": r, "dst": d} for s, lst in self.out.items() for r, d in lst]}

    # ---------- persistence (relational) ----------
    def save(self, job_id: str, db_url: str | None = None) -> None:
        from apex_one.persistence.db import session_scope
        from apex_one.persistence.models import KGEdgeRow, KGNodeRow

        with session_scope(db_url) as s:
            s.execute(delete(KGEdgeRow).where(KGEdgeRow.job_id == job_id))
            s.execute(delete(KGNodeRow).where(KGNodeRow.job_id == job_id))
            for n in self.nodes.values():
                s.add(KGNodeRow(node_id=f"{job_id}:{n.node_id}", entity_type=n.entity_type.value, label=n.label[:2000],
                                job_id=job_id, payload=n.data))
            for src, lst in self.out.items():
                for rel, dst in lst:
                    s.add(KGEdgeRow(src=f"{job_id}:{src}", rel=rel, dst=f"{job_id}:{dst}", job_id=job_id, payload={}))

    @classmethod
    def load(cls, job_id: str, db_url: str | None = None) -> "KnowledgeGraph":
        from apex_one.persistence.db import session_scope
        from apex_one.persistence.models import KGEdgeRow, KGNodeRow

        g = cls()
        pre = f"{job_id}:"
        with session_scope(db_url) as s:
            for r in s.execute(select(KGNodeRow).where(KGNodeRow.job_id == job_id)).scalars():
                g.add_node(r.node_id.removeprefix(pre), EntityType(r.entity_type), r.label, **(r.payload or {}))
            for e in s.execute(select(KGEdgeRow).where(KGEdgeRow.job_id == job_id)).scalars():
                g.add_edge(e.src.removeprefix(pre), e.rel, e.dst.removeprefix(pre))
        return g


def build_graph_from_research(state, mission) -> KnowledgeGraph:
    g = KnowledgeGraph()
    opp = g.add_node("opportunity", EntityType.OPPORTUNITY, mission.opportunity_name, cycle=mission.cycle)
    inst = g.add_node("institution", EntityType.INSTITUTION, mission.institution or mission.opportunity_name)
    prog = g.add_node("program", EntityType.PROGRAM, f"{mission.cycle or ''} entry".strip())
    g.add_edge(opp.node_id, Relation.OFFERED_BY, inst.node_id)
    g.add_edge(opp.node_id, Relation.FOR_PROGRAM, prog.node_id)
    for s in state.sources:
        g.add_node(s.source_id, EntityType.SOURCE, s.url, kind=s.kind.value, authority=s.authority, cycle=s.cycle_year)
    for e in state.evidence:
        g.add_node(e.evidence_id, EntityType.EVIDENCE, e.quote[:200], locator=e.locator)
        g.add_edge(e.evidence_id, Relation.FROM_SOURCE, e.source_id)
    for c in state.claims:
        g.add_node(c.claim_id, EntityType.CLAIM, f"{c.slot}={c.value.canonical}", status=c.status.value)
        for eid in c.evidence_ids:
            g.add_edge(c.claim_id, Relation.SUPPORTED_BY, eid)
    for x in state.contradictions:
        for a in x.claim_ids:
            for b in x.claim_ids:
                if a < b:
                    g.add_edge(a, Relation.CONTRADICTS, b)
    deadlines = []
    for lk in state.locks:
        etype, rel = PREDICATE_ENTITY.get(lk.predicate, (EntityType.CLAIM, Relation.HAS_ELIGIBILITY))
        fid = f"fact:{lk.slot}"
        g.add_node(fid, etype, f"{lk.slot}: {lk.display_en}", slot=lk.slot, value=lk.value.canonical, locked=True)
        g.add_edge(opp.node_id, rel, fid)
        g.add_edge(fid, Relation.ASSERTED_BY, lk.claim_id)
        if etype == EntityType.DEADLINE:
            deadlines.append((lk.value.canonical, fid))
        if lk.predicate == "country_eligibility":
            g.add_node("country:all", EntityType.COUNTRY, "All countries (incl. Egypt)")
            g.add_edge(fid, Relation.OPEN_TO, "country:all")
    deadlines.sort()
    prev = None
    for i, (_, fid) in enumerate(deadlines):
        step = g.add_node(f"step:{i + 1}", EntityType.APPLICANT_STEP, f"Step {i + 1}: {g.nodes[fid].label}")
        g.add_edge(opp.node_id, Relation.HAS_STEP, step.node_id)
        g.add_edge(step.node_id, Relation.HAS_DEADLINE, fid)
        if prev:
            g.add_edge(prev, Relation.PRECEDES, step.node_id)
        prev = step.node_id
    return g
