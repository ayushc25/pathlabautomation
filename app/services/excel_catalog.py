"""Load customer/device test catalogs from the shared workbook."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parents[2]

# Lab-side test catalog (the laboratory's own test IDs, used as the mapping
# target). Updated to the new STAG catalog; the previous SK-lab workbook is
# no longer used for this side of the mapping.
LAB_WORKBOOK_PATH = BASE_DIR / "data" / "new stag test ids.xlsx"

# Device/analyzer-side test catalog (HORIBA Yumizen universal test IDs).
# This sheet is independent of the lab's own ID scheme, so it still comes
# from the original workbook.
MACHINE_WORKBOOK_PATH = BASE_DIR / "data" / "SK CBC and ESR test id list.xlsx"
MACHINE_SHEET_NAME = "HorribaTestIDs"


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _read_rows(ws) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        test_id = _clean(row[0] if len(row) > 0 else "")
        test_type = _clean(row[1] if len(row) > 1 else "")
        category = _clean(row[2] if len(row) > 2 else "")
        test_name = _clean(row[3] if len(row) > 3 else "")
        if not test_id and not test_name:
            continue
        rows.append(
            {
                "test_id": test_id,
                "test_type": test_type,
                "category": category,
                "test_name": test_name,
                "label": f"{test_id} - {test_name}" if test_name else test_id,
            }
        )
    return rows


def _read_lab_rows(ws) -> List[Dict[str, str]]:
    # new stag test ids.xlsx columns: ID, Name, Test Category (no Type column).
    rows: List[Dict[str, str]] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        test_id = _clean(row[0] if len(row) > 0 else "")
        test_name = _clean(row[1] if len(row) > 1 else "")
        category = _clean(row[2] if len(row) > 2 else "")
        if not test_id and not test_name:
            continue
        rows.append(
            {
                "test_id": test_id,
                "test_type": "",
                "category": category,
                "test_name": test_name,
                "label": f"{test_id} - {test_name}" if test_name else test_id,
            }
        )
    return rows


@lru_cache(maxsize=1)
def load_catalog() -> Dict[str, Any]:
    try:
        from openpyxl import load_workbook
    except ModuleNotFoundError:
        return {
            "sheet1": [],
            "sheet2": [],
            "source": str(LAB_WORKBOOK_PATH),
            "machine_source": str(MACHINE_WORKBOOK_PATH),
            "exists": LAB_WORKBOOK_PATH.exists(),
            "error": "openpyxl is not installed in this environment.",
        }

    if not LAB_WORKBOOK_PATH.exists():
        return {
            "sheet1": [],
            "sheet2": [],
            "source": str(LAB_WORKBOOK_PATH),
            "machine_source": str(MACHINE_WORKBOOK_PATH),
            "exists": False,
            "error": "lab workbook not found",
        }

    lab_wb = load_workbook(LAB_WORKBOOK_PATH, data_only=True)
    lab_sheet = lab_wb[lab_wb.sheetnames[0]]
    sheet1 = _read_lab_rows(lab_sheet)

    sheet2: List[Dict[str, str]] = []
    error = None
    if MACHINE_WORKBOOK_PATH.exists():
        machine_wb = load_workbook(MACHINE_WORKBOOK_PATH, data_only=True)
        machine_sheet = (
            machine_wb[MACHINE_SHEET_NAME]
            if MACHINE_SHEET_NAME in machine_wb.sheetnames
            else machine_wb[machine_wb.sheetnames[-1]]
        )
        sheet2 = _read_rows(machine_sheet)
    else:
        error = "machine workbook not found"

    return {
        "sheet1": sheet1,
        "sheet2": sheet2,
        "source": str(LAB_WORKBOOK_PATH),
        "machine_source": str(MACHINE_WORKBOOK_PATH),
        "exists": True,
        "error": error,
    }
