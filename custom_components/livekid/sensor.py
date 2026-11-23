from __future__ import annotations
from datetime import timedelta
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.util import dt as dt_util
from .const import DOMAIN
from .entity import KidEntity


async def async_setup_entry(hass, entry, async_add):
    c = hass.data[DOMAIN][entry.entry_id]
    async_add([cls(c, entry, rid) for rid in c.data for cls in
               (Status, Arrived, PickedUp, Meals, Nap, Report, News, Gallery, Unread, LastBill, Balance, Menu, MenuToday, MenuTomorrow, MonthPresence)])


class _S(KidEntity, SensorEntity):
    pass


class Status(_S):
    key, _attr_name, _attr_icon = "status", "Status", "mdi:human-child"

    @property
    def native_value(self):
        return self.k["dzis"]["status"]

    @property
    def extra_state_attributes(self):
        d = self.k["dzis"]
        return {k: d[k] for k in ("przyszedl", "odebrany", "kto_przyprowadzil", "kto_odebral", "temperatura")}


class Arrived(_S):
    key, _attr_name, _attr_icon = "arrived", "Przyjście", "mdi:login"

    @property
    def native_value(self):
        return self.k["dzis"]["przyszedl"]

    @property
    def extra_state_attributes(self):
        return {"kto": self.k["dzis"]["kto_przyprowadzil"], "temperatura": self.k["dzis"]["temperatura"]}


class PickedUp(_S):
    key, _attr_name, _attr_icon = "picked_up", "Odbiór", "mdi:logout"

    @property
    def native_value(self):
        return self.k["dzis"]["odebrany"]

    @property
    def extra_state_attributes(self):
        return {"kto": self.k["dzis"]["kto_odebral"]}


class Meals(_S):
    key, _attr_name, _attr_icon = "meals", "Posiłki dziś", "mdi:silverware-fork-knife"

    @property
    def native_value(self):
        return len(self.k["dzis"]["posilki"])

    @property
    def extra_state_attributes(self):
        return {"posilki": self.k["dzis"]["posilki"]}


class Nap(_S):
    key, _attr_name, _attr_icon = "nap", "Drzemka", "mdi:sleep"

    @property
    def native_value(self):
        s = self.k["dzis"]["drzemki"]
        return f"{s[-1]['od'] or '?'}–{s[-1]['do'] or '…'}" if s else None

    @property
    def extra_state_attributes(self):
        return {"drzemki": self.k["dzis"]["drzemki"]}


class Report(_S):
    key, _attr_name, _attr_icon = "report", "Raport dnia", "mdi:text-box-outline"

    @property
    def native_value(self):
        r = self.k["dzis"]["raport"]
        return r[:255] if r else None

    @property
    def extra_state_attributes(self):
        return {"raport": self.k["dzis"]["raport"], "notatki": self.k["dzis"]["notatki"], "toalety": self.k["dzis"]["toalety"]}


class News(_S):
    key, _attr_name, _attr_icon = "news", "Aktualności", "mdi:newspaper-variant-outline"

    @property
    def native_value(self):
        n = self.k["aktualnosci"]
        return n[0]["tytul"][:255] if n else None

    @property
    def extra_state_attributes(self):
        n = self.k["aktualnosci"]
        return {"nieprzeczytane": sum(not x["przeczytane"] for x in n), "najnowsza": n[0] if n else None,
                "lista": [{**x, "tresc": (x.get("tresc") or "")[:500]} for x in n[:5]]}


class Gallery(_S):
    key, _attr_name, _attr_icon = "gallery", "Galeria", "mdi:image-multiple"

    @property
    def native_value(self):
        a = self.k["galeria"]
        return a[0]["tytul"][:255] if a else None

    @property
    def extra_state_attributes(self):
        a = self.k["galeria"]
        return {"nieobejrzane": sum(not x["obejrzane"] for x in a), "najnowszy": a[0] if a else None,
                "lista": [{k: v for k, v in x.items() if k != "okladka"} for x in a[:5]]}


class Unread(_S):
    key, _attr_name, _attr_icon = "unread", "Wiadomości nieprzeczytane", "mdi:message-badge-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        return sum(c["nieprzeczytany"] for c in self.k["czaty"])

    @property
    def extra_state_attributes(self):
        c = [x for x in self.k["czaty"] if not x["moja"]]
        return {"ostatnia": c[0] if c else None}


class LastBill(_S):
    key, _attr_name, _attr_icon = "last_bill", "Ostatni rachunek", "mdi:receipt-text-outline"
    _attr_native_unit_of_measurement = "zł"

    @property
    def native_value(self):
        b = self.k["rachunki"]
        return b[0]["kwota"] if b else None

    @property
    def extra_state_attributes(self):
        b = self.k["rachunki"]
        return {**(b[0] if b else {}), "poprzednie": b[1:4]}


class Balance(_S):
    key, _attr_name, _attr_icon = "balance", "Saldo", "mdi:wallet-outline"

    @property
    def native_value(self):
        return self.k.get("saldo")

    @property
    def extra_state_attributes(self):
        return {"wartosc": self.k.get("saldo_liczba")}


class Menu(_S):
    key, _attr_name, _attr_icon = "menu", "Jadłospis", "mdi:food-variant"

    @property
    def native_value(self):
        m = self.k.get("jadlospis")
        return m["tytul"][:255] if m else None

    @property
    def extra_state_attributes(self):
        return self.k.get("jadlospis") or {}


class MonthPresence(_S):
    key, _attr_name, _attr_icon = "month_presence", "Obecności w miesiącu", "mdi:calendar-check"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        return self.k["miesiac"]["obecnosci"]

    @property
    def extra_state_attributes(self):
        return self.k["miesiac"]


class _MenuDay(_S):
    """Stan = obiad; atrybuty = wszystkie posiłki danego dnia (z pliku jadłospisu)."""
    offset = 0
    _attr_icon = "mdi:silverware-fork-knife"

    def _day(self) -> dict:
        d = dt_util.now().date() + timedelta(days=self.offset)
        return (self.k.get("jadlospis_dni") or {}).get(d.isoformat()) or {}

    @property
    def native_value(self):
        day = self._day()
        v = day.get("obiad") or day.get("sniadanie")
        return v[:255] if v else None

    @property
    def extra_state_attributes(self):
        return self._day()


class MenuToday(_MenuDay):
    key, _attr_name, offset = "menu_today", "Jadłospis dziś", 0


class MenuTomorrow(_MenuDay):
    key, _attr_name, offset = "menu_tomorrow", "Jadłospis jutro", 1
