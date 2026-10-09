"""CSS generation from Design Genome invariants + page genes."""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

from apex_one.core.schemas.design import DesignGenome, Genes

FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
FONT_FACES = [("IBM Plex Sans Arabic", w, f"IBMPlexSansArabic-{w}.ttf") for w in (300, 400, 600, 700)] + \
             [("Readex Pro", w, f"ReadexPro-{w}.ttf") for w in (300, 500, 700)] + \
             [("IBM Plex Mono", 500, "IBMPlexMono-500.ttf")]


@lru_cache(maxsize=2)
def font_css(mode: str = "relative") -> str:
    rules = []
    for fam, w, fn in FONT_FACES:
        if mode == "embedded":
            data = base64.b64encode((FONT_DIR / fn).read_bytes()).decode()
            src = f"url(data:font/ttf;base64,{data}) format('truetype')"
        else:
            src = f"url('fonts/{fn}') format('truetype')"
        rules.append(f"@font-face{{font-family:'{fam}';font-weight:{w};font-style:normal;font-display:block;src:{src};}}")
    return "\n".join(rules)


def base_css(genome: DesignGenome) -> str:
    p = genome.invariants["palette"]
    f = genome.invariants["fonts"]
    return f"""
:root{{--navy-900:{p['navy_900']};--navy-700:{p['navy_700']};--navy-500:{p['navy_500']};--silver-400:{p['silver_400']};
--silver-200:{p['silver_200']};--silver-100:{p['silver_100']};--white:{p['white']};--ink:{p['ink']};--signal:{p['signal']};
--warning:{p['warning']};--f-text:'{f['arabic_text']}','DejaVu Sans',sans-serif;--f-display:'{f['display']}','{f['arabic_text']}',sans-serif;
--f-fig:'{f['figures']}','{f['arabic_text']}',monospace;}}
@page{{size:A4;margin:0}}
*{{box-sizing:border-box;margin:0;padding:0}}
html{{background:var(--silver-200)}}
body{{font-family:var(--f-text);color:var(--ink);-webkit-print-color-adjust:exact;print-color-adjust:exact}}
.page{{position:relative;width:210mm;height:297mm;overflow:hidden;page-break-after:always;break-after:page;margin:0 auto 8mm}}
@media print{{html{{background:none}}.page{{margin:0}}}}
.page.tone-light{{background:var(--white);color:var(--ink);--accent:var(--navy-700);--rule:var(--silver-400);--muted:var(--navy-500);--fig:var(--navy-900)}}
.page.tone-dark{{background:var(--navy-900);color:var(--white);--accent:var(--silver-200);--rule:var(--navy-500);--muted:var(--silver-200);--fig:var(--white)}}
.page.tone-silver{{background:var(--silver-100);color:var(--ink);--accent:var(--navy-700);--rule:var(--silver-400);--muted:var(--navy-500);--fig:var(--navy-900)}}
.decor{{position:absolute;inset:0;pointer-events:none}}
.decor svg{{width:100%;height:100%;display:block}}
.page-body{{position:absolute;display:grid;grid-template-columns:repeat(12,1fr);align-content:start}}
.zone{{display:flex;flex-direction:column;min-width:0}}
.blk{{min-width:0;overflow-wrap:break-word}}
bdi.term,bdi.url{{unicode-bidi:isolate}}
.url{{overflow-wrap:anywhere;word-break:break-all;font-family:var(--f-fig);font-size:.85em}}
.fact{{font-feature-settings:"tnum" 1}}
.blk-kicker{{font-family:var(--f-display);font-weight:500;letter-spacing:0;color:var(--muted);text-transform:none}}
.blk-heading{{font-family:var(--f-display);color:var(--accent)}}
.tone-dark .blk-heading{{color:var(--white)}}
.blk-subheading{{font-family:var(--f-display);font-weight:500;color:var(--accent)}}
.blk-lead{{color:var(--muted)}}
.blk-label{{font-family:var(--f-display);font-weight:500;color:var(--accent)}}
.tone-dark .blk-label{{color:var(--signal)}}
.blk-quote{{font-family:var(--f-display);font-weight:300;border-inline-start:3px solid var(--rule);padding-inline-start:5mm}}
.blk-quote[dir=ltr]{{border-inline-start:none;border-left:3px solid var(--rule);padding-left:5mm;text-align:left}}
.blk-notice{{font-size:.8em;color:var(--muted);border-top:1px solid var(--rule);padding-top:2mm}}
.blk-aside{{color:var(--muted);font-style:normal}}
.blk-note{{color:var(--muted)}}
.blk-list_item{{position:relative;padding-inline-start:7mm}}
.blk-list_item::before{{content:"";position:absolute;inset-inline-start:0;top:.62em;width:3.2mm;height:1.4px;background:var(--accent)}}
.blk-list_item.check::before{{width:3mm;height:3mm;top:.45em;background:none;border:1.4px solid var(--accent);border-radius:1px}}
.blk-cta{{font-family:var(--f-display);font-weight:700;color:var(--accent)}}
.blk-cta::after{{content:" ←"}}
.stat-label{{display:block;color:var(--muted);font-family:var(--f-display);font-weight:500}}
.stat-value{{display:block;font-family:var(--f-fig);color:var(--fig);font-weight:500;line-height:1.1}}
.num-outlined .blk-hero .stat-value{{color:transparent;-webkit-text-stroke:2px var(--fig)}}
.num-underline-rule .stat-value{{text-decoration:underline;text-decoration-thickness:3px;text-underline-offset:6px;text-decoration-color:var(--signal)}}
.num-inline .stat-value{{font-family:var(--f-display)}}
.blk-hero .stat-value{{font-family:var(--f-fig)}}
.blk-step{{display:grid;grid-template-columns:minmax(52mm,auto) 1fr;align-items:baseline;gap:4mm;padding-block:3mm;border-top:1px solid var(--rule)}}
.blk-step .step-date{{font-family:var(--f-fig);color:var(--fig);font-weight:500;white-space:nowrap}}
.blk-step.critical .step-date{{color:var(--warning)}}
.tone-dark .blk-step.critical .step-date{{color:var(--signal)}}
.blk-warning{{border-inline-start:5px solid var(--warning);padding-inline-start:5mm}}
.blk-figure .viz-bar{{width:100%;height:5mm;display:block;margin-top:2mm}}
.blk-figure .stat-label{{margin-top:1.5mm}}
.blk-pullquote{{font-family:var(--f-display);font-weight:300;color:var(--accent)}}
.page-footer{{position:absolute;display:flex;align-items:center;gap:3mm;font-family:var(--f-fig);font-size:9px;color:var(--muted)}}
.page-footer svg{{width:5.2mm;height:5.2mm;color:var(--muted)}}
.page-footer .pno{{font-family:var(--f-fig)}}
.page-footer .syn{{color:var(--warning);font-family:var(--f-display)}}
.logo{{color:var(--accent)}} .logo svg{{height:7mm;width:auto;display:block}}
.tone-dark .logo{{color:var(--white)}}
.ledger-row{{display:flex;justify-content:space-between;align-items:baseline;gap:6mm;border-top:1px solid var(--rule)}}
.ledger-row .stat-label{{display:inline}}
.ledger-row .stat-value{{display:inline;text-align:end}}
.numeral{{font-family:var(--f-fig);color:var(--rule);line-height:.9}}
.band{{border-top:6px solid var(--accent)}}
@media screen and (max-width:640px){{
html{{background:var(--white)}}
.page{{width:auto;height:auto;overflow:visible;margin:0;border-bottom:10px solid var(--silver-200)}}
.page-body{{position:static !important;display:flex !important;flex-direction:column;gap:14px;padding:26px 20px 18px}}
.zone{{grid-column:auto !important;margin:0 !important;max-width:none !important}}
.decor,.numeral{{display:none}}
.logo{{position:static !important;padding:20px 20px 0}}
.page-footer{{position:static !important;padding:0 20px 18px}}
.page .blk{{font-size:16.5px !important;line-height:1.75 !important;max-width:none !important}}
.page .blk-heading{{font-size:28px !important;line-height:1.35 !important}}
.page .blk-hero .stat-value{{font-size:84px !important}}
.page .blk-stat .stat-value,.page .ledger-row .stat-value{{font-size:30px !important}}
.page .blk-pullquote{{font-size:24px !important}}
.page .blk-step{{grid-template-columns:1fr}}
}}
"""


def page_css(genes: Genes, scope: str, min_margin_mm: float) -> str:
    r = genes.type_scale_ratio
    b = genes.base_font_px
    lh = round(1.85 - 0.35 * genes.density, 3)
    gap_mm = round(2.0 + 7.0 * genes.whitespace, 2)
    m = max(min_margin_mm, genes.margin_mm)
    h1 = min(b * r ** 4, 64.0)
    h2 = min(max(b * r ** 3, 30.0), 52.0)
    wrap = {"balance": "balance", "pretty": "pretty", "normal": "wrap"}[genes.arabic_wrap]
    s = f"#{scope}"
    return f"""
{s} .page-body{{inset:{m}mm {m}mm {m + 9}mm {m}mm;column-gap:{round(3 + 4 * genes.whitespace, 2)}mm;row-gap:{gap_mm}mm}}
{s} .zone{{gap:{round(gap_mm * 0.6, 2)}mm}}
{s} .page-footer{{inset-inline:{m}mm;bottom:{max(6.0, m - 6)}mm}}
{s} .blk{{font-size:{b}px;line-height:{lh}}}
{s} .blk-paragraph{{font-size:{round(b * 1.06, 2)}px}}
{s} .blk-paragraph,{s} .blk-lead,{s} .blk-list_item,{s} .blk-warning,{s} .blk-note{{text-wrap:{wrap};max-width:{round(150 + 60 * (1 - genes.density))}mm}}
{s} .blk-lead{{font-size:{round(b * r ** 0.5, 2)}px}}
{s} .blk-kicker{{font-size:{round(max(11.0, b / r * 1.05), 2)}px}}
{s} .blk-heading{{font-size:{round(h2, 2)}px;line-height:1.28;font-weight:{genes.heading_weight};text-wrap:balance}}
{s} .blk-subheading{{font-size:{round(b * r, 2)}px;line-height:1.4}}
{s} .blk-subtitle{{font-size:{round(b * r, 2)}px;line-height:1.5}}
{s} .blk-stat .stat-value{{font-size:{round(b * r ** 2.2, 2)}px}}
{s} .blk-stat .stat-label{{font-size:{round(max(11.0, b * 0.88), 2)}px}}
{s} .blk-hero .stat-value{{font-size:{round(min(230.0, max(150.0, b * r ** 7)), 2)}px;line-height:.95}}
{s} .blk-pullquote{{font-size:{round(min(40.0, b * r ** 2.6), 2)}px;line-height:1.55;text-wrap:balance}}
{s} .blk-quote{{font-size:{round(b * r ** 0.8, 2)}px}}
{s} .blk-warning{{font-size:{round(b * r ** 0.6, 2)}px}}
{s} .blk-cta{{font-size:{round(b * r ** 1.2, 2)}px}}
{s} .blk-step .step-date{{font-size:{round(b * r ** 1.3, 2)}px}}
{s} .ledger-row{{padding-block:{round(2 + 3 * genes.whitespace, 2)}mm}}
{s} .ledger-row .stat-value{{font-size:{round(b * r ** 1.6, 2)}px}}
{s} .numeral{{font-size:{round(min(96.0, b * r ** 4.6), 2)}px}}
"""
