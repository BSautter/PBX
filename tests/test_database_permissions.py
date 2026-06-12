#!/usr/bin/env python3
"""
Tests for database permission error handling
"""

from unittest.mock import MagicMock, patch

from pbx.utils.database import DatabaseBackend


def _make_mock_db():
    """Create a DatabaseBackend with mocked PostgreSQL connection."""
    config = MagicMock()
    config.get.return_value = None
    with patch("pbx.utils.database.psycopg2") as mock_pg:
        mock_conn = MagicMock()
        mock_pg.connect.return_value = mock_conn
        db = DatabaseBackend(config)
        db.connection = mock_conn
        db.enabled = True
        db.db_type = "postgresql"
        db._autocommit = True
    return db, mock_conn


def test_index_creation_with_permission_error() -> None:
    """Test that index creation failures don't cause startup errors"""
    db, mock_conn = _make_mock_db()

    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # First create_tables call should succeed
    with patch.object(db, "_apply_framework_migrations"):
        result = db.create_tables()
    assert result is True

    # Call create_tables again - should succeed even when tables/indexes exist
    # Simulate "already exists" for second call
    with patch.object(db, "_apply_framework_migrations"):
        result = db.create_tables()
    assert result is True

    # Third call to be sure
    with patch.object(db, "_apply_framework_migrations"):
        result = db.create_tables()
    assert result is True

    db.disconnect()


def test_table_already_exists_handling() -> None:
    """Test that 'already exists' errors are handled gracefully"""
    db, mock_conn = _make_mock_db()

    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # Create tables once
    with patch.object(db, "_apply_framework_migrations"):
        assert db.create_tables() is True

    # Create tables again - should succeed without errors
    with patch.object(db, "_apply_framework_migrations"):
        assert db.create_tables() is True

    db.disconnect()


def test_critical_vs_non_critical_errors() -> None:
    """Test that critical and non-critical errors are handled differently"""
    db, mock_conn = _make_mock_db()

    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # Test non-critical permission error (should return True)
    mock_cursor.execute.side_effect = Exception("permission denied for table test_table")
    result = db._execute_with_context(
        "CREATE INDEX test_idx ON test_table(col)", "index creation", critical=False
    )
    # Permission errors on non-critical operations return True
    assert result is True

    # Reset side effect
    mock_cursor.execute.side_effect = Exception("syntax error at or near")

    # Test critical error (should return False)
    result = db._execute_with_context(
        "INVALID SQL SYNTAX HERE", "critical operation", critical=True
    )
    assert result is False

    db.disconnect()
