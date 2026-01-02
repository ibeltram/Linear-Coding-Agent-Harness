"""
Progress Tracking Utilities
===========================

Functions for tracking and displaying progress of the autonomous coding agent.
Progress is tracked via Linear issues, with local state cached in .linear_project.json.

Also includes pending operation tracking for graceful degradation when Linear
is temporarily unavailable.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from linear_config import (
    LINEAR_PROJECT_MARKER,
    LINEAR_ISSUE_CACHE_FILE,
    DEFAULT_CACHE_TTL_SECONDS,
)

# File for tracking pending Linear operations during degraded mode
LINEAR_PENDING_FILE = ".linear_pending.json"


def load_linear_project_state(project_dir: Path) -> dict | None:
    """
    Load the Linear project state from the marker file.

    Args:
        project_dir: Directory containing .linear_project.json

    Returns:
        Project state dict or None if not initialized
    """
    marker_file = project_dir / LINEAR_PROJECT_MARKER

    if not marker_file.exists():
        return None

    try:
        with open(marker_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def is_linear_initialized(project_dir: Path) -> bool:
    """
    Check if Linear project has been initialized.

    Args:
        project_dir: Directory to check

    Returns:
        True if .linear_project.json exists and is valid
    """
    state = load_linear_project_state(project_dir)
    return state is not None and state.get("initialized", False)


def print_session_header(session_num: int, is_initializer: bool) -> None:
    """Print a formatted header for the session."""
    session_type = "INITIALIZER" if is_initializer else "CODING AGENT"

    print("\n" + "=" * 70)
    print(f"  SESSION {session_num}: {session_type}")
    print("=" * 70)
    print()


def print_progress_summary(project_dir: Path) -> None:
    """
    Print a summary of current progress.

    Since actual progress is tracked in Linear, this reads the local
    state file for cached information. The agent updates Linear directly
    and reports progress in session comments.
    """
    state = load_linear_project_state(project_dir)

    if state is None:
        print("\nProgress: Linear project not yet initialized")
        return

    total = state.get("total_issues", 0)
    meta_issue = state.get("meta_issue_id", "unknown")

    print(f"\nLinear Project Status:")
    print(f"  Total issues created: {total}")
    print(f"  META issue ID: {meta_issue}")
    print(f"  (Check Linear for current Done/In Progress/Todo counts)")


def extract_issue_ids_from_response(response_text: str) -> list[str]:
    """
    Extract Linear issue IDs mentioned in agent response text.

    Looks for patterns like:
    - Issue ID: ABC-123
    - issue ABC-123
    - #ABC-123
    - mcp__linear__update_issue with identifier

    Args:
        response_text: The agent's response text

    Returns:
        List of unique issue IDs found
    """
    # Pattern for Linear issue IDs (e.g., COD-123, ABC-456)
    pattern = r'\b([A-Z]{2,5}-\d+)\b'
    matches = re.findall(pattern, response_text)
    return list(set(matches))


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def print_session_summary(
    session_num: int,
    start_time: datetime,
    response_text: str,
    status: str,
    project_dir: Path,
) -> None:
    """
    Print a detailed end-of-session summary.

    Args:
        session_num: The session number
        start_time: When the session started
        response_text: The agent's response text (to extract issue IDs)
        status: The session status ("continue", "error", etc.)
        project_dir: Project directory for loading state
    """
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    # Extract issue IDs from response
    issue_ids = extract_issue_ids_from_response(response_text)

    # Load project state
    state = load_linear_project_state(project_dir)
    project_name = state.get("project_name", "Unknown") if state else "Unknown"

    print("\n" + "-" * 70)
    print("  SESSION SUMMARY")
    print("-" * 70)
    print(f"  Session:     #{session_num}")
    print(f"  Project:     {project_name}")
    print(f"  Duration:    {format_duration(duration)}")
    print(f"  Status:      {status.upper()}")

    if issue_ids:
        print(f"  Issues:      {', '.join(sorted(issue_ids)[:5])}", end="")
        if len(issue_ids) > 5:
            print(f" (+{len(issue_ids) - 5} more)")
        else:
            print()
    else:
        print("  Issues:      No specific issues detected")

    print("-" * 70)


def update_cached_issue_counts(
    project_dir: Path,
    done: int,
    in_progress: int,
    todo: int,
) -> None:
    """
    Update the cached issue counts in .linear_project.json.

    Args:
        project_dir: Project directory
        done: Number of done issues
        in_progress: Number of in-progress issues
        todo: Number of todo issues
    """
    marker_file = project_dir / LINEAR_PROJECT_MARKER

    if not marker_file.exists():
        return

    try:
        with open(marker_file, "r") as f:
            state = json.load(f)

        state["cached_counts"] = {
            "done": done,
            "in_progress": in_progress,
            "todo": todo,
            "updated_at": datetime.now().isoformat(),
        }

        with open(marker_file, "w") as f:
            json.dump(state, f, indent=2)
    except (json.JSONDecodeError, IOError):
        pass


def get_cached_issue_counts(project_dir: Path) -> Optional[dict]:
    """
    Get cached issue counts from .linear_project.json.

    Returns:
        Dict with done, in_progress, todo counts, or None if not cached
    """
    state = load_linear_project_state(project_dir)
    if state and "cached_counts" in state:
        return state["cached_counts"]
    return None


def check_completion_status(project_dir: Path) -> tuple[bool, str]:
    """
    Check if all issues are complete based on cached counts.

    Returns:
        (is_complete, message) tuple
    """
    state = load_linear_project_state(project_dir)
    if not state:
        return False, "Project not initialized"

    counts = state.get("cached_counts")
    if not counts:
        return False, "Issue counts not yet cached (will be updated after Linear query)"

    total = state.get("total_issues", 0)
    done = counts.get("done", 0)
    in_progress = counts.get("in_progress", 0)
    todo = counts.get("todo", 0)

    if done == total and total > 0:
        return True, f"All {total} issues complete!"

    return False, f"Progress: {done}/{total} done, {in_progress} in progress, {todo} todo"


def validate_linear_state(project_dir: Path) -> tuple[bool, list[str]]:
    """
    Validate that .linear_project.json contains valid data.

    Performs local validation only (doesn't call Linear API).
    The agent will query Linear to verify the project/issues exist.

    Args:
        project_dir: Project directory

    Returns:
        (is_valid, list_of_warnings) tuple
    """
    warnings = []
    state = load_linear_project_state(project_dir)

    if not state:
        return False, ["No .linear_project.json found"]

    # Check required fields
    required_fields = ["initialized", "team_id", "project_id", "meta_issue_id"]
    for field in required_fields:
        if field not in state:
            warnings.append(f"Missing required field: {field}")

    # Check initialized flag
    if not state.get("initialized", False):
        warnings.append("Project marked as not initialized")

    # Check total_issues is reasonable
    total = state.get("total_issues", 0)
    if total == 0:
        warnings.append("No issues recorded (total_issues = 0)")
    elif total < 10:
        warnings.append(f"Unusually low issue count: {total}")

    # Check for required IDs
    if not state.get("team_id"):
        warnings.append("Missing team_id")
    if not state.get("project_id"):
        warnings.append("Missing project_id")
    if not state.get("meta_issue_id"):
        warnings.append("Missing meta_issue_id")

    is_valid = len(warnings) == 0
    return is_valid, warnings


def print_validation_result(is_valid: bool, warnings: list[str]) -> None:
    """Print validation results in a formatted way."""
    if is_valid:
        print("  Linear state validation: PASSED")
    else:
        print("  Linear state validation: WARNINGS FOUND")
        for warning in warnings:
            print(f"    - {warning}")


# ============================================================================
# PENDING LINEAR OPERATIONS (for graceful degradation)
# ============================================================================

def load_pending_operations(project_dir: Path) -> dict:
    """
    Load pending Linear operations from file.

    Returns:
        Dict with pending_updates list and metadata
    """
    pending_file = project_dir / LINEAR_PENDING_FILE

    if not pending_file.exists():
        return {"pending_updates": [], "created_at": None}

    try:
        with open(pending_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"pending_updates": [], "created_at": None}


def save_pending_operations(project_dir: Path, pending: dict) -> None:
    """Save pending Linear operations to file."""
    pending_file = project_dir / LINEAR_PENDING_FILE

    pending["updated_at"] = datetime.now().isoformat()
    if not pending.get("created_at"):
        pending["created_at"] = pending["updated_at"]

    with open(pending_file, "w") as f:
        json.dump(pending, f, indent=2)


def add_pending_operation(
    project_dir: Path,
    issue_id: str,
    action: str,
    **kwargs
) -> None:
    """
    Add a pending Linear operation to be retried later.

    Args:
        project_dir: Project directory
        issue_id: Linear issue ID
        action: Operation type (update_status, add_comment, etc.)
        **kwargs: Additional parameters for the operation
    """
    pending = load_pending_operations(project_dir)

    operation = {
        "issue_id": issue_id,
        "action": action,
        "added_at": datetime.now().isoformat(),
        **kwargs
    }

    pending["pending_updates"].append(operation)
    save_pending_operations(project_dir, pending)


def get_pending_operation_count(project_dir: Path) -> int:
    """Get the number of pending Linear operations."""
    pending = load_pending_operations(project_dir)
    return len(pending.get("pending_updates", []))


def clear_pending_operations(project_dir: Path) -> int:
    """
    Clear all pending operations (call after successfully processing them).

    Returns:
        Number of operations that were cleared
    """
    pending = load_pending_operations(project_dir)
    count = len(pending.get("pending_updates", []))

    # Keep an archive of processed operations for debugging
    if count > 0:
        pending["last_cleared"] = datetime.now().isoformat()
        pending["last_cleared_count"] = count
        pending["pending_updates"] = []
        save_pending_operations(project_dir, pending)

    return count


def print_pending_operations_summary(project_dir: Path) -> None:
    """Print a summary of pending Linear operations."""
    pending = load_pending_operations(project_dir)
    count = len(pending.get("pending_updates", []))

    if count > 0:
        print(f"\n  ⚠️  Pending Linear operations: {count}")
        print("     These will be processed when Linear is available.")
        # Show first few operations
        for op in pending["pending_updates"][:3]:
            print(f"     - {op['action']} on {op['issue_id']}")
        if count > 3:
            print(f"     ... and {count - 3} more")


# =============================================================================
# Issue Cache Functions
# =============================================================================
# These functions provide harness-side utilities for the local issue cache.
# The cache itself is written/read by the agent via file operations in prompts.
# =============================================================================


def get_cache_file_path(project_dir: Path) -> Path:
    """
    Get the path to the issue cache file.

    Args:
        project_dir: Project directory

    Returns:
        Path to .linear_issue_cache.json
    """
    return project_dir / LINEAR_ISSUE_CACHE_FILE


def load_issue_cache(project_dir: Path) -> dict | None:
    """
    Load the issue cache from disk.

    Args:
        project_dir: Project directory

    Returns:
        Cache dict or None if file doesn't exist or is malformed
    """
    cache_file = get_cache_file_path(project_dir)

    if not cache_file.exists():
        return None

    try:
        with open(cache_file, "r") as f:
            cache = json.load(f)

        # Validate required fields
        required_fields = ["cache_version", "project_id", "cached_at", "issues"]
        if not all(key in cache for key in required_fields):
            return None

        return cache
    except (json.JSONDecodeError, IOError, KeyError):
        return None


def get_cache_age_seconds(project_dir: Path) -> float | None:
    """
    Get the age of the cache in seconds.

    Args:
        project_dir: Project directory

    Returns:
        Age in seconds or None if cache doesn't exist or has invalid timestamp
    """
    cache = load_issue_cache(project_dir)
    if not cache:
        return None

    try:
        cached_at_str = cache.get("cached_at")
        if not cached_at_str:
            return None

        # Handle both formats: with and without 'Z' suffix
        cached_at_str = cached_at_str.replace("Z", "+00:00")
        if "+" not in cached_at_str and "-" not in cached_at_str[10:]:
            # No timezone info, assume UTC
            cached_at = datetime.fromisoformat(cached_at_str)
        else:
            cached_at = datetime.fromisoformat(cached_at_str)

        # Use UTC-naive comparison
        if cached_at.tzinfo:
            cached_at = cached_at.replace(tzinfo=None)

        age = (datetime.now() - cached_at).total_seconds()
        return max(0, age)  # Ensure non-negative
    except (ValueError, TypeError):
        return None


def is_cache_valid(
    project_dir: Path, max_age_seconds: int | None = None
) -> tuple[bool, str]:
    """
    Check if the issue cache exists and is still valid.

    A cache is valid if:
    1. The cache file exists and is parseable
    2. The cache has not been explicitly invalidated (invalidated_at is null)
    3. The cache is not older than the TTL
    4. The project_id matches (if .linear_project.json exists)

    Args:
        project_dir: Project directory
        max_age_seconds: Override TTL (uses cache's ttl_seconds or default if None)

    Returns:
        (is_valid, reason) where reason explains why cache is invalid
    """
    cache = load_issue_cache(project_dir)

    if not cache:
        return False, "Cache missing or corrupted"

    # Check explicit invalidation
    if cache.get("invalidated_at") is not None:
        return False, "Cache explicitly invalidated"

    # Determine TTL
    ttl = max_age_seconds or cache.get("ttl_seconds") or DEFAULT_CACHE_TTL_SECONDS

    # Check age
    age = get_cache_age_seconds(project_dir)
    if age is None:
        return False, "Cannot determine cache age"

    if age > ttl:
        return False, f"Cache expired ({int(age)}s old, TTL is {ttl}s)"

    # Check project_id matches (if we have project state)
    project_state = load_linear_project_state(project_dir)
    if project_state:
        cache_project_id = cache.get("project_id")
        actual_project_id = project_state.get("project_id")
        if cache_project_id and actual_project_id:
            if cache_project_id != actual_project_id:
                return False, "Cache is for different project"

    return True, f"Cache valid ({int(age)}s old)"


def format_cache_status(project_dir: Path) -> str:
    """
    Get a human-readable cache status string.

    Args:
        project_dir: Project directory

    Returns:
        String like "Cache valid (45s old)" or "Cache invalid (expired)"
    """
    is_valid, reason = is_cache_valid(project_dir)

    if is_valid:
        return f"Cache: {reason}"
    else:
        return f"Cache: invalid - {reason}"
