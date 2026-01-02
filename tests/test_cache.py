"""
Unit tests for the issue cache functionality in progress.py.

Tests cover:
- Cache loading and validation
- TTL expiration
- Explicit invalidation
- Project ID matching
- Error handling for missing/corrupted cache files
"""

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import tempfile
import shutil

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from progress import (
    get_cache_file_path,
    load_issue_cache,
    is_cache_valid,
    get_cache_age_seconds,
    format_cache_status,
)
from linear_config import LINEAR_ISSUE_CACHE_FILE, DEFAULT_CACHE_TTL_SECONDS


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def valid_cache_data():
    """Create valid cache data."""
    return {
        "cache_version": 1,
        "project_id": "test-project-123",
        "cached_at": datetime.now().isoformat(),
        "ttl_seconds": 180,
        "invalidated_at": None,
        "issues": [
            {
                "id": "issue-1",
                "identifier": "TEST-1",
                "title": "Test Issue",
                "status": "Todo",
                "priority": 2,
                "description": "Test description",
                "updated_at": datetime.now().isoformat(),
            }
        ],
        "counts": {
            "todo": 1,
            "in_progress": 0,
            "done": 0,
            "total": 1,
        },
        "meta_issue": {
            "id": "meta-issue-1",
            "identifier": "TEST-META",
        },
    }


def write_cache(project_dir: Path, data: dict) -> None:
    """Helper to write cache file."""
    cache_file = project_dir / LINEAR_ISSUE_CACHE_FILE
    with open(cache_file, "w") as f:
        json.dump(data, f)


def write_project_state(project_dir: Path, project_id: str) -> None:
    """Helper to write .linear_project.json."""
    state_file = project_dir / ".linear_project.json"
    with open(state_file, "w") as f:
        json.dump({"initialized": True, "project_id": project_id}, f)


class TestGetCacheFilePath:
    """Tests for get_cache_file_path()."""

    def test_returns_correct_path(self, temp_project_dir):
        """Should return project_dir / .linear_issue_cache.json."""
        result = get_cache_file_path(temp_project_dir)
        assert result == temp_project_dir / LINEAR_ISSUE_CACHE_FILE

    def test_path_is_pathlib_path(self, temp_project_dir):
        """Should return a Path object."""
        result = get_cache_file_path(temp_project_dir)
        assert isinstance(result, Path)


class TestLoadIssueCache:
    """Tests for load_issue_cache()."""

    def test_returns_none_when_missing(self, temp_project_dir):
        """Should return None when cache file doesn't exist."""
        result = load_issue_cache(temp_project_dir)
        assert result is None

    def test_returns_none_when_corrupted(self, temp_project_dir):
        """Should return None when cache file is invalid JSON."""
        cache_file = temp_project_dir / LINEAR_ISSUE_CACHE_FILE
        with open(cache_file, "w") as f:
            f.write("not valid json {{{")

        result = load_issue_cache(temp_project_dir)
        assert result is None

    def test_returns_none_when_missing_required_fields(self, temp_project_dir):
        """Should return None when required fields are missing."""
        write_cache(temp_project_dir, {"cache_version": 1})  # Missing other fields

        result = load_issue_cache(temp_project_dir)
        assert result is None

    def test_returns_cache_when_valid(self, temp_project_dir, valid_cache_data):
        """Should return cache dict when file is valid."""
        write_cache(temp_project_dir, valid_cache_data)

        result = load_issue_cache(temp_project_dir)
        assert result is not None
        assert result["cache_version"] == 1
        assert result["project_id"] == "test-project-123"


class TestGetCacheAgeSeconds:
    """Tests for get_cache_age_seconds()."""

    def test_returns_none_when_no_cache(self, temp_project_dir):
        """Should return None when cache doesn't exist."""
        result = get_cache_age_seconds(temp_project_dir)
        assert result is None

    def test_returns_age_for_valid_cache(self, temp_project_dir, valid_cache_data):
        """Should return age in seconds for valid cache."""
        # Set cached_at to 30 seconds ago
        cached_time = datetime.now() - timedelta(seconds=30)
        valid_cache_data["cached_at"] = cached_time.isoformat()
        write_cache(temp_project_dir, valid_cache_data)

        result = get_cache_age_seconds(temp_project_dir)
        assert result is not None
        assert 28 <= result <= 35  # Allow some tolerance

    def test_handles_z_suffix_timestamp(self, temp_project_dir, valid_cache_data):
        """Should handle ISO timestamps with Z suffix."""
        valid_cache_data["cached_at"] = "2025-01-01T12:00:00Z"
        write_cache(temp_project_dir, valid_cache_data)

        result = get_cache_age_seconds(temp_project_dir)
        assert result is not None
        assert result > 0


class TestIsCacheValid:
    """Tests for is_cache_valid()."""

    def test_invalid_when_missing(self, temp_project_dir):
        """Should return (False, reason) when cache is missing."""
        is_valid, reason = is_cache_valid(temp_project_dir)
        assert is_valid is False
        assert "missing" in reason.lower() or "corrupted" in reason.lower()

    def test_invalid_when_corrupted(self, temp_project_dir):
        """Should return (False, reason) when cache is corrupted."""
        cache_file = temp_project_dir / LINEAR_ISSUE_CACHE_FILE
        with open(cache_file, "w") as f:
            f.write("invalid json")

        is_valid, reason = is_cache_valid(temp_project_dir)
        assert is_valid is False

    def test_valid_when_fresh(self, temp_project_dir, valid_cache_data):
        """Should return (True, reason) when cache is fresh."""
        # Set cached_at to just now
        valid_cache_data["cached_at"] = datetime.now().isoformat()
        write_cache(temp_project_dir, valid_cache_data)

        is_valid, reason = is_cache_valid(temp_project_dir)
        assert is_valid is True
        assert "valid" in reason.lower()

    def test_invalid_when_expired(self, temp_project_dir, valid_cache_data):
        """Should return (False, reason) when cache is expired."""
        # Set cached_at to 5 minutes ago (> 180s TTL)
        old_time = datetime.now() - timedelta(minutes=5)
        valid_cache_data["cached_at"] = old_time.isoformat()
        write_cache(temp_project_dir, valid_cache_data)

        is_valid, reason = is_cache_valid(temp_project_dir)
        assert is_valid is False
        assert "expired" in reason.lower()

    def test_invalid_when_invalidated(self, temp_project_dir, valid_cache_data):
        """Should return (False, reason) when invalidated_at is set."""
        valid_cache_data["cached_at"] = datetime.now().isoformat()
        valid_cache_data["invalidated_at"] = datetime.now().isoformat()
        write_cache(temp_project_dir, valid_cache_data)

        is_valid, reason = is_cache_valid(temp_project_dir)
        assert is_valid is False
        assert "invalidated" in reason.lower()

    def test_invalid_when_project_id_mismatch(self, temp_project_dir, valid_cache_data):
        """Should return (False, reason) when project_id doesn't match."""
        valid_cache_data["cached_at"] = datetime.now().isoformat()
        valid_cache_data["project_id"] = "wrong-project"
        write_cache(temp_project_dir, valid_cache_data)

        # Write project state with different ID
        write_project_state(temp_project_dir, "correct-project")

        is_valid, reason = is_cache_valid(temp_project_dir)
        assert is_valid is False
        assert "different project" in reason.lower()

    def test_respects_custom_max_age(self, temp_project_dir, valid_cache_data):
        """Should use custom max_age_seconds when provided."""
        # Set cached_at to 60 seconds ago
        old_time = datetime.now() - timedelta(seconds=60)
        valid_cache_data["cached_at"] = old_time.isoformat()
        write_cache(temp_project_dir, valid_cache_data)

        # Should be valid with 120s max age
        is_valid, _ = is_cache_valid(temp_project_dir, max_age_seconds=120)
        assert is_valid is True

        # Should be invalid with 30s max age
        is_valid, _ = is_cache_valid(temp_project_dir, max_age_seconds=30)
        assert is_valid is False


class TestFormatCacheStatus:
    """Tests for format_cache_status()."""

    def test_shows_valid_status(self, temp_project_dir, valid_cache_data):
        """Should show 'Cache: valid' for valid cache."""
        valid_cache_data["cached_at"] = datetime.now().isoformat()
        write_cache(temp_project_dir, valid_cache_data)

        result = format_cache_status(temp_project_dir)
        assert "Cache:" in result
        assert "valid" in result.lower()

    def test_shows_invalid_status(self, temp_project_dir):
        """Should show 'Cache: invalid' for missing cache."""
        result = format_cache_status(temp_project_dir)
        assert "Cache:" in result
        assert "invalid" in result.lower()

    def test_includes_age_when_valid(self, temp_project_dir, valid_cache_data):
        """Should include age in status for valid cache."""
        valid_cache_data["cached_at"] = datetime.now().isoformat()
        write_cache(temp_project_dir, valid_cache_data)

        result = format_cache_status(temp_project_dir)
        assert "s old" in result.lower() or "second" in result.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
