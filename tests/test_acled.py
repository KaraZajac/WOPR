import tempfile
import unittest
import zipfile
from pathlib import Path

from tocsin.pipeline.xlsx import _col_index, xlsx_rows

SHEET = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c></row>
<row r="2"><c r="A2" t="s"><v>3</v></c><c r="B2"><v>2026</v></c><c r="C2"><v>42</v></c></row>
<row r="3"><c r="A3" t="inlineStr"><is><t>Inline</t></is></c><c r="C3"><v>7</v></c></row>
</sheetData></worksheet>"""

SHARED = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="4" uniqueCount="4">
<si><t>COUNTRY</t></si><si><t>YEAR</t></si><si><t>EVENTS</t></si><si><t>Ethiopia</t></si></sst>"""


class TestXlsxReader(unittest.TestCase):
    def test_col_index(self):
        self.assertEqual(_col_index("A1"), 0)
        self.assertEqual(_col_index("C5"), 2)
        self.assertEqual(_col_index("AA2"), 26)

    def test_reads_shared_inline_and_sparse(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.xlsx"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("xl/worksheets/sheet1.xml", SHEET)
                z.writestr("xl/sharedStrings.xml", SHARED)
            rows = xlsx_rows(path)
        self.assertEqual(rows[0], ["COUNTRY", "YEAR", "EVENTS"])
        self.assertEqual(rows[1], ["Ethiopia", "2026", "42"])
        self.assertEqual(rows[2], ["Inline", "", "7"])  # sparse B3 filled as empty


if __name__ == "__main__":
    unittest.main()
