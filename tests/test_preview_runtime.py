from __future__ import annotations

import sys
import unittest
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook, load_workbook


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "streamlit"))

from card_renderer import render_card_png  # noqa: E402
from preview_runtime import _add_preview_sheet  # noqa: E402


SAMPLE_CARD = {
    "slide": 1,
    "card_type": "key_levels",
    "headline": "まず見るのはこの2点",
    "key_message": "下は$62,497。上は$65,818を回復できるか。",
    "footer": "キヨサキ · Market Data · Canonical snapshot",
    "qa": {"renderable": True},
    "metrics": [
        {"id": "btc_price", "label": "BTC", "value": "$63,042", "raw_value": 63042},
        {"id": "btc_primary_support", "label": "PRIMARY SUPPORT", "value": "$62,497", "raw_value": 62497},
        {"id": "btc_primary_resistance", "label": "PRIMARY RESISTANCE", "value": "$65,818", "raw_value": 65818},
    ],
}


class PreviewRuntimeTest(unittest.TestCase):
    def test_renderer_returns_real_png_without_reference_sheet_dependency(self) -> None:
        png = render_card_png(SAMPLE_CARD, width=540, height=675)
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertGreater(len(png), 10000)

    def test_excel_preview_sheet_contains_embedded_images(self) -> None:
        workbook = Workbook()
        package = {"cards": {"자율제안": [SAMPLE_CARD]}}
        _add_preview_sheet(workbook, package)
        self.assertIn("Card_Previews", workbook.sheetnames)
        self.assertEqual(len(workbook["Card_Previews"]._images), 1)

        payload = BytesIO()
        workbook.save(payload)
        loaded = load_workbook(BytesIO(payload.getvalue()))
        self.assertIn("Card_Previews", loaded.sheetnames)
        self.assertEqual(len(loaded["Card_Previews"]._images), 1)


if __name__ == "__main__":
    unittest.main()
