"""Renders decoded histogram/matrix data to PNG graphs under ``artifacts/``.

Uses the non-interactive ``Agg`` matplotlib backend so this works headless
inside the API process (no display server required).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from app.utils.logger import get_logger

logger = get_logger(__name__)

ARTIFACTS_DIR = Path("artifacts")


def _safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "graph"


def _ensure_artifacts_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)


def generate_histogram_graph(
    key: str,
    histogram: Dict[str, Any],
    output_dir: Path = ARTIFACTS_DIR,
    session_id: Optional[str] = None,
) -> Optional[str]:
    """Render one histogram to a PNG bar/line chart. Returns the file path
    (as a string) or ``None`` if rendering failed."""
    x = histogram.get("x")
    y = histogram.get("y")
    if not x or not y:
        logger.warning("Histogram %s has no data to plot", key)
        return None

    _ensure_artifacts_dir(output_dir)
    filename = f"{session_id + '_' if session_id else ''}histogram_{_safe_filename(key)}.png"
    path = output_dir / filename

    fig, ax = plt.subplots(figsize=(6, 4), dpi=120)
    ax.plot(x, y, color="#2b6cb0", linewidth=1.2)
    ax.fill_between(x, y, color="#2b6cb0", alpha=0.15)
    ax.set_title(f"{histogram.get('type', key)} Histogram")
    ax.set_xlabel("Channel")
    ax.set_ylabel("Count")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    try:
        fig.savefig(path)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to save histogram graph for %s", key)
        return None
    finally:
        plt.close(fig)
    return str(path)


def generate_scattergram_graph(
    key: str,
    matrix: Dict[str, Any],
    output_dir: Path = ARTIFACTS_DIR,
    session_id: Optional[str] = None,
) -> Optional[str]:
    """Render one matrix/scattergram to a PNG scatter plot."""
    points = matrix.get("points")
    if not points:
        logger.warning("Matrix %s has no points to plot", key)
        return None

    _ensure_artifacts_dir(output_dir)
    filename = f"{session_id + '_' if session_id else ''}scattergram_{_safe_filename(key)}.png"
    path = output_dir / filename

    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]

    fig, ax = plt.subplots(figsize=(6, 6), dpi=120)
    ax.scatter(xs, ys, s=2, alpha=0.4, color="#c53030")
    ax.set_title(f"{matrix.get('type', key)} Scattergram")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    try:
        fig.savefig(path)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to save scattergram for %s", key)
        return None
    finally:
        plt.close(fig)
    return str(path)
