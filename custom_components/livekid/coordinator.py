from __future__ import annotations
from datetime import timedelta
import logging
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from . import menu_doc
from . import parser as P
from .api import LiveKidAuthError, LiveKidClient
from .const import (DOMAIN, EVENT_ALBUM, EVENT_ARRIVED, EVENT_BILL, EVENT_MENU, EVENT_MESSAGE, EVENT_NEWS,
                    EVENT_PICKED_UP, EVENT_REPORT)

_LOGGER = logging.getLogger(__name__)


class LiveKidCoordinator(DataUpdateCoordinator):
    """Dane wszystkich dzieci z konta. data = {role_id: {...}}"""

    def __init__(self, hass: HomeAssistant, client: LiveKidClient, entry_id: str, minutes: int) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(minutes=minutes))
        self.client = client
        self._store = Store(hass, 1, f"{DOMAIN}_{entry_id}")
        self._seen: dict | None = None

    async def _fetch_kid(self, role: dict) -> dict:
        rid, kid = str(role["id"]), str(role["kid"])
        today = dt_util.now().date()
        g = self.client.get
        day = await g(rid, f"v1/presence/{today.isoformat()}/{kid}")
        month = await g(rid, f"v1/presence/{today:%Y-%m}/{kid}", {"view": "true"})
        news = await g(rid, "v1/news", {"drafts": "false", "offset": 0, "limit": 10})
        albums = await g(rid, "v1/albums", {"offset": 0, "limit": 10})
        chats = await g(rid, "v1/chats", {"view": "true", "offset": 0, "limit": 20})
        bills = await g(rid, "v1/bills", {"kid": kid, "sort": "date", "reverse": "true", "limit": 5, "offset": 0})
        bal = await g(rid, "v1/report/balance", {"view": "true"})
        menus = await g(rid, "v1/menus", {"day": today.isoformat()})
        own = {rid, str(role.get("pid", "")), str(role.get("account_id", "")).lstrip("-")}
        return {
            "dziecko": role.get("kid_name") or role.get("display"), "nazwisko": role.get("kid_surname"),
            "przedszkole": role.get("school_name"), "kid": kid, "role": rid,
            "dzis": P.presence(day if isinstance(day, dict) else {}),
            "miesiac": P.month_stats(month if isinstance(month, dict) else {}),
            "aktualnosci": P.news(news if isinstance(news, list) else []),
            "galeria": P.albums(albums if isinstance(albums, list) else []),
            "czaty": P.chats(chats if isinstance(chats, list) else [], own),
            "rachunki": P.bills(bills if isinstance(bills, list) else []),
            **P.balance(bal if isinstance(bal, list) else [], kid),
            "jadlospis": P.menu(menus if isinstance(menus, list) else []),
        }

    async def _menu_days(self, rid: str, menu: dict | None) -> dict:
        """Treść jadłospisu z pliku Worda; pobierana raz na nowy jadłospis i zapamiętywana."""
        cache = self._seen.setdefault("_menu_cache", {})
        if not menu or not menu.get("plik"):
            return {}
        mid = menu["id"]
        if mid in cache:
            return cache[mid]
        try:
            raw = await self.client.download(rid, menu["plik"])
            days = await self.hass.async_add_executor_job(menu_doc.parse, raw, dt_util.now().date())
        except Exception as e:  # noqa: BLE001
            _LOGGER.warning("LiveKid: nie udało się odczytać jadłospisu %s: %s", mid, e)
            return {}
        cache.clear()
        cache[mid] = days
        return days

    async def _async_update_data(self):
        if self._seen is None:
            self._seen = await self._store.async_load() or {}
        try:
            roles = self.client.roles or await self.client.login()
            data = {str(r["id"]): await self._fetch_kid(r) for r in roles}
            for rid, d in data.items():
                d["jadlospis_dni"] = await self._menu_days(rid, d["jadlospis"])
                if d["jadlospis"]:
                    d["jadlospis"]["dni_menu"] = d["jadlospis_dni"]
        except LiveKidAuthError as e:
            raise ConfigEntryAuthFailed(str(e)) from e
        except Exception as e:  # noqa: BLE001
            raise UpdateFailed(str(e)) from e
        self._fire_events(data)
        await self._store.async_save(self._seen)
        return data

    def _fire_events(self, data: dict) -> None:
        today = dt_util.now().date().isoformat()
        for rid, d in data.items():
            seen = self._seen.setdefault(rid, {})
            first = not seen
            base = {"dziecko": d["dziecko"], "przedszkole": d["przedszkole"]}
            fire = (lambda ev, payload: None) if first else (lambda ev, payload: self.hass.bus.async_fire(ev, {**base, **payload}))
            dz = d["dzis"]
            # przyjście / odbiór – raz dziennie
            if dz["przyszedl"] and seen.get("in") != f"{today} {dz['przyszedl']}":
                fire(EVENT_ARRIVED, {"godzina": dz["przyszedl"], "kto": dz["kto_przyprowadzil"], "temperatura": dz["temperatura"]})
                seen["in"] = f"{today} {dz['przyszedl']}"
            if dz["odebrany"] and seen.get("out") != f"{today} {dz['odebrany']}":
                fire(EVENT_PICKED_UP, {"godzina": dz["odebrany"], "kto": dz["kto_odebral"], "posilki": dz["posilki"],
                                       "drzemki": dz["drzemki"], "raport": dz["raport"], "notatki": dz["notatki"]})
                seen["out"] = f"{today} {dz['odebrany']}"
            if dz["raport"] and seen.get("raport") != f"{today} {dz['raport'][:80]}":
                fire(EVENT_REPORT, {"raport": dz["raport"]})
                seen["raport"] = f"{today} {dz['raport'][:80]}"
            for key, items, ev in (("news", d["aktualnosci"], EVENT_NEWS), ("albums", d["galeria"], EVENT_ALBUM),
                                   ("bills", d["rachunki"], EVENT_BILL)):
                known = set(seen.get(key, []))
                for it in items:
                    if it["id"] not in known:
                        fire(ev, it)
                seen[key] = sorted(known | {it["id"] for it in items})[-200:]
            msgs = set(seen.get("msgs", []))
            for c in d["czaty"]:
                if c["msg_id"] and c["msg_id"] not in msgs and not c["moja"]:
                    fire(EVENT_MESSAGE, c)
            seen["msgs"] = sorted(msgs | {c["msg_id"] for c in d["czaty"] if c["msg_id"]})[-300:]
            if d["jadlospis"] and seen.get("menu") != d["jadlospis"]["id"]:
                fire(EVENT_MENU, d["jadlospis"])
                seen["menu"] = d["jadlospis"]["id"]
            seen["init"] = True
