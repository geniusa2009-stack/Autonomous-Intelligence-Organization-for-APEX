"""Phase 17 — APEX Design Model Benchmark: 15 real page types × several design systems, SEPARATE metrics.

Page types: every semantic page type of the Document AST (Cover … Closing). Content comes from a real pipeline run
(the golden job's AST + fact locks); types the job did not produce are built from the same locks.

Systems compared (each produces ONE page per type; all are rendered by the same Chromium and measured by the same
deterministic page QA, so the comparison is apples to apples):

* ``native-baseline``    — APEX compiler, fixed default genes (editorial-column), no search.
* ``native-tournament``  — APEX compiler + layout search (population/generations as in quality mode ULTRA).
* ``llm:<model_id>``     — a local open-weight model writes the page HTML itself under the same APEX DOM contract
                           (section.page / [data-block] / [data-slot]); purpose=evaluation (licence UNKNOWN models may
                           be MEASURED but never ship content).

No single score is produced: every metric is reported per system (mean, min, pages below target) next to the number
of critical failures, contract violations and generation latency.
"""

from __future__ import annotations

import json
import re
import statistics
import time
from pathlib import Path
from typing import Any

from apex_one.core.schemas.design import Genes
from apex_one.core.schemas.document import Block, DocNode, NodeType, ReadingMode
from apex_one.document.ast.runs import parse_runs

METRICS = ["design.hierarchy", "design.typography", "design.brand_fit", "rtl.quality", "accessibility.contrast",
           "fact.critical_accuracy", "geometry.alignment", "geometry.whitespace_ratio"]
PAGE_TYPES = [t for t in NodeType if t != NodeType.DOCUMENT]


def _extra_node(ntype: NodeType, locks: dict) -> DocNode:
    def blk(role: str, tpl: str, **data: Any) -> Block:
        return Block(role=role, runs=parse_runs(tpl, locks, base_lang="ar"), data=data)

    if ntype == NodeType.COMPARISON:
        content = [blk("heading", "تقارنها بإيه؟"),
                   blk("paragraph", "الفرق الأساسي بين الفرصة دي وأي منحة تانية إنك بتشتغل جوه الكلية وبتتعلم مجاناً."),
                   blk("list_item", "المصاريف: شبه صفر مقابل مصاريف كاملة في أغلب الجامعات."),
                   blk("list_item", "الشغل: إجباري هنا، واختياري في أماكن تانية."),
                   blk("list_item", "المنافسة: عالية جداً عشان الأماكن قليلة.")]
        reading = ReadingMode.SCAN
    else:
        content = [blk("kicker", "حكاية طالب"), blk("heading", "إزاي واحد زيك وصل؟"),
                   blk("paragraph", "طالب من إسكندرية بدأ يحضّر من تانية ثانوي، رتّب جوابات التوصية بدري، وكتب الـ [[essay]] "
                                    "عن مشروع صغير عمله في الحي بتاعه."),
                   blk("paragraph", "السر مكانش في الدرجات بس، كان في إنه فهم الكلية عايزة إيه وكتب بصدق.")]
        reading = ReadingMode.READ
    for i, b in enumerate(content):        # deterministic ids: re-measurement must find the same blocks
        b.block_id = f"B-bench-{ntype.value}-{i}"
    n = DocNode(node_id=f"N-bench-{ntype.value}", semantic_type=ntype, content=content, reading_mode=reading,
                importance=3)
    n.first_fixation = next(b.block_id for b in content if b.role == "heading")
    return n


def bench_nodes(ast_pages: list[DocNode], locks: dict) -> list[DocNode]:
    by_type: dict[NodeType, DocNode] = {}
    for n in ast_pages:
        by_type.setdefault(n.semantic_type, n)
    return [by_type.get(t) or _extra_node(t, locks) for t in PAGE_TYPES]


def _baseline_genes(node: DocNode) -> Genes:
    tone = "dark" if node.semantic_type in (NodeType.COVER, NodeType.CLOSING) else "light"
    return Genes(archetype="cover-monument" if node.semantic_type == NodeType.COVER else "editorial-column",
                 column_structure="12", base_font_px=16.0, type_scale_ratio=1.333, density=0.5, whitespace=0.5,
                 margin_mm=18.0, tone=tone, visual_metaphor="none", section_division="space")


# ---------------------------------------------------------------- LLM HTML generator (evaluation only)

def _plain(block: Block, locks: dict) -> str:
    out = []
    for r in block.runs:
        if r.kind == "fact" and r.slot in locks:
            lk = locks[r.slot]
            txt = lk.display_en if r.display == "en" else lk.display_ar
            # the SAME fact markup the native compiler emits, so the model only has to copy it verbatim and the
            # lock-integrity check measures the model, not a missing attribute in our prompt
            out.append(f'<span class="fact" data-slot="{r.slot}" data-claim="{r.claim_id or lk.claim_id}" '
                       f'data-lock-hash="{lk.lock_hash}" data-display="{r.display}">{txt}</span>')
        elif r.kind in ("term", "url") or r.lang == "en":
            out.append(f'<bdi dir="ltr" lang="en">{r.text}</bdi>')
        else:
            out.append(r.text)
    label = block.data.get("label")
    return (f"[{label}] " if label else "") + "".join(out)


def llm_prompt(node: DocNode, locks: dict, palette: dict[str, str], fonts: dict[str, str]) -> str:
    blocks = "\n".join(f'- data-block="{b.block_id}" data-role="{b.role}": {_plain(b, locks)}' for b in node.content)
    return (
        "You are the art director of APEX, a premium Egyptian student-guide publisher. Design ONE A4 page "
        "(794x1123 CSS px, fixed size, overflow hidden) as HTML. Arabic, right-to-left.\n"
        f"Page type: {node.semantic_type.value}. Reading mode: {node.reading_mode.value}.\n"
        f"Brand palette ONLY: {json.dumps(palette)}. Fonts: {json.dumps(fonts)}.\n"
        f"The reader's eye must land FIRST on block {node.first_fixation} (make it the dominant element).\n"
        "Rules: no gradients, no rounded cards, no icons, no emojis; deep navy / silver / white; strong typographic "
        "hierarchy; one clear first fixation; generous margins (>= 15 mm).\n"
        "CONTRACT (mandatory): output exactly one <section class=\"page\" dir=\"rtl\" lang=\"ar\"> element containing a "
        "<div class=\"page-body\">. Put EVERY content block below in its own element carrying the given data-block and "
        "data-role attributes, with the text EXACTLY as given (keep every <span class=\"fact\" ...> and <bdi> element "
        "unchanged). You may add a <style> element inside the section; select only descendants of .page. "
        "End the page with <footer data-brand=\"footer\">APEX</footer>.\n"
        f"Content blocks:\n{blocks}\n"
        "Return ONLY the HTML of the section.")


NEUTRAL_CSS = ("*{box-sizing:border-box}html,body{margin:0;padding:0;background:#ECEFF3}"
               ".page{position:relative;width:210mm;height:297mm;overflow:hidden;background:#FFFFFF;"
               "font-family:'IBM Plex Sans Arabic',sans-serif;color:#0B1424;margin:0 auto}")


def neutral_document(section: str) -> str:
    """A model-written page is rendered on a NEUTRAL canvas: brand fonts + an A4 page box, none of the native
    layout rules (the native `.page-body` 12-column grid would otherwise re-lay-out the model's markup and the
    bench would measure APEX's CSS, not the model's design)."""
    from apex_one.document.compiler.styles import font_css

    return ('<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>model page</title>'
            f"<style>{font_css()}{NEUTRAL_CSS}</style></head><body>{section}</body></html>")


def rewrap_llm_pages(job_id: str, out_dir: Path) -> int:
    """Re-render already generated model pages on the neutral canvas (no model is re-run) and append fresh rows."""
    rows_path = out_dir / "apex_design_bench_rows.jsonl"
    rows = [json.loads(x) for x in rows_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    latest = {(r["system"], r["page_type"]): r for r in rows if r["system"].startswith("llm:") and r["produced"]}
    if not latest:
        return 0
    from apex_one.core.governor.runner import JobRunner
    from apex_one.design.genome import load_genome
    from apex_one.qa.deterministic import page_qa
    from apex_one.vision.render import Renderer

    runner, genome = JobRunner.load(job_id), load_genome()
    nodes = {n.semantic_type.value: n for n in bench_nodes(runner._ast().pages(), {lk.slot: lk for lk in runner.locks})}
    n = 0
    with Renderer() as r:
        for (system, ptype), row in latest.items():
            path = out_dir / f"{ptype}--llm-{re.sub(r'[^a-z0-9]+', '-', system[4:].lower())}.html"
            if not path.exists():
                continue
            section = extract_section(path.read_text(encoding="utf-8"))
            if not section:
                continue
            path.write_text(neutral_document(section), encoding="utf-8")
            res = r.measure(path, float(genome.invariants["page"]["min_margin_mm"]), screenshot_dir=out_dir / "shots",
                            screenshot_prefix=path.stem)
            if not res.metrics.get("pages"):
                continue
            node = nodes[ptype]
            res.metrics["pages"][0]["firstFixation"] = res.metrics["pages"][0].get("firstFixation") or node.first_fixation
            pq = page_qa(res.metrics["pages"][0], genome, runner.locks, allowed_years=runner.allowed_years,
                         fonts_loaded=res.metrics.get("fonts", []), html_dir=res.metrics.get("htmlDir", "rtl"))
            new = {**row, "metrics": {m: (pq.metrics[m].value if m in pq.metrics else None) for m in METRICS},
                   "critical": bool(pq.critical), "detail": f"{row.get('detail', '')}; re-measured on neutral canvas"}
            with rows_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(new, ensure_ascii=False, default=str) + "\n")
            n += 1
    return n


def extract_section(text: str) -> str | None:
    m = re.search(r"<section\b.*</section>", text, re.S | re.I)
    return m.group(0) if m else None


def contract_problems(section: str, node: DocNode) -> list[str]:
    probs = []
    if 'class="page' not in section:
        probs.append("missing section.page")
    if "page-body" not in section:
        probs.append("missing .page-body")
    missing = [b.block_id for b in node.content if b.block_id not in section]
    if missing:
        probs.append(f"{len(missing)}/{len(node.content)} content blocks missing")
    if re.search(r"<script", section, re.I):
        probs.append("contains <script>")
    return probs


# ---------------------------------------------------------------- runner

def _summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    systems: dict[str, Any] = {}
    for sysname in sorted({r["system"] for r in rows}):
        rs = [r for r in rows if r["system"] == sysname]
        infra = [r for r in rs if r.get("outcome_class") == "INFRASTRUCTURE_ERROR"]
        rs = [r for r in rs if r not in infra]       # a failed call is not a bad page: never counted as critical
        entry: dict[str, Any] = {"pages": len(rs), "produced": sum(1 for r in rs if r["produced"]),
                                 "infrastructure_errors": len(infra),
                                 "critical_pages": sum(1 for r in rs if r["critical"]),
                                 "contract_violations": sum(1 for r in rs if r["contract"]),
                                 "median_latency_s": statistics.median([r["latency_s"] for r in rs]) if rs else None,
                                 "execution": sorted({r.get("execution", "interleaved") for r in rs}),
                                 "metrics": {}}
        for m in METRICS:
            vals = [r["metrics"].get(m) for r in rs if r["metrics"].get(m) is not None]
            entry["metrics"][m] = {"mean": round(statistics.mean(vals), 1) if vals else None,
                                   "min": round(min(vals), 1) if vals else None, "measured_pages": len(vals),
                                   "below_90": sum(1 for v in vals if v < 90)}
        systems[sysname] = entry
    return systems


def run_apex_design_bench(job_id: str, out_dir: Path, llm_models: list[str] | None = None, *,
                          population: int = 10, generations: int = 4, initial: int = 32,
                          only_types: list[str] | None = None, include_native: bool = True,
                          phase: str = "interleaved") -> dict[str, Any]:
    """phase="interleaved": model call then render, page by page (model and Chromium resident together).
    phase="generate": model calls only, sections saved under llm_sections/ — no Chromium is started.
    phase="render": no model call; render + measure the saved sections (run after the model was unloaded).
    The two-phase path is the resource scheduler's sequential strategy for models too large to share RAM with
    Chromium; the prompt, budget and measurements are identical."""
    from apex_one.compute.broker import ComputeBroker
    from apex_one.compute.providers import ChatMessage
    from apex_one.core.governor.runner import JobRunner
    from apex_one.core.schemas.compute import CapabilityRequest
    from apex_one.design.genome import load_genome
    from apex_one.design.tournament import LayoutTournament
    from apex_one.document.compiler import compile_document, compile_page
    from apex_one.qa.deterministic import page_qa
    from apex_one.vision.render import Renderer, ensure_fonts

    runner = JobRunner.load(job_id)
    genome = load_genome()
    lock_map = {lk.slot: lk for lk in runner.locks}
    nodes = bench_nodes(runner._ast().pages(), lock_map)
    if only_types:
        nodes = [n for n in nodes if n.semantic_type.value in only_types]
    out_dir.mkdir(parents=True, exist_ok=True)
    ensure_fonts(out_dir)
    total = len(nodes)
    palette = genome.invariants["palette"]
    fonts = genome.invariants["fonts"]
    broker = ComputeBroker() if llm_models and phase != "render" else None
    rows: list[dict[str, Any]] = []
    rows_path = out_dir / "apex_design_bench_rows.jsonl"
    done = {(r["system"], r["page_type"]) for r in (json.loads(x) for x in rows_path.read_text(encoding="utf-8")
                                                    .splitlines() if x.strip())} if rows_path.exists() else set()

    def measure(r: Renderer, html: str, name: str, node: DocNode) -> tuple[dict[str, float | None], bool, Path | None]:
        path = out_dir / f"{name}.html"
        path.write_text(html, encoding="utf-8")
        res = r.measure(path, float(genome.invariants["page"]["min_margin_mm"]), screenshot_dir=out_dir / "shots",
                        screenshot_prefix=name)
        if not res.metrics.get("pages"):
            return {}, True, None
        res.metrics["pages"][0]["firstFixation"] = res.metrics["pages"][0].get("firstFixation") or node.first_fixation
        pq = page_qa(res.metrics["pages"][0], genome, runner.locks, allowed_years=runner.allowed_years,
                     fonts_loaded=res.metrics.get("fonts", []), html_dir=res.metrics.get("htmlDir", "rtl"))
        shot = res.page_screenshots[0] if res.page_screenshots else None
        return ({m: (pq.metrics[m].value if m in pq.metrics else None) for m in METRICS}, bool(pq.critical), shot)

    def record(row: dict[str, Any]) -> None:
        rows.append(row)
        with rows_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    sections_dir = out_dir / "llm_sections"
    if phase == "generate":
        sections_dir.mkdir(parents=True, exist_ok=True)
        for node in nodes:
            ptype = node.semantic_type.value
            for mid in llm_models or []:
                slug = re.sub(r"[^a-z0-9]+", "-", mid.lower())
                target = sections_dir / f"{ptype}--llm-{slug}.json"
                if (f"llm:{mid}", ptype) in done or target.exists():
                    continue
                t0 = time.perf_counter()
                req = CapabilityRequest(task="bench.design_html", purpose="evaluation", model_id=mid)
                res = broker.complete(req, [ChatMessage("user", llm_prompt(node, lock_map, palette, fonts))],  # type: ignore[union-attr]
                                      max_tokens=3000, temperature=0.2, timeout=1800)
                from apex_one.compute.benchmark.council import call_failure_kind

                target.write_text(json.dumps({"model": mid, "page_type": ptype, "executed": res.executed,
                                              "text": res.text or "", "latency_s": round(time.perf_counter() - t0, 1),
                                              "failure_kind": None if res.executed else call_failure_kind(res),
                                              "outcome": res.decision.outcome.value}, ensure_ascii=False),
                                  encoding="utf-8")
        return {"phase": "generate", "sections": sorted(p.name for p in sections_dir.glob("*.json"))}

    def model_output(mid: str, node: DocNode) -> tuple[bool, str, float, str | None, str]:
        ptype = node.semantic_type.value
        if phase == "render":
            d = json.loads((sections_dir / f"{ptype}--llm-{re.sub(r'[^a-z0-9]+', '-', mid.lower())}.json")
                           .read_text(encoding="utf-8"))
            return d["executed"], d["text"], d["latency_s"], d.get("failure_kind"), d["outcome"]
        from apex_one.compute.benchmark.council import call_failure_kind

        t0 = time.perf_counter()
        req = CapabilityRequest(task="bench.design_html", purpose="evaluation", model_id=mid)
        res = broker.complete(req, [ChatMessage("user", llm_prompt(node, lock_map, palette, fonts))],  # type: ignore[union-attr]
                              max_tokens=3000, temperature=0.2, timeout=1800)
        return (res.executed, res.text or "", round(time.perf_counter() - t0, 1),
                None if res.executed else call_failure_kind(res), res.decision.outcome.value)

    with Renderer() as r:
        t = LayoutTournament(genome, runner.locks, r, out_dir / "tournament", population=population,
                             generations=generations, elite=2, epsilon=0.5, seed=runner.job.policy.seed,
                             synthetic=runner.synthetic, allowed_years=runner.allowed_years)
        for i, node in enumerate(nodes, 1):
            ptype = node.semantic_type.value
            # baseline
            t0 = time.perf_counter()
            page = compile_page(node, _baseline_genes(node), genome, lock_map, page_no=i, total_pages=total,
                                synthetic=runner.synthetic, seed=7)
            base_html = compile_document([page], genome, title=f"bench-{ptype}", synthetic=runner.synthetic)
            if include_native:
                mets, crit, shot = measure(r, base_html, f"{ptype}--native-baseline", node)
                record({"system": "native-baseline", "page_type": ptype, "produced": True, "metrics": mets,
                        "critical": crit, "contract": [], "latency_s": round(time.perf_counter() - t0, 1),
                        "screenshot": str(shot) if shot else None, "detail": "editorial-column defaults"})
                # tournament
                t0 = time.perf_counter()
                out = t.run_page(node, i, total, [], initial=initial)
                best = out.best
                page = compile_page(node, best.genes, genome, lock_map, page_no=i, total_pages=total,
                                    synthetic=runner.synthetic, seed=runner.job.policy.seed + i)
                html = compile_document([page], genome, title=f"bench-{ptype}", synthetic=runner.synthetic)
                mets, crit, shot = measure(r, html, f"{ptype}--native-tournament", node)
                record({"system": "native-tournament", "page_type": ptype, "produced": True, "metrics": mets,
                        "critical": crit, "contract": [], "latency_s": round(time.perf_counter() - t0, 1),
                        "screenshot": str(shot) if shot else None,
                        "detail": f"{best.genes.archetype}/{best.genes.tone}; evaluated {out.evaluated}"})
            # local LLM page generators
            for mid in llm_models or []:
                if (f"llm:{mid}", ptype) in done:     # resumable: a measured (system, page) is never re-run
                    continue
                executed, text, lat, fk, outcome = model_output(mid, node)
                if not executed:     # the CALL failed: infrastructure, never a bad page
                    record({"system": f"llm:{mid}", "page_type": ptype, "produced": False, "metrics": {},
                            "critical": False, "contract": [], "latency_s": lat, "screenshot": None,
                            "outcome_class": "INFRASTRUCTURE_ERROR", "failure_kind": fk or "UNKNOWN_FAILURE",
                            "execution": phase, "detail": outcome})
                    continue
                section = extract_section(text)
                if section is None:
                    record({"system": f"llm:{mid}", "page_type": ptype, "produced": False, "metrics": {},
                            "critical": True, "contract": ["no <section> produced"], "latency_s": lat,
                            "screenshot": None, "outcome_class": "QUALITY_ZERO", "execution": phase,
                            "detail": text[:300]})
                    continue
                probs = contract_problems(section, node)
                html = neutral_document(section)
                mets, crit, shot = measure(r, html, f"{ptype}--llm-{re.sub(r'[^a-z0-9]+', '-', mid.lower())}", node)
                record({"system": f"llm:{mid}", "page_type": ptype, "produced": True, "metrics": mets,
                        "critical": crit, "contract": probs, "latency_s": lat, "outcome_class": "MEASURED",
                        "execution": phase, "screenshot": str(shot) if shot else None,
                        "detail": f"{len(section)} chars"})
    latest_rows = {(r["system"], r["page_type"]): r for r in
                   (json.loads(x) for x in rows_path.read_text(encoding="utf-8").splitlines() if x.strip())}
    all_rows = list(latest_rows.values())          # a re-measured (system, page) replaces its older row
    summary = {"job_id": job_id, "page_types": sorted({r["page_type"] for r in all_rows}),
               "systems": _summarise(all_rows), "rows": len(all_rows),
               "note": "separate metrics per system; no single aggregate score by design"}
    (out_dir / "apex_design_bench.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary
