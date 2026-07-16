"""Values-only xlsx reading with the stdlib (zipfile + ElementTree) — enough
for the simple single-sheet workbooks UCDP and ACLED publish."""

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


def _col_index(ref: str) -> int:
    """'C5' -> 2"""
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + (ord(ch.upper()) - 64)
        else:
            break
    return n - 1


def xlsx_rows(path: Path) -> list[list[str]]:
    """Values-only reader for simple single-sheet workbooks (stdlib only)."""
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.iter(f"{ns}t")) for si in root]
        sheet = min(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n))
        root = ET.fromstring(z.read(sheet))
    rows = []
    for row in root.iter(f"{ns}row"):
        out: list[str] = []
        for c in row.iter(f"{ns}c"):
            idx = _col_index(c.get("r", ""))
            if c.get("t") == "inlineStr":
                val = "".join(t.text or "" for t in c.iter(f"{ns}t"))
            else:
                v = c.find(f"{ns}v")
                val = "" if v is None or v.text is None else (shared[int(v.text)] if c.get("t") == "s" else v.text)
            while len(out) < idx:
                out.append("")
            out.append(val)
        rows.append(out)
    return rows
