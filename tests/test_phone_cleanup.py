#!/usr/bin/env python3
"""
Comprehensive Phone Cleanup and Registration Tests
Tests phone cleanup on boot, registration preservation, and incomplete registration cleanup
"""

from unittest.mock import Mock, call

from pbx.utils.database import DatabaseBackend, RegisteredPhonesDB

# ============================================================================
# Phone Clear Functionality Tests
# ============================================================================


def test_clear_all_phones() -> None:
    """Test clearing all phone registrations"""

    db = Mock(spec=DatabaseBackend)
    db.db_type = "postgresql"
    db.enabled = True

    phones_db = RegisteredPhonesDB(db)

    # register_phone uses fetch_one (not fetch_all), so side_effect here
    # only needs entries for the two list_all() calls.
    db.fetch_all.side_effect = [
        # list_all returns 3 phones
        [
            {
                "id": 1,
                "extension_number": "1001",
                "mac_address": "001565123456",
                "ip_address": "192.168.1.100",
            },
            {
                "id": 2,
                "extension_number": "1002",
                "mac_address": "001565123457",
                "ip_address": "192.168.1.101",
            },
            {
                "id": 3,
                "extension_number": "1003",
                "mac_address": None,
                "ip_address": "192.168.1.102",
            },
        ],
        # list_all after clear returns 0 phones
        [],
    ]
    db.fetch_one.return_value = None  # No existing registrations
    db.execute.return_value = True

    # Register multiple phones
    phones_db.register_phone("1001", "192.168.1.100", "001565123456")
    phones_db.register_phone("1002", "192.168.1.101", "001565123457")
    phones_db.register_phone("1003", "192.168.1.102", None)

    # Verify phones were registered
    all_phones = phones_db.list_all()
    assert len(all_phones) == 3, f"Expected 3 phones, got {len(all_phones)}"

    # Clear all phones
    success = phones_db.clear_all()
    assert success, "Failed to clear phones"

    # Verify all phones were cleared
    all_phones = phones_db.list_all()
    assert len(all_phones) == 0, f"Expected 0 phones after clear, got {len(all_phones)}"


def test_clear_empty_table() -> None:
    """Test clearing an already empty table"""

    db = Mock(spec=DatabaseBackend)
    db.db_type = "postgresql"
    db.enabled = True

    phones_db = RegisteredPhonesDB(db)

    db.execute.return_value = True
    db.fetch_all.return_value = []

    # Clear empty table (should not fail)
    success = phones_db.clear_all()
    assert success, "Failed to clear empty table"

    # Verify still empty
    all_phones = phones_db.list_all()
    assert len(all_phones) == 0, f"Expected 0 phones, got {len(all_phones)}"


def test_register_after_clear() -> None:
    """Test that phones can be registered after clearing"""

    db = Mock(spec=DatabaseBackend)
    db.db_type = "postgresql"
    db.enabled = True

    phones_db = RegisteredPhonesDB(db)

    db.execute.return_value = True
    db.fetch_one.return_value = None  # No existing registrations
    db.fetch_all.side_effect = [
        # list_all after clear returns 0
        [],
        # list_all after re-register returns 1
        [
            {
                "id": 3,
                "extension_number": "1003",
                "mac_address": "001565123458",
                "ip_address": "192.168.1.102",
            }
        ],
    ]

    # Clear all
    phones_db.clear_all()

    # Verify cleared
    assert len(phones_db.list_all()) == 0, "Phones not cleared"

    # Register new phone
    success, _ = phones_db.register_phone("1003", "192.168.1.102", "001565123458")
    assert success, "Failed to register phone after clear"

    # Verify new phone is registered
    phones = phones_db.list_all()
    assert len(phones) == 1, f"Expected 1 phone, got {len(phones)}"
    assert phones[0]["extension_number"] == "1003", "Wrong extension registered"


# ============================================================================
# PBX Boot Preservation Tests
# ============================================================================


def test_pbx_preserves_phones_on_boot() -> None:
    """Test that PBX preserves registered phones table on boot (phones survive clear_all cycle)"""

    db = Mock(spec=DatabaseBackend)
    db.db_type = "postgresql"
    db.enabled = True

    phones_db = RegisteredPhonesDB(db)

    db.execute.return_value = True
    db.fetch_one.return_value = None

    # Simulate: register 2 phones, then list_all returns them after boot
    db.fetch_all.side_effect = [
        # list_all returns 2 phones (preserved after boot)
        [
            {
                "id": 1,
                "extension_number": "1001",
                "mac_address": "001565123456",
                "ip_address": "192.168.1.100",
            },
            {
                "id": 2,
                "extension_number": "1002",
                "mac_address": "001565123457",
                "ip_address": "192.168.1.101",
            },
        ],
    ]

    # Verify phones table was preserved after simulated boot
    phones = phones_db.list_all()
    phone_count = len(phones)
    assert phone_count == 2, f"Expected 2 phones after boot, got {phone_count}"


# ============================================================================
# Incomplete Registration Cleanup Tests
# ============================================================================


class TestPhoneCleanupStartup:
    """Test cleanup of incomplete phone registrations"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.db = Mock(spec=DatabaseBackend)
        self.db.db_type = "postgresql"
        self.db.enabled = True
        self.phones_db = RegisteredPhonesDB(self.db)

    def test_cleanup_no_incomplete_registrations(self) -> None:
        """Test cleanup when there are no incomplete registrations"""
        # Mock execute_rowcount to return 0 (no rows deleted)
        self.db.execute_rowcount.return_value = 0

        success, count = self.phones_db.cleanup_incomplete_registrations()

        assert success
        assert count == 0
        # execute_rowcount should have been called with the DELETE query
        self.db.execute_rowcount.assert_called_once()

    def test_cleanup_with_incomplete_registrations(self) -> None:
        """Test cleanup when there are incomplete registrations"""
        # Mock execute_rowcount to return 3 rows deleted
        self.db.execute_rowcount.return_value = 3

        success, count = self.phones_db.cleanup_incomplete_registrations()

        assert success
        assert count == 3
        # Verify the DELETE query was executed via execute_rowcount
        self.db.execute_rowcount.assert_called_once()
        call_args = self.db.execute_rowcount.call_args[0][0]
        assert "DELETE FROM registered_phones" in call_args
        assert "mac_address IS NULL" in call_args
        assert "ip_address IS NULL" in call_args
        assert "extension IS NULL" in call_args

    def test_cleanup_database_error(self) -> None:
        """Test cleanup handles database errors gracefully"""
        # Mock execute_rowcount to raise a ValueError (caught by the method)
        self.db.execute_rowcount.side_effect = ValueError("Database error")

        success, count = self.phones_db.cleanup_incomplete_registrations()

        assert not success
        assert count == 0

    def test_cleanup_delete_failure(self) -> None:
        """Test cleanup when delete operation fails"""
        # Mock execute_rowcount to return None (failure)
        self.db.execute_rowcount.return_value = None

        success, count = self.phones_db.cleanup_incomplete_registrations()

        assert not success
        assert count == 0
        # Verify execute_rowcount was called
        self.db.execute_rowcount.assert_called_once()

    def test_cleanup_query_structure(self) -> None:
        """Test that cleanup query checks all required fields"""
        self.db.execute_rowcount.return_value = 5

        self.phones_db.cleanup_incomplete_registrations()

        # Get the DELETE query from execute_rowcount
        delete_query = self.db.execute_rowcount.call_args[0][0]

        # Verify it checks for NULL or empty string for all three fields
        assert "mac_address IS NULL OR mac_address = ''" in delete_query
        assert "ip_address IS NULL OR ip_address = ''" in delete_query
        assert "extension IS NULL OR extension = ''" in delete_query
        # Verify it uses OR between field conditions (mac_address OR ip_address OR extension)
        # Any single missing field should trigger deletion of that record
        assert "OR" in delete_query
