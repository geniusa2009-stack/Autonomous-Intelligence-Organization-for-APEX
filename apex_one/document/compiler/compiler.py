"""apex-native-compiler: Document AST + genes -> editable, semantic HTML/CSS.

Facts are rendered from FactLocks with data-slot/data-claim/data-lock-hash so that QA can re-verify the
DOM after rendering. English terms and LTR facts are bidi-isolated. No cards, no gradients, no shadows.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from apex_one.core.schemas.design import DesignGenome, Genes
from apex_one.core.schemas.document import Block, DocNode, TextRun
from apex_one.core.schemas.evidence import FactLock
from apex_one.core.schemas.common import stable_hash
from apex_one.design.assets.svg import bar_fraction_svg, metaphor_svg
from apex_one.document.compiler.styles import base_css, font_css, page_css
from apex_one.release.assets import brand_svg

ARABIC = re.compile(r"[؀-ۿ]")
LTRISH = re.compile(r"[A-Za-z$€£%]")
PAGE_W, PAGE_H = 794, 1123   # CSS px at 96 dpi
HEADER_ROLES = ("kicker", "heading", "lead", "subtitle", "label")


@dataclass
class CompiledPage:
    page_id: str
    node_type: str
    archetype: str
    html: str
    css: str
    signature: str
    provenance: list[str] = field(default_factory=lambda: ["apex-native-compiler", "apex-native-layout"])


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def render_runs(runs: list[TextRun], locks: dict[str, FactLock]) -> str:
    out = []
    for r in runs:
        if r.kind == "fact" and r.slot:
            lk = locks.get(r.slot)
            h = lk.lock_hash if lk else ""
            inner = esc(r.text)
            if LTRISH.search(r.text) or not ARABIC.search(r.text):
                inner = f'<bdi dir="ltr">{inner}</bdi>' if not ARABIC.search(r.text) else f"<bdi>{inner}</bdi>"
            cond = f' data-cond="{esc(r.cond)}"' if r.cond else ""
            out.append(f'<span class="fact" data-slot="{esc(r.slot)}" data-claim="{esc(r.claim_id or "")}" '
                       f'data-lock-hash="{h}" data-display="{esc(r.display)}"{cond}>{inner}</span>')
        elif r.kind == "term":
            out.append(f'<bdi class="term" dir="ltr" lang="en">{esc(r.text)}</bdi>')
        elif r.kind == "url":
            out.append(f'<bdi class="url" dir="ltr" lang="en">{esc(r.text)}</bdi>')
        else:
            out.append(esc(r.text))
    return "".join(out)


def _block_lang(b: Block) -> str:
    """A block is LTR English only when it is explicitly English content (e.g. an official quote) or when
    every run is English and it carries no Arabic label. Numeric values never switch a block to LTR."""
    if b.data.get("lang") == "en":
        return "en"
    if b.role in ("stat", "hero", "figure", "step"):
        return "ar"
    has_ar = any(ARABIC.search(r.text) for r in b.runs) or ARABIC.search(str(b.data.get("label", "")))
    return "ar" if has_ar or not b.runs else ("en" if all(r.lang == "en" for r in b.runs) else "ar")


def render_block(b: Block, locks: dict[str, FactLock], genes: Genes, *, step_no: int | None = None) -> str:
    lang = _block_lang(b)
    dir_attr = ' dir="ltr"' if lang == "en" else ""
    cls = f"blk blk-{b.role}" + (" check" if b.data.get("check") else "") + (" critical" if b.data.get("critical") else "") \
        + (" ff" if b.data.get("first_fixation") else "") + (" stat-text" if b.data.get("textual") else "")
    attrs = f'class="{cls}" data-block="{b.block_id}" data-role="{b.role}" lang="{lang}"{dir_attr}'
    if b.data.get("opinion"):
        attrs += ' data-opinion="1"'
    if b.data.get("humor"):
        attrs += ' data-humor="1"'
    if b.data.get("open_question"):
        attrs += f' data-open-question="{esc(b.data["open_question"])}"'
    body = render_runs(b.runs, locks)
    label = b.data.get("label")
    label_html = render_label(label, locks) if label else ""
    if b.role in ("stat", "hero"):
        return (f'<div {attrs}>{f"<span class=stat-label>{label_html}</span>" if label_html else ""}'
                f'<span class="stat-value">{body}</span></div>')
    if b.role == "step":
        return (f'<div {attrs}><span class="step-date">{body}</span><span class="step-label">{label_html}</span></div>')
    if b.role == "figure":
        viz = bar_fraction_svg(float(b.data.get("value") or 0), "var(--accent)", "var(--rule)") \
            if genes.data_viz != "none" else ""
        return (f'<div {attrs}><span class="stat-value">{body}</span>{viz}'
                f'<span class="stat-label">{label_html}</span></div>')
    if b.role == "heading":
        tag = "h1" if b.data.get("level", 1) == 1 else "h2"
        return f'<{tag} {attrs}>{body}</{tag}>'
    if b.role == "list_item" and step_no is not None and genes.archetype == "checklist-sheet":
        return f'<div {attrs}><span class="item-no fact-free">{step_no:02d}</span> {body}</div>'
    return f'<div {attrs}>{body}</div>'


def render_label(template: str, locks: dict[str, FactLock]) -> str:
    from apex_one.document.ast.runs import parse_runs

    return render_runs(parse_runs(template, locks), locks)


# ----------------------------------------------------------------------------------------------
def _split_cols(genes: Genes) -> tuple[int, int]:
    parts = [int(x) for x in genes.column_structure.split("-")]
    if len(parts) == 2:
        return parts[0], parts[1]
    a = int(round(5 + 3 * genes.asymmetry))   # 5..8 columns
    return a, 12 - a


@dataclass
class Zone:
    name: str
    col_start: int
    col_span: int
    row: int
    blocks: list[Block]
    cls: str = ""
    justify: str = "start"      # start | center | end | space-between


def zones_for(node: DocNode, genes: Genes) -> list[Zone]:
    """Explicit grid placement (RTL grid: column 1 is the right edge). Zones never share cells."""
    blocks = list(node.content)
    head = [b for b in blocks if b.role in HEADER_ROLES]
    rest = [b for b in blocks if b.role not in HEADER_ROLES]
    arch = genes.archetype
    spread = "space-between" if genes.whitespace > 0.55 else "start"
    if arch == "cover-monument":
        top = [b for b in blocks if b.role == "kicker"]
        mid = [b for b in blocks if b.role in ("heading", "subtitle")]
        bottom = [b for b in blocks if b.role in ("stat", "notice")]
        width = 12 if genes.asymmetry < 0.5 else 10
        return [Zone("cover-top", 1, 12, 1, top), Zone("cover-mid", 1, width, 2, mid, justify="center"),
                Zone("cover-bottom", 1, 12, 3, bottom, justify="end")]
    if arch == "hero-number":
        hero = [b for b in blocks if b.role == "hero" or (b.role == "stat" and not any(x.role == "hero" for x in blocks))]
        others = [b for b in blocks if b not in hero]
        span = 8 if genes.asymmetry > 0.4 else 11
        return [Zone("hero", 1, 12, 2, hero, justify="end"), Zone("hero-text", 1, span, 3, others)]
    if arch == "quiet-breath":
        span = 9 if genes.asymmetry > 0.5 else 11
        start = 1 if genes.asymmetry < 0.75 else 12 - span + 1
        return [Zone("breath", start, span, 2, blocks, justify="center")]
    if arch == "manifesto":
        span = 10 if genes.asymmetry < 0.5 else 8
        return [Zone("statement", 1, 12, 2, head, justify="end"), Zone("statement-body", 1, span, 3, rest)]
    if arch in ("ledger", "timeline-rail", "checklist-sheet"):
        band = " band" if genes.section_division == "tone-shift" else ""
        span = 12 if genes.asymmetry < 0.55 else 10
        start = 1 if genes.asymmetry < 0.8 else 3
        return [Zone("header", 1, 12, 1, head, band), Zone("rows", start, span, 2, rest, justify=spread)]
    a, b = _split_cols(genes)
    if arch == "split-asymmetric":
        side = min(max(a, 4), 7)
        return [Zone("side", 1, side, 1, head), Zone("main", side + 1, 12 - side, 1, rest,
                                                     justify="center" if genes.whitespace > 0.6 else "start")]
    # editorial-column
    main_roles = ("paragraph", "list_item", "quote", "warning", "cta", "subheading", "step", "pullquote")
    main = [x for x in rest if x.role in main_roles]
    side = [x for x in rest if x.role not in main_roles]
    band = " band" if genes.section_division == "tone-shift" else ""
    zones = [Zone("header", 1, 12, 1, head, band)]
    if side:
        zones += [Zone("column", 1, a, 2, main), Zone("rail", a + 1, b, 2, side)]
    else:
        zones.append(Zone("column", 1, 12 if genes.density > 0.5 else 10, 2, main))
    return zones


ROW_TEMPLATES = {
    "cover-monument": "auto 1fr auto", "hero-number": "minmax(0,.9fr) auto minmax(0,1fr)",
    "quiet-breath": "1fr auto 1.2fr", "manifesto": "minmax(0,.8fr) auto minmax(0,1fr)",
    "ledger": "auto 1fr", "timeline-rail": "auto 1fr", "checklist-sheet": "auto 1fr",
    "split-asymmetric": "1fr", "editorial-column": "auto 1fr",
}


def structural_signature(node: DocNode, genes: Genes) -> str:
    zones = zones_for(node, genes)
    shape = [genes.archetype, genes.column_structure if genes.archetype in ("editorial-column", "split-asymmetric") else "",
             genes.tone, genes.hero_treatment if genes.archetype == "hero-number" else "",
             "|".join(f"{z.name}:{z.col_start}:{z.col_span}:{len(z.blocks)}" for z in zones)]
    return stable_hash(shape)[:16]


def compile_page(node: DocNode, genes: Genes, genome: DesignGenome, locks: dict[str, FactLock], *,
                 page_no: int, total_pages: int, synthetic: bool, seed: int = 0,
                 scope: str | None = None) -> CompiledPage:
    scope = scope or f"p-{node.node_id}"
    tone = genes.tone
    min_m = float(genome.invariants["page"]["min_margin_mm"])
    css = page_css(genes, scope, min_m)
    for blk in node.content:
        if blk.block_id == node.first_fixation:
            blk.data["first_fixation"] = True
    zone_html = []
    numeral_used = False
    for z in zones_for(node, genes):
        if not z.blocks:
            continue
        rendered, n = [], 0
        if genes.section_division == "numeral" and not numeral_used and z.name in ("header", "side", "statement"):
            rendered.append(f'<div class="numeral" data-decor="1" aria-hidden="true">{page_no:02d}</div>')
            numeral_used = True
        for b in z.blocks:
            if b.role == "list_item":
                n += 1
            rendered.append(render_block(b, locks, genes, step_no=n if b.role == "list_item" else None))
        if genes.archetype == "ledger" and z.name == "rows":
            rendered = [_ledgerize(r) for r in rendered]
        style = (f"grid-column:{z.col_start} / span {z.col_span};grid-row:{z.row};"
                 f"justify-content:{z.justify};")
        zone_html.append(f'<div class="zone zone-{z.name}{z.cls}" style="{style}">{"".join(rendered)}</div>')
    decor = ""
    if genes.visual_metaphor != "none" and genes.archetype in ("cover-monument", "hero-number", "quiet-breath",
                                                               "manifesto", "timeline-rail"):
        decor = metaphor_svg(genes.visual_metaphor, PAGE_W, PAGE_H, "#A9B3C1", seed=seed,
                             opacity=0.16 if tone == "dark" else 0.2)
    logo = ""
    if node.semantic_type.value in ("Cover", "Closing"):
        logo_svg, logo_sha = brand_svg("logo_on_dark" if tone == "dark" else "logo")
        logo = (f'<div class="logo" data-brand="logo" data-decor="1" data-asset-sha="{logo_sha}" '
                f'style="position:absolute;inset-inline-end:'
                f'{max(min_m, genes.margin_mm)}mm;top:{max(min_m, genes.margin_mm)}mm">{logo_svg}</div>')
    footer = ""
    if node.semantic_type.value != "Cover":
        syn = '<bdi class="syn" dir="ltr">SYNTHETIC — fictional data</bdi>' if synthetic else ""
        robot_svg, robot_sha = brand_svg("robot")
        footer = (f'<footer class="page-footer" data-decor="1" data-brand="footer" data-asset-sha="{robot_sha}">'
                  f'{robot_svg}<bdi dir="ltr">APEX</bdi>'
                  f'<bdi class="pno" dir="ltr">{page_no:02d} / {total_pages:02d}</bdi>{syn}</footer>')
    cls = f"page tone-{tone} arch-{genes.archetype} num-{genes.number_treatment} div-{genes.section_division}"
    rows = ROW_TEMPLATES.get(genes.archetype, "auto 1fr")
    page_html = (f'<section class="{cls}" id="{scope}" data-page-id="{node.node_id}" data-node-type="{node.semantic_type.value}" '
                 f'data-archetype="{genes.archetype}" data-first-fixation="{node.first_fixation}">'
                 f'<div class="decor" data-decor="1">{decor}</div>{logo}'
                 f'<div class="page-body" style="grid-template-rows:{rows}">{"".join(zone_html)}</div>{footer}</section>')
    b, r = genes.base_font_px, genes.type_scale_ratio
    css += (f"#{scope} .zone-cover-mid .blk-heading{{font-size:{min(84, max(56, b * r ** 5)):.1f}px;line-height:1.08}}"
            f"#{scope} .zone-statement .blk-heading{{font-size:{min(72, max(42, b * r ** 4.4)):.1f}px;line-height:1.22}}"
            f"#{scope} .zone-statement-body .blk{{font-size:{b * r ** 0.75:.1f}px}}"
            f"#{scope} .zone-hero-text .blk-paragraph{{font-size:{b * r:.1f}px;line-height:1.5}}"
            f"#{scope} .zone-breath .blk-pullquote{{font-size:{min(46, max(32, b * r ** 3)):.1f}px}}")
    # intentional hierarchy: when the eye must land on a number first, the heading yields
    ff_block = next((x for x in node.content if x.block_id == node.first_fixation), None)
    if ff_block is not None and ff_block.role in ("stat", "step", "hero"):
        css += f"#{scope} .blk-heading{{font-size:{min(34.0, b * r ** 2):.1f}px}}"
    # the designated first-fixation stat out-ranks the page heading
    ff_size = min(104.0, max(46.0, b * r ** 3.4))
    css += (f"#{scope} .blk.ff .stat-value{{font-size:{ff_size:.1f}px;line-height:1.05}}"
            f"#{scope} .blk.ff .stat-label{{font-size:{max(13.0, b):.1f}px}}"
            f"#{scope} .blk-step.ff .step-date{{font-size:{min(72.0, max(46.0, b * r ** 3)):.1f}px}}")
    if genes.archetype == "timeline-rail":
        css += f"#{scope} .zone-rows{{border-inline-start:2px solid var(--accent);padding-inline-start:7mm}}"
        css += f"#{scope} .zone-rows .blk-step .step-date{{font-size:{b * r ** 1.6:.1f}px}}"
    if genes.archetype == "checklist-sheet":
        css += (f"#{scope} .zone-rows .blk-list_item{{border-top:1px solid var(--rule);padding-block:3.2mm;"
                f"padding-inline-start:14mm;font-size:{b * r ** 0.5:.1f}px}} #{scope} .zone-rows .blk-list_item::before{{display:none}}"
                f" #{scope} .item-no{{position:absolute;inset-inline-start:0;font-family:var(--f-fig);color:var(--accent);"
                f"font-size:{b * r:.1f}px}}")
    if genes.archetype == "ledger":
        css += f"#{scope} .zone-rows .blk-list_item{{padding-block:1.2mm;font-size:{b * r ** 0.4:.1f}px}}"
    if genes.section_division == "rule":
        css += f"#{scope} .zone-header,#{scope} .zone-side{{border-bottom:1px solid var(--rule);padding-bottom:5mm}}"
    if genes.section_division == "tone-shift":
        css += f"#{scope} .zone.band{{padding-top:7mm}}"
    return CompiledPage(page_id=node.node_id, node_type=node.semantic_type.value, archetype=genes.archetype,
                        html=page_html, css=css, signature=structural_signature(node, genes))


def _ledgerize(block_html: str) -> str:
    if 'data-role="stat"' in block_html:
        return block_html.replace('class="blk blk-stat', 'class="ledger-row blk blk-stat', 1)
    return block_html


def compile_document(pages: list[CompiledPage], genome: DesignGenome, *, title: str, font_mode: str = "relative",
                     synthetic: bool = False, extra_meta: dict[str, str] | None = None) -> str:
    meta = "".join(f'<meta name="{esc(k)}" content="{esc(v)}">' for k, v in (extra_meta or {}).items())
    syn = '<meta name="apex-synthetic" content="true">' if synthetic else ""
    css = font_css(font_mode) + base_css(genome) + "".join(p.css for p in pages)
    return (f'<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">{syn}{meta}'
            f'<title>{esc(title)}</title><style>{css}</style></head><body>'
            + "".join(p.html for p in pages) + "</body></html>")
