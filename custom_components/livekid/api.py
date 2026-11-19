"""Klient REST API LiveKid (to samo API, z którego korzysta app.livekid.com)."""
from __future__ import annotations
import logging
from typing import Any
import aiohttp
from .const import API_URL

_LOGGER = logging.getLogger(__name__)
HEADERS = {"Accept": "application/json, text/plain, */*", "Content-Type": "application/json",
           "Origin": "https://app.livekid.com", "Referer": "https://app.livekid.com/",
           "User-Agent": "Mozilla/5.0 (compatible; ha-livekid/0.1; +https://github.com/Dezeusik/ha-livekid)"}


class LiveKidAuthError(Exception):
    pass


class LiveKidError(Exception):
    pass


class LiveKidClient:
    def __init__(self, session: aiohttp.ClientSession, email: str, password: str, region: str = "pl") -> None:
        self._s, self._email, self._password = session, email.strip(), password
        self._base = API_URL.format(region=region)
        self.roles: list[dict] = []           # role rodzica – po jednej na dziecko
        self._jwt: dict[str, str] = {}        # role id -> JWT

    async def login(self) -> list[dict]:
        body = {"mail": self._email.lower(), "password": self._password}
        async with self._s.post(self._base + "v1/accounts/login", json=body, headers=HEADERS,
                                timeout=aiohttp.ClientTimeout(total=30)) as r:
            data = await r.json(content_type=None) if r.content_type.endswith("json") else {"error": await r.text()}
            if r.status in (400, 401, 403, 404):
                raise LiveKidAuthError(f"HTTP {r.status}: {str(data.get('error', data))[:200]}")
            if r.status >= 400:
                raise LiveKidError(f"HTTP {r.status}")
        roles = [x for x in (data.get("roles") or []) if x.get("type") == "parent" and x.get("is_active", True)]
        if not roles:
            raise LiveKidAuthError("Konto nie ma aktywnej roli rodzica")
        self.roles = roles
        self._jwt = {str(x["id"]): x["jwt"] for x in roles}
        return roles

    async def get(self, role_id: str, path: str, params: dict | None = None) -> Any:
        for attempt in (0, 1):
            if not self._jwt:
                await self.login()
            hdr = {**HEADERS, "Authorization": f"Bearer {self._jwt[str(role_id)]}"}
            async with self._s.get(self._base + path, params=params, headers=hdr,
                                   timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status == 401 and attempt == 0:
                    self._jwt = {}
                    continue
                if r.status == 401:
                    raise LiveKidAuthError("Sesja odrzucona po ponownym logowaniu")
                if r.status >= 400:
                    raise LiveKidError(f"{path}: HTTP {r.status}")
                return await r.json(content_type=None)
        raise LiveKidError(path)
