"""Phase 9 — model-written pages vs the native APEX layout system, measured SEPARATELY (no single score).

Re-renders every page the APEX design bench saved (no model is re-run) and measures, per (system, page type):

  text_fidelity        content blocks rendered with the words they were given (order-independent recall, %)
  fact_preservation    locked facts present with the exact locked display text (%)
  html_validity        100 − 10 × HTML parse errors in the page section
  css_validity         100 − 10 × CSS parse errors (section <style> blocks + inline style attributes)
  rtl                  rtl.quality from the deterministic page QA
  overflow_issues      count of overflow / clipping / page-bounds issues
  visual_hierarchy     design.hierarchy (DOM saliency)
  editability          share of contract content blocks present as addressable [data-block] elements (%);
                       inline_styles reported alongside
  novelty_vs_native    100 × (1 − layout similarity to the native-baseline page of the same type)
  apex_similarity      brand similarity (palette, brand fonts, signature, no cards) × 100
  reader_comprehension extractive reader simulation over this page's own facts (NOT_MEASURED if it has none)
and, per system, layout_repetition = mean pairwise layout similarity between its pages (lower = less repetitive).

Decision rule: a model-backed system is preferred only where it measurably beats native on a metric without
losing on fact preservation, RTL, overflow or text fidelity. Otherwise native stays.
"""

from __future__ import annotations

import json
import re
import statistics
from itertools import combinations
from pathlib import Path
from typing import Any

import tinycss2
from lxml import etree

SAFETY = ("fact_preservation", "rtl", "text_fidelity")
OVERFLOW_CHECKS = {"qa.overflow", "qa.clipping", "qa.page_bounds", "qa.collision"}


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t)).strip()


def _words(t: str) -> list[str]:
    t = re.sub(r"\[\[([^\]]+)\]\]", r"\1", _norm(t))          # [[term]] markup -> term
    # DOM innerText can glue adjacent elements («2026آخر»): split where Arabic meets digits/Latin
    t = re.sub(r"(?<=[0-9A-Za-z%$])(?=[\u0600-\u06FF])|(?<=[\u0600-\u06FF])(?=[0-9A-Za-z%$])", " ", t)
    return re.findall(r"[\w\u0600-\u06FF%$.,/:-]+", t.replace("[", " ").replace("]", " "))


def word_recall(expected: str, got: str) -> float:
    """Share of the expected words (multiset) present in the rendered block — order-independent, because a layout
    may legitimately place a step's label after its value."""
    from collections import Counter

    e, g = Counter(_words(expected)), Counter(_words(got))
    total = sum(e.values())
    return sum(min(n, g[w]) for w, n in e.items()) / total if total else 1.0


def accepted_texts(lock, fact: dict[str, Any]) -> set[str]:
    """Exact lock displays, plus the lock-defined conditional wording for boolean facts (data-cond "yes|no")."""
    ok = {_norm(lock.display_ar), _norm(lock.display_en)}
    cond = fact.get("cond")
    if cond and "|" in cond:
        yes, no = cond.split("|", 1)
        ok.add(_norm(yes if str(lock.value.canonical).lower() == "true" else no))
    return ok


def _section(html: str) -> str:
    i = html.find('<section class="page')
    if i < 0:
        i = html.find("<section")
    j = html.find("</section>", i)
    return html[i:j + 10] if i >= 0 and j > 0 else ""


def html_errors(section: str) -> int:
    parser = etree.HTMLParser(recover=True)
    etree.fromstring(f"<html><body>{section}</body></html>", parser)
    return sum(1 for e in parser.error_log if e.level_name in ("ERROR", "FATAL"))


def css_errors(section: str) -> tuple[int, int]:
    errs, inline = 0, 0
    for block in re.findall(r"<style[^>]*>(.*?)</style>", section, re.S | re.I):
        for rule in tinycss2.parse_stylesheet(block, skip_whitespace=True, skip_comments=True):
            if rule.type == "error":
                errs += 1
            elif rule.type == "qualified-rule":
                errs += sum(1 for d in tinycss2.parse_declaration_list(rule.content, skip_whitespace=True)
                            if d.type == "error")
    for style in re.findall(r'\sstyle="([^"]*)"', section):
        inline += 1
        errs += sum(1 for d in tinycss2.parse_declaration_list(style, skip_whitespace=True) if d.type == "error")
    return errs, inline


def _slug(system: str) -> str:
    if system.startswith("llm:"):
        return "llm-" + re.sub(r"[^a-z0-9]+", "-", system[4:].lower())
    return system


def remeasure(job_id: str, bench_dir: Path) -> list[dict[str, Any]]:
    from apex_one.core.governor.runner import JobRunner
    from apex_one.design.genome import load_genome
    from apex_one.design.similarity import brand_similarity, grid_iou, occupancy_grid
    from apex_one.lab.benchmarks.apex_design_bench import _plain, bench_nodes
    from apex_one.qa.deterministic import page_qa
    from apex_one.reader_lab.personas import load_personas
    from apex_one.reader_lab.simulator import ReaderSimulator, ReadItem
    from apex_one.vision.render import Renderer

    runner = JobRunner.load(job_id)
    genome = load_genome()
    lock_map = {lk.slot: lk for lk in runner.locks}
    nodes = {n.semantic_type.value: n for n in bench_nodes(runner._ast().pages(), lock_map)}
    rows_path = bench_dir / "apex_design_bench_rows.jsonl"
    rows = [json.loads(x) for x in rows_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    latest = {(r["system"], r["page_type"]): r for r in rows}
    personas = load_personas()
    out: list[dict[str, Any]] = []
    grids: dict[tuple[str, str], list[int]] = {}
    with Renderer() as r:
        for (system, ptype), row in sorted(latest.items()):
            html_path = bench_dir / f"{ptype}--{_slug(system)}.html"
            rec: dict[str, Any] = {"system": system, "page_type": ptype, "produced": row["produced"]}
            if not row["produced"] or not html_path.exists():
                rec["note"] = "no page produced" if not row["produced"] else "html not saved"
                out.append(rec)
                continue
            node = nodes[ptype]
            html = html_path.read_text(encoding="utf-8")
            section = _section(html)
            res = r.measure(html_path, float(genome.invariants["page"]["min_margin_mm"]))
            if not res.metrics.get("pages"):
                rec["note"] = "rendered no page"
                out.append(rec)
                continue
            page = res.metrics["pages"][0]
            # the intended entry point is part of the brief, not of the markup: measure every system against it
            page["firstFixation"] = page.get("firstFixation") or node.first_fixation
            pq = page_qa(page, genome, runner.locks, allowed_years=runner.allowed_years,
                         fonts_loaded=res.metrics.get("fonts", []), html_dir=res.metrics.get("htmlDir", "rtl"))
            items = {i["id"]: i for i in page["items"]}
            ratios = []
            for b in node.content:
                it = items.get(b.block_id)
                ratios.append(0.0 if it is None else word_recall(_plain(b, lock_map),
                                                                 it.get("diffText") or it["text"]))
            slots = {run.slot for b in node.content for run in b.runs if run.kind == "fact" and run.slot in lock_map}
            ok_facts = sum(1 for s in slots if any(f["slot"] == s and _norm(f["text"]) in accepted_texts(lock_map[s], f)
                                                   for f in page["facts"]))
            css_err, inline = css_errors(section)
            grid = occupancy_grid(page)
            grids[(system, ptype)] = grid
            sim = ReaderSimulator(runner.locks, sorted(slots))
            ritems = [ReadItem(i["text"], 1, i["fontPx"], i["lang"], {"heading": "heading", "stat": "stat",
                                                                        "hero": "stat"}.get(i["role"], i["role"]),
                               [f["slot"] for f in page["facts"] if i["y"] - 2 <= f["y"] <= i["y"] + i["h"] + 2])
                      for i in sorted(page["items"], key=lambda i: (i["y"], -i["x"]))]
            # page level: only this page's own facts (the document-level "next action / main risk / deadline"
            # questions belong to the whole guide, not to one page)
            comp_vals = []
            for persona in personas if slots else []:
                ans = [a for a in sim.simulate(persona, ritems).answers if a.slot is not None]
                comp_vals.append(100.0 * sum(a.correct for a in ans) / len(ans) if ans else 0.0)
            comp = statistics.mean(comp_vals) if comp_vals else None
            rec.update({
                "text_fidelity": round(100 * statistics.mean(ratios), 1) if ratios else None,
                "fact_preservation": round(100 * ok_facts / len(slots), 1) if slots else None,
                "html_validity": max(0, 100 - 10 * html_errors(section)),
                "css_validity": max(0, 100 - 10 * css_err), "inline_styles": inline,
                "rtl": (pq.metrics.get("rtl.quality").value if pq.metrics.get("rtl.quality") else None),
                "overflow_issues": sum(1 for i in pq.issues if i.check in OVERFLOW_CHECKS and i.severity != "minor"),
                "visual_hierarchy": pq.metrics["design.hierarchy"].value,
                "editability": round(100 * sum(1 for b in node.content if b.block_id in items) / len(node.content), 1),
                "apex_similarity": round(100 * brand_similarity(page, genome.invariants, res.metrics.get("fonts", [])), 1),
                "reader_comprehension": round(comp, 1) if comp is not None else None,
                "critical_issues": len(pq.critical),
            })
            out.append(rec)
    for rec in out:
        base = grids.get(("native-baseline", rec["page_type"]))
        mine = grids.get((rec["system"], rec["page_type"]))
        if base and mine and rec["system"] != "native-baseline":
            rec["novelty_vs_native"] = round(100 * (1 - grid_iou(mine, base)), 1)
    repetition = {}
    for system in {s for s, _ in grids}:
        gs = [g for (s, _), g in grids.items() if s == system]
        pairs = [grid_iou(a, b) for a, b in combinations(gs, 2)]
        repetition[system] = round(100 * statistics.mean(pairs), 1) if pairs else None
    result = {"rows": out, "layout_repetition": repetition}
    (bench_dir / "page_compare.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


METRICS = ["text_fidelity", "fact_preservation", "html_validity", "css_validity", "rtl", "overflow_issues",
           "visual_hierarchy", "editability", "novelty_vs_native", "apex_similarity", "reader_comprehension"]
LOWER_IS_BETTER = {"overflow_issues"}


def verdicts(result: dict[str, Any], native: str = "native-tournament") -> dict[str, Any]:
    """Per model system: where it beats native WITHOUT losing a safety metric; otherwise keep native."""
    by: dict[str, dict[str, dict[str, Any]]] = {}
    for r in result["rows"]:
        by.setdefault(r["system"], {})[r["page_type"]] = r
    out = {}
    for system, pages in by.items():
        if not system.startswith("llm:"):
            continue
        wins, losses, safety_losses = [], [], []
        for ptype, r in pages.items():
            n = by.get(native, {}).get(ptype)
            if not n or not r.get("produced") or "text_fidelity" not in r:
                losses.append(f"{ptype}: no valid page")
                continue
            for m in METRICS:
                a, b = r.get(m), n.get(m)
                if a is None or b is None or m == "novelty_vs_native":
                    continue
                better = a < b if m in LOWER_IS_BETTER else a > b
                worse = a > b if m in LOWER_IS_BETTER else a < b
                if better:
                    wins.append(f"{ptype}:{m}")
                elif worse:
                    (safety_losses if m in SAFETY or m == "overflow_issues" else losses).append(f"{ptype}:{m} {a} vs {b}")
        out[system] = {"wins": wins, "losses": losses, "safety_losses": safety_losses,
                       "decision": ("use only where it wins and never loses safety" if wins and not safety_losses
                                    else "KEEP NATIVE (model page lost on safety metrics or never won)")}
    return out
