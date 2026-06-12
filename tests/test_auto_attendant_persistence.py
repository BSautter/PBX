"""
Tests for Auto Attendant Database Persistence
Ensures configuration and menu options persist across restarts
"""

import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from pbx.features.auto_attendant import AutoAttendant


class _MockDB:
    """SQLite-backed mock for DatabaseBackend, translating %s -> ? for tests."""

    def __init__(self, db_path: str) -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.enabled = True

    @staticmethod
    def _convert(sql: str) -> str:
        return sql.replace("%s", "?").replace(
            "SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT"
        )

    def execute(self, sql: str, params: tuple = ()) -> bool:
        cursor = self.conn.execute(self._convert(sql), params or ())
        self.conn.commit()
        return cursor.rowcount > 0 or cursor.description is not None

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        cursor = self.conn.execute(self._convert(sql), params or ())
        row = cursor.fetchone()
        return dict(row) if row else None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        cursor = self.conn.execute(self._convert(sql), params or ())
        return [dict(row) for row in cursor.fetchall()]


class MockConfig:
    """Mock configuration for testing"""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def get(self, key: str, default: Any = None) -> Any:
        if key == "database":
            return {"path": self.db_path}
        if key == "auto_attendant":
            return {
                "enabled": True,
                "extension": "0",
                "timeout": 10,
                "max_retries": 3,
                "audio_path": "auto_attendant",
                "menu_options": [
                    {"digit": "1", "destination": "1001", "description": "Sales"},
                    {"digit": "2", "destination": "1002", "description": "Support"},
                ],
            }
        return default


class TestAutoAttendantPersistence:
    """Test auto attendant database persistence"""

    def setup_method(self) -> None:
        """Set up test environment"""
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.config = MockConfig(self.db_path)
        self.mock_db = _MockDB(self.db_path)
        self.mock_pbx = MagicMock()
        self.mock_pbx.database = self.mock_db

    def teardown_method(self) -> None:
        """Clean up test environment"""
        os.close(self.db_fd)
        Path(self.db_path).unlink(missing_ok=True)

    def _create_aa(self) -> AutoAttendant:
        return AutoAttendant(config=self.config, pbx_core=self.mock_pbx)

    def test_initial_config_saved_to_db(self) -> None:
        self._create_aa()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT enabled, extension, timeout, max_retries FROM auto_attendant_config WHERE id = 1"
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == 1  # enabled
        assert row[1] == "0"  # extension
        assert row[2] == 10  # timeout
        assert row[3] == 3  # max_retries

    def test_initial_menu_options_saved_to_db(self) -> None:
        self._create_aa()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT digit, destination, description FROM auto_attendant_menu_options ORDER BY digit"
        )
        rows = cursor.fetchall()
        conn.close()

        assert len(rows) == 2
        assert rows[0][0] == "1"
        assert rows[0][1] == "1001"
        assert rows[0][2] == "Sales"
        assert rows[1][0] == "2"
        assert rows[1][1] == "1002"
        assert rows[1][2] == "Support"

    def test_config_persists_across_restarts(self) -> None:
        aa1 = self._create_aa()
        aa1.update_config(enabled=False, extension="9", timeout=20, max_retries=5)

        aa2 = self._create_aa()

        assert not aa2.enabled
        assert aa2.extension == "9"
        assert aa2.timeout == 20
        assert aa2.max_retries == 5

    def test_menu_options_persist_across_restarts(self) -> None:
        aa1 = self._create_aa()
        aa1.add_menu_option("3", "1003", "Billing")

        aa2 = self._create_aa()

        assert "3" in aa2.menu_options
        assert aa2.menu_options["3"]["destination"] == "1003"
        assert aa2.menu_options["3"]["description"] == "Billing"

    def test_menu_option_update_persists(self) -> None:
        aa1 = self._create_aa()
        aa1.add_menu_option("1", "1005", "New Sales")

        aa2 = self._create_aa()

        assert aa2.menu_options["1"]["destination"] == "1005"
        assert aa2.menu_options["1"]["description"] == "New Sales"

    def test_menu_option_deletion_persists(self) -> None:
        aa1 = self._create_aa()
        aa1.remove_menu_option("1")

        aa2 = self._create_aa()

        assert "1" not in aa2.menu_options
        assert "2" in aa2.menu_options

    def test_database_tables_created(self) -> None:
        self._create_aa()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='auto_attendant_config'"
        )
        assert cursor.fetchone() is not None
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='auto_attendant_menu_options'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_multiple_updates_persist(self) -> None:
        aa1 = self._create_aa()

        aa1.update_config(timeout=15)
        aa1.add_menu_option("3", "1003", "Billing")
        aa1.add_menu_option("4", "1004", "HR")
        aa1.remove_menu_option("2")
        aa1.update_config(max_retries=7)

        aa2 = self._create_aa()

        assert aa2.timeout == 15
        assert aa2.max_retries == 7
        assert "1" in aa2.menu_options
        assert "2" not in aa2.menu_options
        assert "3" in aa2.menu_options
        assert "4" in aa2.menu_options
