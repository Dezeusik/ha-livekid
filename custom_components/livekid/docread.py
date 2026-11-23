"""Minimalny odczyt tekstu z plików Word: .doc (Word 97–2003, OLE) i .docx – bez zewnętrznych bibliotek.

Dla .doc: czytnik kontenera OLE (Compound File) + tablica fragmentów (piece table) z FIB.
Komórki tabel kończą się znakiem 0x07, akapity 0x0D.
"""
from __future__ import annotations

import io
import re
import struct
import zipfile
import xml.etree.ElementTree as ET

ENDOFCHAIN = 0xFFFFFFFE
FREESECT = 0xFFFFFFFF


class _Ole:
    def __init__(self, data: bytes) -> None:
        if data[:8] != bytes.fromhex("D0CF11E0A1B11AE1"):
            raise ValueError("to nie jest plik .doc (OLE)")
        self.d = data
        self.ssz = 1 << struct.unpack_from("<H", data, 30)[0]
        self.mssz = 1 << struct.unpack_from("<H", data, 32)[0]
        n_fat, dir_start = struct.unpack_from("<I", data, 44)[0], struct.unpack_from("<I", data, 48)[0]
        self.cutoff = struct.unpack_from("<I", data, 56)[0]
        minifat_start, n_minifat, difat_start, n_difat = struct.unpack_from("<IIII", data, 60)
        difat = list(struct.unpack_from("<109I", data, 76))
        s = difat_start
        for _ in range(n_difat):
            if s in (ENDOFCHAIN, FREESECT):
                break
            ints = struct.unpack_from(f"<{self.ssz // 4}I", self._sec(s))
            difat += ints[:-1]
            s = ints[-1]
        self.fat = []
        for s in difat[:n_fat]:
            self.fat += struct.unpack_from(f"<{self.ssz // 4}I", self._sec(s))
        dirs = self._chain(dir_start)
        self.entries = []
        for i in range(0, len(dirs), 128):
            e = dirs[i:i + 128]
            nlen = struct.unpack_from("<H", e, 64)[0]
            name = e[:max(nlen - 2, 0)].decode("utf-16-le", "ignore")
            typ = e[66]
            start, size = struct.unpack_from("<I", e, 116)[0], struct.unpack_from("<Q", e, 120)[0]
            self.entries.append((name, typ, start, size))
        root = self.entries[0]
        self.ministream = self._chain(root[2])
        self.minifat = []
        if n_minifat:
            mf = self._chain(minifat_start)
            self.minifat = list(struct.unpack_from(f"<{len(mf) // 4}I", mf))

    def _sec(self, n: int) -> bytes:
        o = (n + 1) * self.ssz
        return self.d[o:o + self.ssz]

    def _chain(self, start: int) -> bytes:
        out, s, guard = [], start, 0
        while s not in (ENDOFCHAIN, FREESECT) and s < len(self.fat) and guard < 1_000_000:
            out.append(self._sec(s))
            s = self.fat[s]
            guard += 1
        return b"".join(out)

    def stream(self, name: str) -> bytes:
        for n, typ, start, size in self.entries:
            if n == name and typ == 2:
                if size < self.cutoff:
                    out, s = [], start
                    while s not in (ENDOFCHAIN, FREESECT) and s < len(self.minifat):
                        out.append(self.ministream[s * self.mssz:(s + 1) * self.mssz])
                        s = self.minifat[s]
                    return b"".join(out)[:size]
                return self._chain(start)[:size]
        raise KeyError(name)


def doc_text(data: bytes) -> str:
    ole = _Ole(data)
    wd = ole.stream("WordDocument")
    flags = struct.unpack_from("<H", wd, 0x0A)[0]
    table = ole.stream("1Table" if flags & 0x0200 else "0Table")
    # FibRgFcLcb97: fcClx/lcbClx pod indeksem 33 (pary fc/lcb od offsetu 154)
    csw = struct.unpack_from("<H", wd, 32)[0]
    o = 34 + csw * 2
    cslw = struct.unpack_from("<H", wd, o)[0]
    o += 2 + cslw * 4
    o += 2  # cbRgFcLcb
    fc_clx, lcb_clx = struct.unpack_from("<II", wd, o + 33 * 8)
    clx = table[fc_clx:fc_clx + lcb_clx]
    i = 0
    while i < len(clx) and clx[i] == 0x01:  # Prc – pomijamy
        i += 3 + struct.unpack_from("<H", clx, i + 1)[0]
    if i >= len(clx) or clx[i] != 0x02:
        raise ValueError("brak tablicy fragmentów tekstu")
    lcb = struct.unpack_from("<I", clx, i + 1)[0]
    plc = clx[i + 5:i + 5 + lcb]
    n = (lcb - 4) // 12
    cps = struct.unpack_from(f"<{n + 1}I", plc, 0)
    out = []
    for k in range(n):
        pcd = plc[(n + 1) * 4 + k * 8:(n + 1) * 4 + (k + 1) * 8]
        fc = struct.unpack_from("<I", pcd, 2)[0]
        length = cps[k + 1] - cps[k]
        if fc & 0x40000000:
            start = (fc & 0x3FFFFFFF) // 2
            out.append(wd[start:start + length].decode("cp1252", "replace"))
        else:
            out.append(wd[fc:fc + 2 * length].decode("utf-16-le", "replace"))
    return "".join(out)


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def docx_rows(data: bytes) -> tuple[list[list[str]], list[str]]:
    root = ET.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml"))
    rows = []
    for tr in root.iter(_W + "tr"):
        cells = []
        for tc in tr.findall(_W + "tc"):
            paras = ["".join(t.text or "" for t in p.iter(_W + "t")) for p in tc.iter(_W + "p")]
            cells.append("\n".join(x for x in paras if x.strip()))
        rows.append(cells)
    body = root.find(_W + "body")
    paras = ["".join(t.text or "" for t in p.iter(_W + "t")) for p in body.findall(_W + "p")] if body is not None else []
    return rows, [p for p in paras if p.strip()]


def doc_rows(data: bytes) -> tuple[list[list[str]], list[str]]:
    """Zwraca (wiersze tabel, akapity spoza tabel). Akapity tuż przed tabelą mogą trafić do pierwszej komórki."""
    text = doc_text(data)
    text = re.sub(r"\x13[^\x14\x15]*\x14", "", text).replace("\x15", "").replace("\x0b", "\r")
    rows, paras = [], []
    for part in text.split("\x07\x07"):
        if "\x07" not in part:
            paras += [x.strip() for x in part.split("\r") if x.strip()]
            continue
        cells = part.split("\x07")
        rows.append(["\n".join(x.strip() for x in c.split("\r") if x.strip()) for c in cells])
    return rows, paras


def read_rows(data: bytes) -> tuple[list[list[str]], list[str]]:
    if data[:2] == b"PK":
        return docx_rows(data)
    return doc_rows(data)
