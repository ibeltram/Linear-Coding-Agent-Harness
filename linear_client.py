"""
Linear API Client
=================

Harness-side Linear API client for fetching issues before agent sessions.
This reduces agent API calls by injecting issue data directly into prompts.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import httpx
except ImportError:
    httpx = None  # Will be checked at runtime

from linear_config import (
    LINEAR_API_KEY,
    LINEAR_ISSUE_CACHE_FILE,
    DEFAULT_CACHE_TTL_SECONDS,
    LINEAR_PROJECT_MARKER,
)


LINEAR_API_URL = "https://api.linear.app/graphql"


class LinearClientError(Exception):
    """Raised when Linear API operations fail."""
    pass


def get_api_key() -> str:
    """Get Linear API key from environment."""
    key = LINEAR_API_KEY
    if not key:
        # Try loading from .env file
        env_file = Path(__file__).parent / ".env"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    if line.startswith("LINEAR_API_KEY="):
                        key = line.split("=", 1)[1].strip()
                        break

    if not key:
        raise LinearClientError("LINEAR_API_KEY not found in environment")
    return key


def load_project_state(project_dir: Path) -> Optional[dict]:
    """Load .linear_project.json to get project info."""
    state_file = project_dir / LINEAR_PROJECT_MARKER
    if not state_file.exists():
        return None

    try:
        with open(state_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def load_cache(project_dir: Path) -> Optional[dict]:
    """Load the issue cache from disk."""
    cache_file = project_dir / LINEAR_ISSUE_CACHE_FILE

    if not cache_file.exists():
        return None

    try:
        with open(cache_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def is_cache_valid(cache: dict, project_id: str, max_age: int = DEFAULT_CACHE_TTL_SECONDS) -> bool:
    """Check if cache is still valid."""
    if not cache:
        return False

    # Check invalidation
    if cache.get("invalidated_at"):
        return False

    # Check project ID matches
    if cache.get("project_id") != project_id:
        return False

    # Check age
    try:
        cached_at_str = cache.get("cached_at", "")
        cached_at_str = cached_at_str.replace("Z", "+00:00")
        if "+" not in cached_at_str and "-" not in cached_at_str[10:]:
            cached_at = datetime.fromisoformat(cached_at_str)
        else:
            cached_at = datetime.fromisoformat(cached_at_str)

        if cached_at.tzinfo:
            cached_at = cached_at.replace(tzinfo=None)

        age = (datetime.now() - cached_at).total_seconds()
        return age <= max_age
    except (ValueError, TypeError):
        return False


def save_cache(project_dir: Path, cache_data: dict) -> None:
    """Save cache to disk."""
    cache_file = project_dir / LINEAR_ISSUE_CACHE_FILE
    with open(cache_file, "w") as f:
        json.dump(cache_data, f, indent=2)


def fetch_issues_from_api(api_key: str, project_id: str) -> list[dict]:
    """Fetch all issues from Linear API."""
    if httpx is None:
        raise LinearClientError("httpx not installed. Run: pip install httpx")

    query = """
    query($projectId: ID!, $after: String) {
        issues(
            filter: { project: { id: { eq: $projectId } } }
            first: 100
            after: $after
        ) {
            pageInfo {
                hasNextPage
                endCursor
            }
            nodes {
                id
                identifier
                title
                description
                priority
                updatedAt
                state {
                    name
                }
            }
        }
    }
    """

    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
    }

    all_issues = []
    cursor = None

    with httpx.Client(timeout=30.0) as client:
        while True:
            variables = {"projectId": project_id}
            if cursor:
                variables["after"] = cursor

            try:
                response = client.post(
                    LINEAR_API_URL,
                    headers=headers,
                    json={"query": query, "variables": variables},
                )
            except httpx.RequestError as e:
                raise LinearClientError(f"Linear API request failed: {e}")

            if response.status_code != 200:
                raise LinearClientError(f"Linear API returned {response.status_code}: {response.text}")

            data = response.json()

            if "errors" in data:
                raise LinearClientError(f"Linear API errors: {json.dumps(data['errors'])}")

            issues_data = data["data"]["issues"]
            nodes = issues_data["nodes"]

            for node in nodes:
                all_issues.append({
                    "id": node["id"],
                    "identifier": node["identifier"],
                    "title": node["title"],
                    "description": node.get("description"),
                    "priority": node.get("priority", 0),
                    "status": node["state"]["name"] if node.get("state") else "Unknown",
                    "updated_at": node.get("updatedAt"),
                })

            page_info = issues_data["pageInfo"]
            if not page_info["hasNextPage"]:
                break

            cursor = page_info["endCursor"]

    return all_issues


def count_by_status(issues: list[dict]) -> dict:
    """Count issues by status."""
    counts = {"todo": 0, "in_progress": 0, "done": 0, "total": len(issues)}

    for issue in issues:
        status = issue.get("status", "").lower().replace(" ", "_")
        if status in ("todo", "backlog", "triage"):
            counts["todo"] += 1
        elif status == "in_progress":
            counts["in_progress"] += 1
        elif status in ("done", "completed", "closed"):
            counts["done"] += 1

    return counts


def find_meta_issue(issues: list[dict]) -> Optional[dict]:
    """Find the META issue from the issue list."""
    for issue in issues:
        if "[META]" in issue.get("title", ""):
            return {
                "id": issue["id"],
                "identifier": issue["identifier"],
                "title": issue["title"],
            }
    return None


def get_issues_for_session(
    project_dir: Path,
    force_refresh: bool = False,
    cache_ttl: int = DEFAULT_CACHE_TTL_SECONDS,
) -> Optional[dict]:
    """
    Get issues for an agent session.

    Uses cache if valid, otherwise fetches from Linear API.
    Returns None if project is not initialized or API fails.

    Args:
        project_dir: Project directory
        force_refresh: If True, ignore cache and fetch fresh data
        cache_ttl: Cache time-to-live in seconds

    Returns:
        Dict with issues, counts, meta_issue, and cache metadata
        Or None if unavailable
    """
    # Load project state
    project_state = load_project_state(project_dir)
    if not project_state:
        return None

    project_id = project_state.get("project_id")
    if not project_id:
        return None

    # Check cache
    if not force_refresh:
        cache = load_cache(project_dir)
        if cache and is_cache_valid(cache, project_id, cache_ttl):
            cache["_from_cache"] = True
            cache["_cache_age"] = _get_cache_age(cache)
            return cache

    # Fetch from API
    try:
        api_key = get_api_key()
        issues = fetch_issues_from_api(api_key, project_id)
    except LinearClientError as e:
        print(f"  ⚠️  Linear API error: {e}")
        # Return stale cache if available
        cache = load_cache(project_dir)
        if cache:
            cache["_from_cache"] = True
            cache["_stale"] = True
            cache["_cache_age"] = _get_cache_age(cache)
            return cache
        return None

    # Build cache data
    cache_data = {
        "cache_version": 1,
        "project_id": project_id,
        "cached_at": datetime.utcnow().isoformat() + "Z",
        "ttl_seconds": cache_ttl,
        "invalidated_at": None,
        "issues": issues,
        "counts": count_by_status(issues),
        "meta_issue": find_meta_issue(issues),
        "_from_cache": False,
    }

    # Save cache
    save_cache(project_dir, cache_data)

    return cache_data


def _get_cache_age(cache: dict) -> int:
    """Get cache age in seconds."""
    try:
        cached_at_str = cache.get("cached_at", "")
        cached_at_str = cached_at_str.replace("Z", "+00:00")
        if "+" not in cached_at_str and "-" not in cached_at_str[10:]:
            cached_at = datetime.fromisoformat(cached_at_str)
        else:
            cached_at = datetime.fromisoformat(cached_at_str)

        if cached_at.tzinfo:
            cached_at = cached_at.replace(tzinfo=None)

        return int((datetime.now() - cached_at).total_seconds())
    except (ValueError, TypeError):
        return -1


def format_issues_for_prompt(issue_data: dict) -> str:
    """
    Format issue data for injection into agent prompts.

    Returns a markdown-formatted string with all issue information
    that the agent needs to select and work on issues.
    """
    if not issue_data:
        return "**Issue data unavailable.** Query Linear directly using MCP tools."

    issues = issue_data.get("issues", [])
    counts = issue_data.get("counts", {})
    meta_issue = issue_data.get("meta_issue")
    from_cache = issue_data.get("_from_cache", False)
    stale = issue_data.get("_stale", False)
    cache_age = issue_data.get("_cache_age", 0)

    lines = []

    # Header with cache status
    if from_cache:
        if stale:
            lines.append(f"**⚠️ Issue data from STALE cache ({cache_age}s old) - Linear API unavailable**")
        else:
            lines.append(f"**Issue data from cache ({cache_age}s old)**")
    else:
        lines.append("**Issue data fresh from Linear API**")

    lines.append("")

    # Progress summary
    lines.append(f"### Progress: {counts.get('done', 0)}/{counts.get('total', 0)} Done")
    lines.append(f"- Todo: {counts.get('todo', 0)}")
    lines.append(f"- In Progress: {counts.get('in_progress', 0)}")
    lines.append(f"- Done: {counts.get('done', 0)}")
    lines.append("")

    # META issue
    if meta_issue:
        lines.append(f"### META Issue: {meta_issue.get('identifier')} - {meta_issue.get('title')}")
        lines.append(f"ID: `{meta_issue.get('id')}`")
        lines.append("")

    # In Progress issues (priority!)
    in_progress = [i for i in issues if i.get("status", "").lower() == "in progress"]
    if in_progress:
        lines.append("### ⚠️ IN PROGRESS ISSUES (Priority!)")
        lines.append("*These may be stale from interrupted sessions - check and complete first*")
        lines.append("")
        for issue in in_progress:
            lines.append(f"- **{issue['identifier']}**: {issue['title']}")
            lines.append(f"  - ID: `{issue['id']}`")
            lines.append(f"  - Priority: {issue.get('priority', 'None')}")
            lines.append(f"  - Updated: {issue.get('updated_at', 'Unknown')}")
        lines.append("")

    # Todo issues (sorted by priority)
    todo = [i for i in issues if i.get("status", "").lower() in ("todo", "backlog", "triage")]
    todo.sort(key=lambda x: x.get("priority", 99) or 99)

    if todo:
        lines.append("### TODO ISSUES (by priority)")
        lines.append("")
        for issue in todo[:15]:  # Show top 15
            priority_str = f"P{issue.get('priority', '?')}" if issue.get('priority') else "P?"
            lines.append(f"- **[{priority_str}] {issue['identifier']}**: {issue['title']}")
            lines.append(f"  - ID: `{issue['id']}`")

        if len(todo) > 15:
            lines.append(f"- ... and {len(todo) - 15} more Todo issues")
        lines.append("")

    # Done count
    done_count = len([i for i in issues if i.get("status", "").lower() in ("done", "completed", "closed")])
    if done_count > 0:
        lines.append(f"### DONE: {done_count} issues completed")
        lines.append("*(Use Linear MCP to query specific Done issues if needed for verification)*")
        lines.append("")

    return "\n".join(lines)


def get_issue_by_identifier(issue_data: dict, identifier: str) -> Optional[dict]:
    """Get a specific issue by its identifier (e.g., 'COD-123')."""
    if not issue_data:
        return None

    for issue in issue_data.get("issues", []):
        if issue.get("identifier") == identifier:
            return issue
    return None


def get_issue_description(issue_data: dict, identifier: str) -> Optional[str]:
    """Get the full description of an issue by identifier."""
    issue = get_issue_by_identifier(issue_data, identifier)
    if issue:
        return issue.get("description")
    return None
