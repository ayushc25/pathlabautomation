"""Lightweight SQLite persistence for raw captures and decoded reports."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, Optional


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
RAW_DB_PATH = DATA_DIR / "raw_captures.sqlite3"
DECODED_DB_PATH = DATA_DIR / "decoded_results.sqlite3"
MAPPING_DB_PATH = DATA_DIR / "mapping_config.sqlite3"

_lock = threading.Lock()


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_raw_db() -> None:
    with _connect(RAW_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_captures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                filename TEXT,
                payload TEXT NOT NULL,
                received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def _init_decoded_db() -> None:
    with _connect(DECODED_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decoded_captures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                raw_capture_id INTEGER,
                payload TEXT NOT NULL,
                decoded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(raw_capture_id) REFERENCES raw_captures(id)
            )
            """
        )
        conn.commit()


def _init_mapping_db() -> None:
    with _connect(MAPPING_DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS machines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                machine_name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, machine_name),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS machine_test_master (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id INTEGER NOT NULL,
                test_id TEXT NOT NULL,
                test_type TEXT,
                category TEXT,
                test_name TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(machine_id, test_id),
                FOREIGN KEY(machine_id) REFERENCES machines(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lab_test_master (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id TEXT NOT NULL UNIQUE,
                test_type TEXT,
                category TEXT,
                test_name TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                machine_id INTEGER NOT NULL,
                machine_test_master_id INTEGER NOT NULL,
                lab_test_master_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, machine_id, machine_test_master_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(machine_id) REFERENCES machines(id) ON DELETE CASCADE,
                FOREIGN KEY(machine_test_master_id) REFERENCES machine_test_master(id) ON DELETE CASCADE,
                FOREIGN KEY(lab_test_master_id) REFERENCES lab_test_master(id) ON DELETE CASCADE
            )
            """
        )

        # Backward-compatible migration from the earlier installation tables.
        existing_tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "installations" in existing_tables and "installation_mappings" in existing_tables:
            conn.execute(
                """
                INSERT OR IGNORE INTO users (id, user_name, created_at, updated_at)
                SELECT id, customer_name, created_at, updated_at FROM installations
                """
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO machines (id, user_id, machine_name, created_at, updated_at)
                SELECT im.id, i.id, i.device_name, i.created_at, i.updated_at
                FROM installations i
                JOIN installation_mappings im ON im.installation_id = i.id
                GROUP BY i.id, i.device_name
                """
            )
        conn.commit()


def init_databases() -> None:
    with _lock:
        _init_raw_db()
        _init_decoded_db()
        _init_mapping_db()


def save_raw_capture(source: str, payload: str, filename: Optional[str] = None) -> int:
    init_databases()
    with _lock, _connect(RAW_DB_PATH) as conn:
        cursor = conn.execute(
            "INSERT INTO raw_captures (source, filename, payload) VALUES (?, ?, ?)",
            (source, filename, payload),
        )
        conn.commit()
        return int(cursor.lastrowid)


def load_raw_captures(limit: int = 100) -> list[Dict[str, Any]]:
    init_databases()
    with _lock, _connect(RAW_DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, source, filename, payload, datetime(received_at, 'localtime') AS received_at FROM raw_captures "
            "ORDER BY datetime(received_at) DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def load_raw_capture(raw_capture_id: int) -> Optional[Dict[str, Any]]:
    init_databases()
    with _lock, _connect(RAW_DB_PATH) as conn:
        row = conn.execute(
            "SELECT id, source, filename, payload, datetime(received_at, 'localtime') AS received_at FROM raw_captures WHERE id = ?",
            (raw_capture_id,),
        ).fetchone()
        return dict(row) if row else None


def save_decoded_capture(source: str, payload: Dict[str, Any], raw_capture_id: Optional[int] = None) -> int:
    init_databases()
    with _lock, _connect(DECODED_DB_PATH) as conn:
        cursor = conn.execute(
            "INSERT INTO decoded_captures (source, raw_capture_id, payload) VALUES (?, ?, ?)",
            (source, raw_capture_id, json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()
        return int(cursor.lastrowid)


def upsert_user(user_name: str) -> int:
    init_databases()
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO users (user_name)
            VALUES (?)
            ON CONFLICT(user_name)
            DO UPDATE SET updated_at = CURRENT_TIMESTAMP
            """,
            (user_name,),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM users WHERE user_name = ?",
            (user_name,),
        ).fetchone()
        return int(row["id"])


def upsert_machine(user_id: int, machine_name: str) -> int:
    init_databases()
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO machines (user_id, machine_name)
            VALUES (?, ?)
            ON CONFLICT(user_id, machine_name)
            DO UPDATE SET updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, machine_name),
        )
        conn.execute(
            "UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (user_id,),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM machines WHERE user_id = ? AND machine_name = ?",
            (user_id, machine_name),
        ).fetchone()
        return int(row["id"])


def load_users() -> list[Dict[str, Any]]:
    init_databases()
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        rows = conn.execute("SELECT id, user_name FROM users ORDER BY user_name ASC").fetchall()
        return [dict(row) for row in rows]


def load_machines(user_id: int) -> list[Dict[str, Any]]:
    init_databases()
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, user_id, machine_name FROM machines WHERE user_id = ? ORDER BY machine_name ASC",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def save_catalog_rows(rows: list[Dict[str, Any]], target: str) -> None:
    init_databases()
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        if target == "machine":
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO machine_test_master (machine_id, test_id, test_type, category, test_name)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(machine_id, test_id)
                    DO UPDATE SET test_type = excluded.test_type, category = excluded.category, test_name = excluded.test_name
                    """,
                    (
                        row["machine_id"],
                        row["test_id"],
                        row.get("test_type", ""),
                        row.get("category", ""),
                        row.get("test_name", ""),
                    ),
                )
        else:
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO lab_test_master (test_id, test_type, category, test_name)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(test_id)
                    DO UPDATE SET test_type = excluded.test_type, category = excluded.category, test_name = excluded.test_name
                    """,
                    (
                        row["test_id"],
                        row.get("test_type", ""),
                        row.get("category", ""),
                        row.get("test_name", ""),
                    ),
                )
        conn.commit()


def load_machine_test_master(user_id: int, machine_id: int) -> list[Dict[str, Any]]:
    init_databases()
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT id, machine_id, test_id, test_type, category, test_name
            FROM machine_test_master
            WHERE machine_id = ?
            ORDER BY test_id ASC
            """,
            (machine_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def load_lab_test_master() -> list[Dict[str, Any]]:
    init_databases()
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, test_id, test_type, category, test_name FROM lab_test_master ORDER BY test_id ASC"
        ).fetchall()
        return [dict(row) for row in rows]


def get_or_create_lab_test(test_id: str) -> int:
    init_databases()
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO lab_test_master (test_id)
            VALUES (?)
            ON CONFLICT(test_id) DO NOTHING
            """,
            (test_id,)
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM lab_test_master WHERE test_id = ?",
            (test_id,)
        ).fetchone()
        return int(row["id"])


def save_test_mapping(user_id: int, machine_id: int, machine_test_master_id: int, lab_test_master_id: int) -> int:
    init_databases()
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        existing = conn.execute(
            """
            SELECT id FROM test_mappings
            WHERE user_id = ? AND machine_id = ? AND machine_test_master_id = ?
            """,
            (user_id, machine_id, machine_test_master_id),
        ).fetchone()
        if existing:
            return int(existing["id"])
        conn.execute(
            """
            INSERT INTO test_mappings (user_id, machine_id, machine_test_master_id, lab_test_master_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, machine_id, machine_test_master_id)
            DO UPDATE SET lab_test_master_id = excluded.lab_test_master_id, updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, machine_id, machine_test_master_id, lab_test_master_id),
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT id FROM test_mappings
            WHERE user_id = ? AND machine_id = ? AND machine_test_master_id = ?
            """,
            (user_id, machine_id, machine_test_master_id),
        ).fetchone()
        return int(row["id"])


def test_mapping_exists(user_id: int, machine_id: int, machine_test_master_id: int) -> bool:
    init_databases()
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT 1 FROM test_mappings
            WHERE user_id = ? AND machine_id = ? AND machine_test_master_id = ?
            LIMIT 1
            """,
            (user_id, machine_id, machine_test_master_id),
        ).fetchone()
        return row is not None


def load_test_mappings(user_id: int, machine_id: int) -> list[Dict[str, Any]]:
    init_databases()
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT tm.id, tm.user_id, tm.machine_id, tm.machine_test_master_id, tm.lab_test_master_id,
                   mtt.test_id AS machine_test_id, mtt.test_name AS machine_test_name,
                   ltt.test_id AS lab_test_id, ltt.test_name AS lab_test_name
            FROM test_mappings tm
            JOIN machine_test_master mtt ON mtt.id = tm.machine_test_master_id
            JOIN lab_test_master ltt ON ltt.id = tm.lab_test_master_id
            WHERE tm.user_id = ? AND tm.machine_id = ?
            ORDER BY tm.id DESC
            """,
            (user_id, machine_id),
        ).fetchall()
        return [dict(row) for row in rows]


def delete_test_mapping(mapping_id: int) -> None:
    init_databases()
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        conn.execute("DELETE FROM test_mappings WHERE id = ?", (mapping_id,))
        conn.commit()


def load_latest_installation_mapping_lookup() -> Dict[str, str]:
    init_databases()
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        mapping = conn.execute(
            "SELECT user_id, machine_id FROM test_mappings ORDER BY updated_at DESC, id DESC LIMIT 1"
        ).fetchone()
        if not mapping:
            return {}
        rows = conn.execute(
            """
            SELECT mtt.test_id AS machine_test_id, ltt.test_id AS final_json_field
            FROM test_mappings tm
            JOIN machine_test_master mtt ON mtt.id = tm.machine_test_master_id
            JOIN lab_test_master ltt ON ltt.id = tm.lab_test_master_id
            WHERE tm.user_id = ? AND tm.machine_id = ?
            ORDER BY tm.id ASC
            """,
            (int(mapping["user_id"]), int(mapping["machine_id"])),
        ).fetchall()
        lookup: Dict[str, str] = {}
        for row in rows:
            machine_test_id = str(row["machine_test_id"] or "").strip()
            final_json_field = str(row["final_json_field"] or "").strip()
            if machine_test_id and final_json_field:
                lookup[machine_test_id] = final_json_field
        return lookup
