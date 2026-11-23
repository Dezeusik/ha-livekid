"""Rozpoznawanie tygodniowego jadłospisu z tabeli Worda (dzień | śniadanie | obiad | podwieczorek | alergeny)."""
from __future__ import annotations

import datetime as dt
import re

from .docread import read_rows

DAYS = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")
COLS = {"śniad": "sniadanie", "ii śniad": "drugie_sniadanie", "drugie": "drugie_sniadanie", "obiad": "obiad",
        "podwiecz": "podwieczorek", "kolac": "kolacja", "alerg": "alergeny"}
DEFAULT = ["sniadanie", "obiad", "podwieczorek", "alergeny"]
DATE = re.compile(r"(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?")


def _col(name: str) -> str | None:
    n = name.lower().strip()
    for k in sorted(COLS, key=len, reverse=True):
        if n.startswith(k):
            return COLS[k]
    return None


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\n", " ")).strip(" ,;")


def parse(data: bytes, today: dt.date | None = None) -> dict[str, dict]:
    """Zwraca {"2026-11-23": {"dzien": "Poniedziałek", "sniadanie": ..., "obiad": ..., ...}}."""
    today = today or dt.date.today()
    rows, _ = read_rows(data)
    cols = DEFAULT
    for r in rows:
        mapped = [_col(c) for c in r[1:]]
        if sum(1 for m in mapped if m) >= 2 and not DATE.search(r[0] if r else ""):
            cols = [m or f"kol{i}" for i, m in enumerate(mapped)]
    out: dict[str, dict] = {}
    for r in rows:
        if len(r) < 2 or sum(1 for c in r[1:] if _col(c)) >= 2:   # nagłówek tabeli
            continue
        first = "\n".join(r[0].split("\n")[-3:])   # akapity sprzed tabeli mogą wpaść do 1. komórki
        low = first.lower()
        day = next((d for d in DAYS if d in low), None)
        m = DATE.search(first)
        if not day and not m:
            continue
        date = None
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
            year = (2000 + int(y)) if y and len(y) == 2 else int(y) if y else today.year
            try:
                date = dt.date(year, mo, d)
            except ValueError:
                date = None
        if date is None and day:
            monday = today - dt.timedelta(days=today.weekday())
            date = monday + dt.timedelta(days=DAYS.index(day))
        entry = {"dzien": (day or DAYS[date.weekday()]).capitalize()}
        for name, val in zip(cols, r[1:]):
            if val.strip():
                entry[name] = _clean(val)
        out[date.isoformat()] = entry
    return out
