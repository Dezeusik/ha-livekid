"""Przekształcenie odpowiedzi API LiveKid na proste słowniki (bez zależności od HA)."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

def hhmm(minutes: Any) -> str | None:
    """API podaje godziny jako minuty od północy (469 -> 07:49)."""
    if minutes is None or minutes == "":
        return None
    try:
        m = int(minutes)
    except (TypeError, ValueError):
        return str(minutes)
    return f"{m // 60:02d}:{m % 60:02d}"


def ms_to_iso(ms: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _txt(v: Any, n: int = 400) -> str:
    return " ".join(str(v or "").split())[:n]


def presence(day: dict | None) -> dict:
    d = day or {}
    t_in, t_out = d.get("in"), d.get("out")
    if d.get("planned_absence"):
        status = "nieobecność zgłoszona"
    elif d.get("absent"):
        status = "nieobecny"
    elif t_in is not None and t_out is None:
        status = "w przedszkolu"
    elif t_in is not None and t_out is not None:
        status = "odebrany"
    elif not d:
        status = "brak danych"
    else:
        status = "jeszcze nie ma"
    meals = []
    for m in d.get("meals") or []:
        item = {"nazwa": m.get("name"), "godzina": hhmm(m.get("serving_time"))}
        if m.get("eaten"):  # tylko gdy przedszkole zaznacza porcje (funkcja meals-eaten)
            item["zjedzone"] = m.get("eaten")
        if m.get("comment"):
            item["komentarz"] = _txt(m.get("comment"), 200)
        meals.append(item)
    sleeps = []
    for s_ in d.get("sleeps") or []:
        if isinstance(s_, dict):
            sleeps.append({"od": hhmm(s_.get("asleep")), "do": hhmm(s_.get("awoken"))})
    if not sleeps and d.get("asleep") is not None:
        sleeps.append({"od": hhmm(d.get("asleep")), "do": hhmm(d.get("awoken"))})
    report = d.get("daily_report_comment")
    if not report and isinstance(d.get("daily_report"), dict):
        report = d["daily_report"].get("comment") or d["daily_report"].get("text")
    return {
        "status": status,
        "przyszedl": hhmm(t_in), "odebrany": hhmm(t_out),
        "kto_odebral": _txt(d.get("pickuper") or d.get("pick_up"), 80) or None,
        "kto_przyprowadzil": _txt(d.get("drop_off"), 80) or None,
        "temperatura": d.get("in_temperature"),
        "posilki": meals, "drzemki": sleeps,
        "notatki": [_txt(n if not isinstance(n, dict) else (n.get("text") or n.get("note") or n), 300) for n in d.get("notes") or []],
        "raport": _txt(report, 600) or None,
        "toalety": len(d.get("toilets") or []),
        "rewizja": d.get("last_revision"),
    }


def month_stats(month: dict | None) -> dict:
    days = (month or {}).get("days") or {}
    present = sum(1 for v in days.values() if v.get("is_present"))
    absent = sum(1 for v in days.values() if v.get("is_absent") or v.get("has_planned_absence"))
    workdays = sum(1 for v in days.values() if not v.get("is_day_off"))
    return {"obecnosci": present, "nieobecnosci": absent, "dni_robocze": workdays}


def news(items: list | None) -> list[dict]:
    out = [{"id": str(n.get("id")), "tytul": _txt(n.get("title"), 120), "tresc": _txt(n.get("body"), 500),
            "data": ms_to_iso(n.get("created_at")), "autor": _txt((n.get("author") or {}).get("display"), 60),
            "zdjec": len(n.get("photos") or []), "przeczytane": bool(n.get("seen"))}
           for n in items or [] if not n.get("draft") and not n.get("trashed")]
    return sorted(out, key=lambda x: x["data"] or "", reverse=True)


def albums(items: list | None) -> list[dict]:
    out = [{"id": str(a.get("id")), "tytul": _txt(a.get("title"), 120), "opis": _txt(a.get("description"), 300),
            "data": ms_to_iso(a.get("created_at")), "zdjec": len(a.get("photos") or []), "obejrzane": bool(a.get("seen")),
            "okladka": a.get("cover")} for a in items or [] if not a.get("trashed")]
    return sorted(out, key=lambda x: x["data"] or "", reverse=True)


def chats(items: list | None, own_ids: set[str]) -> list[dict]:
    out = []
    for c in items or []:
        lm = c.get("last_message") or {}
        out.append({"id": str(c.get("id")), "nazwa": _txt(c.get("name") or c.get("kid_name"), 80),
                    "nieprzeczytany": c.get("seen") is False, "msg_id": str(lm.get("id") or ""),
                    "od": _txt(lm.get("author_name"), 60), "moja": str(lm.get("author")) in own_ids,
                    "tekst": _txt(lm.get("text"), 500), "zalacznikow": len(lm.get("attachments") or []),
                    "data": ms_to_iso(lm.get("date") or c.get("last_message_date"))})
    return sorted(out, key=lambda x: x["data"] or "", reverse=True)


def bills(items: list | None) -> list[dict]:
    out = []
    for b in items or []:
        cat = b.get("total_to_pay_by_category") or b.get("total_by_category") or {}
        total = sum(v for v in cat.values() if isinstance(v, (int, float))) / 100
        out.append({"id": str(b.get("id") or f"{b.get('date')}-{b.get('description')}"), "data": b.get("date"),
                    "opis": _txt(b.get("description"), 120), "kwota": round(total, 2),
                    "termin": b.get("payment_due_date"), "wplat": len(b.get("payments") or []),
                    "kategorie": {k: v / 100 for k, v in cat.items() if isinstance(v, (int, float)) and v}})
    return sorted(out, key=lambda x: x["data"] or "", reverse=True)


def balance(items: list | None, kid: str) -> dict:
    for b in items or []:
        if str(b.get("kid")) == str(kid):
            return {"saldo": b.get("balance"), "saldo_liczba": b.get("balance_numeric")}
    return {"saldo": None, "saldo_liczba": None}


def menu(items: list | None) -> dict | None:
    for m in items or []:
        return {"id": str(m.get("id")), "tytul": _txt(m.get("title"), 120), "plik": m.get("file"),
                "dni": m.get("dates") or []}
    return None
