"""Geometry QA from real browser DOM measurements."""

from __future__ import annotations

from apex_one.core.schemas.common import Metric
from apex_one.core.schemas.quality import QAIssue

MM = 96 / 25.4
TEXT_ROLES = ("paragraph", "lead", "list_item", "warning", "note", "quote", "aside")


def _rect(i: dict) -> tuple[float, float, float, float]:
    return i["x"], i["y"], i["x"] + i["w"], i["y"] + i["h"]


def check_geometry(page: dict, min_margin_mm: float, limits: dict) -> tuple[list[QAIssue], dict[str, Metric]]:
    pid = page["pageId"]
    issues: list[QAIssue] = []
    items = [i for i in page["items"] if i["w"] > 0 and i["h"] > 0]
    W, H = page["w"], page["h"]
    body = page["body"]
    if body["overflowY"] > 1 or body["overflowX"] > 1:
        issues.append(QAIssue(check="qa.overflow", severity="critical", page=pid,
                              message=f"page body overflows by {body['overflowY']:.0f}px vertically / {body['overflowX']:.0f}px horizontally"))
    safe = min_margin_mm * MM
    footer_top = page["footerRect"]["y"] if page.get("footerRect") else H - safe
    for i in items:
        x0, y0, x1, y1 = _rect(i)
        hides = any(v in ("hidden", "clip", "scroll", "auto") for v in i.get("overflowStyle", "visible/visible").split("/"))
        if hides and (i["overflowX"] > 1 or i["overflowY"] > 2):
            issues.append(QAIssue(check="qa.clipping", severity="critical", page=pid, selector=i["id"],
                                  message=f"{i['role']} content clipped ({i['overflowX']:.0f}x/{i['overflowY']:.0f}y px)"))
        elif i["overflowX"] > 1:
            issues.append(QAIssue(check="qa.overflow", severity="critical", page=pid, selector=i["id"],
                                  message=f"{i['role']} content wider than its block by {i['overflowX']:.0f}px"))
        elif i["overflowY"] > 0.3 * i["fontPx"]:
            issues.append(QAIssue(check="qa.ink_overflow", severity="minor", page=pid, selector=i["id"],
                                  message=f"{i['role']} glyphs extend {i['overflowY']:.0f}px beyond the line box"))
        if x0 < safe - 1 or x1 > W - safe + 1 or y0 < safe - 1:
            issues.append(QAIssue(check="qa.margins", severity="critical", page=pid, selector=i["id"],
                                  message=f"{i['role']} enters the {min_margin_mm}mm safe margin"))
        if y1 > body["y"] + body["h"] + 1 or y1 > footer_top - 2:
            issues.append(QAIssue(check="qa.page_bounds", severity="critical", page=pid, selector=i["id"],
                                  message=f"{i['role']} runs past the content area into the footer/page edge"))
    # collisions between blocks
    for a_idx in range(len(items)):
        for b_idx in range(a_idx + 1, len(items)):
            a, b = _rect(items[a_idx]), _rect(items[b_idx])
            ix = min(a[2], b[2]) - max(a[0], b[0])
            iy = min(a[3], b[3]) - max(a[1], b[1])
            if ix > 2 and iy > 2:
                issues.append(QAIssue(check="qa.collision", severity="critical", page=pid,
                                      message=f"{items[a_idx]['role']} overlaps {items[b_idx]['role']} ({ix:.0f}x{iy:.0f}px)"))
    # alignment: start edge (right edge in RTL) shared with another block or the body edge
    edges = [round(i["x"] + i["w"]) if i["dir"] == "rtl" else round(i["x"]) for i in items]
    body_edge = round(body["x"] + body["w"])
    aligned = sum(1 for k, e in enumerate(edges)
                  if abs(e - body_edge) <= 2 or any(abs(e - f) <= 2 for j, f in enumerate(edges) if j != k))
    align_score = 100.0 * aligned / max(1, len(edges))
    # line length
    long_lines = 0
    for i in items:
        if i["role"] in TEXT_ROLES and i["lines"] >= 2:
            cpl = i["chars"] / i["lines"]
            lim = limits["max_line_chars_en"] if i["lang"] == "en" else limits["max_line_chars_ar"]
            if cpl > lim:
                long_lines += 1
                issues.append(QAIssue(check="qa.line_length", severity="major", page=pid, selector=i["id"],
                                      message=f"{cpl:.0f} chars/line > {lim}"))
    coverage = page["coverage"]
    chars = sum(i["chars"] for i in items)
    metrics = {
        "geometry.alignment": Metric.measured("geometry.alignment", align_score, "shared start-edge ratio (DOM)"),
        "geometry.whitespace_ratio": Metric.measured("geometry.whitespace_ratio", 100 * (1 - coverage),
                                                     "1 - sampled text-block coverage (DOM)", unit="percent"),
        "geometry.density": Metric.measured("geometry.density", chars / (W * H / 10000), "chars per 100x100px",
                                            unit="ratio"),
        "geometry.long_lines": Metric.measured("geometry.long_lines", long_lines, "count", unit="count"),
    }
    return issues, metrics
