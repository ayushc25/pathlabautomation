"""Lookup table for analyzer result codes to human-readable test names.

The mapping is based on the HORIBA Yumizen H500/H500E RAA085BEN PDF
(`Output Format for Host Connection`). It combines the CBC, DIF, and ESR
code tables so callers can resolve a raw result key into a stable display
name and optional panel metadata.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


TEST_CODE_LOOKUP: Dict[str, Dict[str, str]] = {
    # CBC
    "789-8": {"name": "Red Blood Cells", "panel": "CBC"},
    "718-7": {"name": "Hemoglobin Concentration", "panel": "CBC"},
    "4544-3": {"name": "Hematocrit", "panel": "CBC"},
    "787-2": {"name": "Mean Corpuscular Volume", "panel": "CBC"},
    "785-6": {"name": "Mean Corpuscular Hemoglobin", "panel": "CBC"},
    "786-4": {"name": "Mean Corpuscular Hemoglobin Concentration", "panel": "CBC"},
    "21000-5": {"name": "Red Distribution Width Standard Deviation", "panel": "CBC"},
    "788-0": {"name": "Red Distribution Width", "panel": "CBC"},
    "X-MIC": {"name": "Microcytic Red Blood Cells percentage (versus RBC)", "panel": "CBC"},
    "X-MAC": {"name": "Macrocytic Red Blood Cells percentage (versus RBC)", "panel": "CBC"},
    "777-3": {"name": "Platelets", "panel": "CBC"},
    "51637-7": {"name": "Plateletcrit", "panel": "CBC"},
    "51631-0": {"name": "Platelets Distribution Width", "panel": "CBC"},
    "32623-1": {"name": "Mean Platelet Volume", "panel": "CBC"},
    "96354-6": {"name": "Platelets - Large Cell Count", "panel": "CBC"},
    "48386-7": {"name": "Platelets - Large Cell Ratio", "panel": "CBC"},
    "6690-2": {"name": "White Blood Cells", "panel": "CBC"},
    # DIF
    "731-0": {"name": "Lymphocytes absolute value", "panel": "DIF"},
    "736-9": {"name": "Lymphocytes percentage", "panel": "DIF"},
    "742-7": {"name": "Monocytes absolute value", "panel": "DIF"},
    "5905-5": {"name": "Monocytes percentage", "panel": "DIF"},
    "751-8": {"name": "Neutrophils absolute value", "panel": "DIF"},
    "770-8": {"name": "Neutrophils percentage", "panel": "DIF"},
    "711-2": {"name": "Eosinophils absolute value", "panel": "DIF"},
    "713-8": {"name": "Eosinophils percentage", "panel": "DIF"},
    "704-7": {"name": "Basophils absolute value", "panel": "DIF"},
    "706-2": {"name": "Basophils percentage", "panel": "DIF"},
    "53115-2": {"name": "Immature Granulocytic cells absolute value", "panel": "DIF"},
    "71695-1": {"name": "Immature Granulocytic cells percentage", "panel": "DIF"},
    "X-IMM#": {"name": "Immature Monocytic cells absolute value", "panel": "DIF"},
    "X-IMM%": {"name": "Immature Monocytic cells percentage", "panel": "DIF"},
    "X-IML#": {"name": "Immature Lymphocytic cells absolute value", "panel": "DIF"},
    "X-IML%": {"name": "Immature Lymphocytic cells percentage", "panel": "DIF"},
    "43743-4": {"name": "Atypical Lymphocytes absolute value", "panel": "DIF"},
    "42250-1": {"name": "Atypical Lymphocytes percentage", "panel": "DIF"},
    "55432-9": {"name": "Large Immature Cells absolute value", "panel": "DIF"},
    "55433-7": {"name": "Large Immature Cells percentage", "panel": "DIF"},
    # ESR
    "82477-1": {"name": "Erythrocyte Sedimentation Rate", "panel": "ESR"},
    # Analyzer/result aliases that can appear as raw ASTM parameters
    "RBC": {"name": "Red Blood Cells", "panel": "CBC"},
    "HGB": {"name": "Hemoglobin Concentration", "panel": "CBC"},
    "HCT": {"name": "Hematocrit", "panel": "CBC"},
    "MCV": {"name": "Mean Corpuscular Volume", "panel": "CBC"},
    "MCH": {"name": "Mean Corpuscular Hemoglobin", "panel": "CBC"},
    "MCHC": {"name": "Mean Corpuscular Hemoglobin Concentration", "panel": "CBC"},
    "RDW-SD": {"name": "Red Distribution Width Standard Deviation", "panel": "CBC"},
    "RDW-CV": {"name": "Red Distribution Width", "panel": "CBC"},
    "MIC": {"name": "Microcytic Red Blood Cells percentage (versus RBC)", "panel": "CBC"},
    "MAC": {"name": "Macrocytic Red Blood Cells percentage (versus RBC)", "panel": "CBC"},
    "PLT": {"name": "Platelets", "panel": "CBC"},
    "PCT": {"name": "Plateletcrit", "panel": "CBC"},
    "PDW": {"name": "Platelets Distribution Width", "panel": "CBC"},
    "MPV": {"name": "Mean Platelet Volume", "panel": "CBC"},
    "P-LCC": {"name": "Platelets - Large Cell Count", "panel": "CBC"},
    "P-LCR": {"name": "Platelets - Large Cell Ratio", "panel": "CBC"},
    "WBC": {"name": "White Blood Cells", "panel": "CBC"},
    "LYM#": {"name": "Lymphocytes absolute value", "panel": "DIF"},
    "LYM%": {"name": "Lymphocytes percentage", "panel": "DIF"},
    "MON#": {"name": "Monocytes absolute value", "panel": "DIF"},
    "MON%": {"name": "Monocytes percentage", "panel": "DIF"},
    "NEU#": {"name": "Neutrophils absolute value", "panel": "DIF"},
    "NEU%": {"name": "Neutrophils percentage", "panel": "DIF"},
    "EOS#": {"name": "Eosinophils absolute value", "panel": "DIF"},
    "EOS%": {"name": "Eosinophils percentage", "panel": "DIF"},
    "BAS#": {"name": "Basophils absolute value", "panel": "DIF"},
    "BAS%": {"name": "Basophils percentage", "panel": "DIF"},
    "IMG#": {"name": "Immature Granulocytic cells absolute value", "panel": "DIF"},
    "IMG%": {"name": "Immature Granulocytic cells percentage", "panel": "DIF"},
    "IMM#": {"name": "Immature Monocytic cells absolute value", "panel": "DIF"},
    "IMM%": {"name": "Immature Monocytic cells percentage", "panel": "DIF"},
    "IML#": {"name": "Immature Lymphocytic cells absolute value", "panel": "DIF"},
    "IML%": {"name": "Immature Lymphocytic cells percentage", "panel": "DIF"},
    "ALY#": {"name": "Atypical Lymphocytes absolute value", "panel": "DIF"},
    "ALY%": {"name": "Atypical Lymphocytes percentage", "panel": "DIF"},
    "LIC#": {"name": "Large Immature Cells absolute value", "panel": "DIF"},
    "LIC%": {"name": "Large Immature Cells percentage", "panel": "DIF"},
}


def resolve_test_code(code: str) -> Optional[Dict[str, str]]:
    """Return the mapping for a raw analyzer/test code, if known."""
    if not code:
        return None
    return TEST_CODE_LOOKUP.get(code)


def resolve_test_name(code: str, default: Optional[str] = None) -> Optional[str]:
    """Return just the human-readable name for a test code."""
    resolved = resolve_test_code(code)
    if resolved:
        return resolved["name"]
    return default


def all_test_codes() -> Dict[str, Dict[str, str]]:
    """Return a copy of the full lookup table for export or seeding."""
    return dict(TEST_CODE_LOOKUP)
