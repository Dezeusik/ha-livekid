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

    async def download(self, role_id: str, ref) -> bytes:
        """Pobiera załącznik (np. jadłospis .doc/.docx). ref: URL, ścieżka API albo obiekt z polem url/path."""
        if isinstance(ref, dict):
            ref = ref.get("url") or ref.get("path") or ref.get("link") or ref.get("file") or ref.get("name")
        if not ref:
            raise LiveKidError("brak pliku")
        url = ref if str(ref).startswith("http") else self._base + str(ref).lstrip("/")
        if not self._jwt:
            await self.login()
        hdr = {k: v for k, v in HEADERS.items() if k != "Content-Type"}
        hdr["Accept"] = "*/*"
        for headers in ({**hdr, "Authorization": f"Bearer {self._jwt[str(role_id)]}"}, hdr):
            async with self._s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as r:
                if r.status < 400:
                    data = await r.read()
                    if data[:2] == b"PK" or data[:4] == bytes.fromhex("D0CF11E0"):
                        return data
                    raise LiveKidError(f"plik nie jest dokumentem Worda ({r.content_type}, {len(data)} B)")
        raise LiveKidError(f"pobieranie pliku: HTTP {r.status}")
