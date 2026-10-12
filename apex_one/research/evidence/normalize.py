"""Value normalization for dates, money, percentages and numbers (English + Arabic)."""

from __future__ import annotations

import re
from datetime import date

from apex_one.core.schemas.evidence import NormalizedValue, ValueType

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

MONTHS_EN = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], start=1)}
MONTHS_EN.update({k[:3]: v for k, v in list(MONTHS_EN.items())})
MONTHS_EN["sept"] = 9
MONTHS_AR = {"يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "ابريل": 4, "مايو": 5, "يونيو": 6, "يوليو": 7,
             "أغسطس": 8, "اغسطس": 8, "سبتمبر": 9, "أكتوبر": 10, "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12}
MONTH_NAMES_AR = {v: k for k, v in MONTHS_AR.items() if k not in ("ابريل", "اغسطس", "اكتوبر")}
MONTH_NAMES_EN = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September",
                  "October", "November", "December"]

_MON = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_MON_AR = "|".join(sorted(MONTHS_AR, key=len, reverse=True))
DATE_PATTERNS = [
    re.compile(rf"\b(?P<mon>{_MON})\.?\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<year>20\d\d)\b", re.I),
    re.compile(rf"\b(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<mon>{_MON})\.?,?\s+(?P<year>20\d\d)\b", re.I),
    re.compile(r"\b(?P<year>20\d\d)-(?P<mnum>\d{2})-(?P<day>\d{2})\b"),
    re.compile(rf"(?P<day>\d{{1,2}})\s+(?P<mon_ar>{_MON_AR})\s+(?P<year>20\d\d)"),
]
MONEY_PATTERNS = [
    re.compile(r"(?P<cur>US\$|USD\s?|\$|EGP\s?|E£|£|€)\s?(?P<amt>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<dec>\d{1,2}))?", re.I),
    re.compile(r"(?P<amt>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<dec>\d{1,2}))?\s?(?P<cur>USD|US dollars|dollars|EGP|جنيه|دولار)", re.I),
]
PERCENT_PATTERN = re.compile(r"(?P<num>\d{1,3}(?:\.\d+)?)\s?(?:%|٪|percent)", re.I)
CURRENCY_MAP = {"us$": "USD", "usd": "USD", "$": "USD", "us dollars": "USD", "dollars": "USD", "دولار": "USD",
                "egp": "EGP", "e£": "EGP", "جنيه": "EGP", "£": "GBP", "€": "EUR"}


def to_ascii_digits(s: str) -> str:
    return s.translate(ARABIC_DIGITS)


YEARLESS_PATTERNS = [
    re.compile(rf"\b(?P<mon>{_MON})\.?\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\b(?!,?\s+20\d\d)", re.I),
]


def find_dates(text: str, context_year: int | None = None) -> list[tuple[date, str, int]]:
    """Return (date, raw, position) for each full date (day+month+year) found. Dates WITHOUT a year are returned
    only when the caller supplies an explicit `context_year` (e.g. a table header "Dates (2027)"); the raw text
    is kept verbatim so the inference stays visible."""
    t = to_ascii_digits(text)
    out: list[tuple[date, str, int]] = []
    seen: set[int] = set()
    patterns = DATE_PATTERNS + ([(p, context_year) for p in YEARLESS_PATTERNS] if context_year else [])
    for p in patterns:
        if isinstance(p, tuple):
            p, year = p
            for m in p.finditer(t):
                if any(abs(m.start() - s0) < 3 for s0 in seen):
                    continue
                key = m.group("mon").lower().rstrip(".")
                try:
                    month = MONTHS_EN[key] if key in MONTHS_EN else MONTHS_EN[key[:3]]
                    out.append((date(year, month, int(m.group("day"))), m.group(0), m.start()))
                    seen.add(m.start())
                except (KeyError, ValueError):
                    continue
            continue
        for m in p.finditer(t):
            if m.start() in seen:
                continue
            gd = m.groupdict()
            try:
                if gd.get("mnum"):
                    month = int(gd["mnum"])
                elif gd.get("mon_ar"):
                    month = MONTHS_AR[gd["mon_ar"]]
                else:
                    key = gd["mon"].lower().rstrip(".")
                    month = MONTHS_EN[key] if key in MONTHS_EN else MONTHS_EN[key[:3]]
                out.append((date(int(gd["year"]), month, int(gd["day"])), m.group(0), m.start()))
                seen.add(m.start())
            except (KeyError, ValueError):
                continue
    return sorted(out, key=lambda x: x[2])


def find_money(text: str) -> list[tuple[float, str, str, int]]:
    t = to_ascii_digits(text)
    out: list[tuple[float, str, str, int]] = []
    taken: list[tuple[int, int]] = []
    for p in MONEY_PATTERNS:
        for m in p.finditer(t):
            if any(a <= m.start() < b for a, b in taken):
                continue
            amt = float(m.group("amt").replace(",", "") + ("." + m.group("dec") if m.group("dec") else ""))
            cur = CURRENCY_MAP.get(m.group("cur").strip().lower(), m.group("cur").strip().upper())
            out.append((amt, cur, m.group(0), m.start()))
            taken.append((m.start(), m.end()))
    return sorted(out, key=lambda x: x[3])


def find_percents(text: str) -> list[tuple[float, str, int]]:
    t = to_ascii_digits(text)
    return [(float(m.group("num")), m.group(0), m.start()) for m in PERCENT_PATTERN.finditer(t)]


def date_value(d: date, raw: str, qualifier: str | None = None) -> NormalizedValue:
    return NormalizedValue(type=ValueType.DATE, raw=raw, canonical=d.isoformat(), qualifier=qualifier)


def money_value(amount: float, currency: str, raw: str, qualifier: str | None = None) -> NormalizedValue:
    amt = int(amount) if amount == int(amount) else amount
    return NormalizedValue(type=ValueType.MONEY, raw=raw, canonical=f"{currency} {amt}", currency=currency,
                           amount=float(amount), qualifier=qualifier)


def percent_value(p: float, raw: str, qualifier: str | None = None) -> NormalizedValue:
    v = int(p) if p == int(p) else p
    return NormalizedValue(type=ValueType.PERCENT, raw=raw, canonical=f"{v}%", amount=float(p), qualifier=qualifier)


def number_value(n: float, raw: str, qualifier: str | None = None) -> NormalizedValue:
    v = int(n) if n == int(n) else n
    return NormalizedValue(type=ValueType.NUMBER, raw=raw, canonical=str(v), amount=float(n), qualifier=qualifier)


def text_value(s: str, qualifier: str | None = None) -> NormalizedValue:
    canon = re.sub(r"\s+", " ", s.strip().lower())
    return NormalizedValue(type=ValueType.TEXT, raw=s, canonical=canon[:300], qualifier=qualifier)


def bool_value(b: bool, raw: str, qualifier: str | None = None) -> NormalizedValue:
    return NormalizedValue(type=ValueType.BOOLEAN, raw=raw, canonical="true" if b else "false", qualifier=qualifier)


def display(value: NormalizedValue) -> tuple[str, str]:
    """(English display, Egyptian-Arabic display) for a locked value. Digits stay Latin for clarity."""
    if value.type == ValueType.DATE:
        d = date.fromisoformat(value.canonical)
        return f"{d.day} {MONTH_NAMES_EN[d.month]} {d.year}", f"{d.day} {MONTH_NAMES_AR[d.month]} {d.year}"
    if value.type == ValueType.MONEY:
        amt = value.amount or 0.0
        num = f"{int(amt):,}" if amt == int(amt) else f"{amt:,.2f}"
        if value.currency == "USD":
            return (f"${num}", f"{num} دولار") if amt else ("$0", "0 دولار")
        if value.currency == "EGP":
            return f"EGP {num}", f"{num} جنيه"
        return f"{value.currency} {num}", f"{num} {value.currency}"
    if value.type == ValueType.PERCENT:
        return value.canonical, value.canonical
    if value.type == ValueType.BOOLEAN:
        return ("Yes", "أيوه") if value.canonical == "true" else ("No", "لأ")
    if value.type == ValueType.NUMBER:
        return value.canonical, value.canonical
    if value.type == ValueType.TEXT and value.canonical in TEXT_AR:
        return value.raw, TEXT_AR[value.canonical]
    return value.raw, value.raw


# Controlled Arabic renderings for normalized text values (anything else is quoted in English).
TEXT_AR = {
    "open to all countries": "مفتوح للطلاب من كل الدول",
    "need-based": "على حسب الاحتياج المادي",
    "must demonstrate financial need": "لازم تثبت إنك محتاج دعم مادي",
    "f-1 student visa": "فيزا طالب F-1",
}
