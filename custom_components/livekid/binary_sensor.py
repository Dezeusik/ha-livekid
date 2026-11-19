from __future__ import annotations
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from .const import DOMAIN
from .entity import KidEntity


async def async_setup_entry(hass, entry, async_add):
    c = hass.data[DOMAIN][entry.entry_id]
    async_add([InKindergarten(c, entry, rid) for rid in c.data])


class InKindergarten(KidEntity, BinarySensorEntity):
    key, _attr_name, _attr_icon = "present", "W przedszkolu", "mdi:home-account"
    _attr_device_class = BinarySensorDeviceClass.PRESENCE

    @property
    def is_on(self):
        return self.k["dzis"]["status"] == "w przedszkolu"
