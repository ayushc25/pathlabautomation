"""Generates a realistic, checksum-valid synthetic ASTM capture file
(``examples/sample_capture.txt``) and the corresponding decoded response
(``examples/sample_response.json``) for documentation purposes.

Run from the project root:

    python -m examples.generate_example
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.helpers import build_capture, deflate_base64_floats  # noqa: E402
from app.services.report_generator import generate_report  # noqa: E402

EXAMPLES_DIR = Path(__file__).resolve().parent


def _records() -> list[str]:
    rbc_hist = deflate_base64_floats([abs(50 - i) * 0.8 for i in range(60)])
    plt_hist = deflate_base64_floats([abs(30 - i) * 1.2 for i in range(60)])
    wbc_hist = deflate_base64_floats([abs(20 - i) * 2.0 for i in range(40)])
    lmne_matrix = deflate_base64_floats(
        [v for i in range(50) for v in (float(i % 10), float((i * 3) % 20))]
    )
    eos_matrix = deflate_base64_floats(
        [v for i in range(40) for v in (float(i % 8), float((i * 2) % 15))]
    )
    return [
        "H|\\^&|||HORIBA^Yumizen_H500|||||LIS||P|1|20260729093000",
        "P|1||PID-00123||Doe^Jane^A||19850304|F|||||Dr.House",
        "O|1|SAMP-2026-0456||^^^WBC\\^^^RBC\\^^^HGB\\^^^PLT|R|20260729092500",
        "R|1|^^^WBC|6.42|10^3/uL|4.00-10.00|N||F|||20260729093015",
        "R|2|^^^RBC|4.81|10^6/uL|4.20-6.10|N||F|||20260729093015",
        "R|3|^^^HGB|14.3|g/dL|12.0-16.0|N||F|||20260729093015",
        "R|4|^^^PLT|312|10^3/uL|150-400|N||F|||20260729093015",
        "R|5|^^^EOS%|9.8|%|0.0-7.0|H||F|||20260729093015",
        "C|1|I|^^Elevated eosinophil percentage|G",
        f"M|1|HISTOGRAM|RBC|RBCVolHist|FLOATLE-stream/deflate:base64^{rbc_hist}",
        f"M|2|HISTOGRAM|PLT|PltVolHist|FLOATLE-stream/deflate:base64^{plt_hist}",
        f"M|3|HISTOGRAM|WBC|WbcVolHist|FLOATLE-stream/deflate:base64^{wbc_hist}",
        f"M|4|MATRIX|LMNE|LmneScatter|FLOATLE-stream/deflate:base64^{lmne_matrix}",
        f"M|5|MATRIX|EOS|EosScatter|FLOATLE-stream/deflate:base64^{eos_matrix}",
        "L|1|N",
    ]


def main() -> None:
    capture_text = build_capture(_records())
    (EXAMPLES_DIR / "sample_capture.txt").write_text(capture_text, encoding="utf-8")

    report = generate_report(
        capture_text,
        session_id="example",
        artifacts_dir=Path("artifacts"),
    )
    (EXAMPLES_DIR / "sample_response.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print("Wrote examples/sample_capture.txt and examples/sample_response.json")


if __name__ == "__main__":
    main()
