"""Template -> TextRun parsing. Facts are bound to locks; terms are bidi-isolated English."""

from __future__ import annotations

import re

from apex_one.core.schemas.document import TextRun
from apex_one.core.schemas.evidence import FactLock

TOKEN = re.compile(r"\{\{\s*(?P<slot>[\w.]+)(?:\|(?P<disp>en|ar))?\s*\}\}|\[\[(?P<term>[^\]]+)\]\]|(?P<url>https?://\S+)")


class MissingFact(KeyError):
    """A template referenced a slot that is not locked: the sentence must be dropped, never guessed."""


LATIN_SPAN = re.compile(r"[A-Za-z][A-Za-z0-9.'&/\-]*(?:\s+[A-Za-z0-9][A-Za-z0-9.'&/\-]*)*")


def _split_latin(text: str, base_lang: str) -> list[TextRun]:
    """Inside Arabic text, Latin spans become isolated English term runs (bidi safety)."""
    if base_lang != "ar":
        return [TextRun(kind="text", text=text, lang=base_lang)]
    runs, pos = [], 0
    for m in LATIN_SPAN.finditer(text):
        if m.start() > pos:
            runs.append(TextRun(kind="text", text=text[pos:m.start()], lang="ar"))
        runs.append(TextRun(kind="term", text=m.group(0), lang="en"))
        pos = m.end()
    if pos < len(text):
        runs.append(TextRun(kind="text", text=text[pos:], lang="ar"))
    return runs


def parse_runs(template: str, locks: dict[str, FactLock], variables: dict[str, str] | None = None,
               base_lang: str = "ar") -> list[TextRun]:
    if variables:
        for k, v in variables.items():
            template = template.replace("{" + k + "}", v)
    runs: list[TextRun] = []
    pos = 0
    for m in TOKEN.finditer(template):
        if m.start() > pos:
            runs += _split_latin(template[pos:m.start()], base_lang)
        if m.group("slot"):
            slot = m.group("slot")
            lk = locks.get(slot)
            if lk is None:
                raise MissingFact(slot)
            disp = m.group("disp") or ("ar" if base_lang == "ar" else "en")
            runs.append(TextRun(kind="fact", slot=slot, claim_id=lk.claim_id, display=disp,
                                text=lk.display_ar if disp == "ar" else lk.display_en,
                                lang="ar" if disp == "ar" and re.search(r"[؀-ۿ]", lk.display_ar) else "en"))
        elif m.group("term"):
            runs.append(TextRun(kind="term", text=m.group("term"), lang="en"))
        else:
            runs.append(TextRun(kind="url", text=m.group("url"), lang="en"))
        pos = m.end()
    if pos < len(template):
        runs += _split_latin(template[pos:], base_lang)
    return runs


def runs_text(runs: list[TextRun]) -> str:
    return "".join(r.text for r in runs)
