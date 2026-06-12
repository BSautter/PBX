#!/usr/bin/env python3
"""
Tests for PostgreSQL transaction rollback handling
Validates that failed transactions are properly rolled back to prevent
"current transaction is aborted" errors
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


def test_transaction_rollback_on_error() -> None:
    """Test that transactions are rolled back after errors"""
    db, mock_conn = _make_mock_db()

    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # First call: simulate a failed query
    mock_cursor.execute.side_effect = Exception("syntax error")
    result = db.execute("INVALID SQL SYNTAX", ())
    assert result is False

    # Verify rollback was called after the error
    mock_conn.rollback.assert_called()

    # Reset side effect for a successful query
    mock_cursor.execute.side_effect = None
    mock_cursor.execute.reset_mock()
    mock_conn.rollback.reset_mock()

    # Second call: valid query should succeed (rollback cleared the error state)
    result = db.execute(
        "INSERT INTO vip_callers (caller_id, priority_level) VALUES (%s, %s)",
        ("1234567890", 1),
    )
    assert result is True

    db.disconnect()


def test_fetch_one_rollback_on_error() -> None:
    """Test that fetch_one rolls back transaction on error"""
    db, mock_conn = _make_mock_db()

    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # Simulate a failed SELECT query
    mock_cursor.execute.side_effect = Exception("relation does not exist")
    result = db.fetch_one("SELECT * FROM nonexistent_table", ())
    assert result is None

    # Verify rollback was called
    mock_conn.rollback.assert_called()

    # Reset for a successful query
    mock_cursor.execute.side_effect = None
    mock_cursor.execute.reset_mock()
    mock_conn.rollback.reset_mock()

    result = db.execute(
        "INSERT INTO vip_callers (caller_id, priority_level) VALUES (%s, %s)",
        ("9876543210", 1),
    )
    assert result is True

    db.disconnect()


def test_fetch_all_rollback_on_error() -> None:
    """Test that fetch_all rolls back transaction on error"""
    db, mock_conn = _make_mock_db()

    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # Simulate a failed SELECT query
    mock_cursor.execute.side_effect = Exception("relation does not exist")
    result = db.fetch_all("SELECT * FROM nonexistent_table", ())
    assert result == []

    # Verify rollback was called
    mock_conn.rollback.assert_called()

    # Reset for a successful query
    mock_cursor.execute.side_effect = None
    mock_cursor.execute.reset_mock()
    mock_conn.rollback.reset_mock()

    result = db.execute(
        "INSERT INTO vip_callers (caller_id, priority_level) VALUES (%s, %s)",
        ("5555555555", 1),
    )
    assert result is True

    db.disconnect()


def test_schema_migration_rollback() -> None:
    """Test that schema migration errors don't leave transactions open"""
    db, mock_conn = _make_mock_db()

    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # create_tables should succeed (all CREATE TABLE IF NOT EXISTS)
    # Also mock _apply_framework_migrations to avoid import issues
    with patch.object(db, "_apply_framework_migrations"):
        result = db.create_tables()
    assert result is True

    # After table creation, we should be able to execute inserts
    result = db.execute(
        "INSERT INTO vip_callers (caller_id, priority_level) VALUES (%s, %s)",
        ("1112223333", 1),
    )
    assert result is True

    db.disconnect()


def test_permission_error_rollback() -> None:
    """Test that permission errors properly rollback transactions"""
    db, mock_conn = _make_mock_db()

    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # Simulate a failed index creation (non-critical)
    mock_cursor.execute.side_effect = Exception("relation does not exist")
    result = db._execute_with_context(
        "CREATE INDEX test_idx ON nonexistent_table(col)", "index creation", critical=False
    )
    # Non-critical errors that are not permission/already-exists still return False
    # but the rollback should have cleared the connection state

    # Verify rollback was called
    mock_conn.rollback.assert_called()

    # Reset for a successful query
    mock_cursor.execute.side_effect = None
    mock_cursor.execute.reset_mock()
    mock_conn.rollback.reset_mock()

    # After the failed index creation, we should still be able to insert
    result = db.execute(
        "INSERT INTO vip_callers (caller_id, priority_level) VALUES (%s, %s)",
        ("4445556666", 1),
    )
    assert result is True

    db.disconnect()
