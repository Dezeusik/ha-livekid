from __future__ import annotations
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN


class KidEntity(CoordinatorEntity):
    _attr_has_entity_name = True
    key = ""

    def __init__(self, coordinator, entry, role_id: str) -> None:
        super().__init__(coordinator)
        self.role_id = role_id
        d = coordinator.data[role_id]
        self._attr_unique_id = f"{entry.entry_id}_{role_id}_{self.key}"
        self._attr_device_info = {"identifiers": {(DOMAIN, f"{entry.entry_id}_{role_id}")},
                                  "name": f"LiveKid – {d['dziecko']}", "manufacturer": "LiveKid",
                                  "model": d.get("przedszkole") or "Przedszkole"}

    @property
    def k(self) -> dict:
        return (self.coordinator.data or {}).get(self.role_id, {})

    @property
    def available(self) -> bool:
        return super().available and bool(self.k)
