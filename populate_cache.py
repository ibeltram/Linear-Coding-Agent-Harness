#!/usr/bin/env python3
"""
Populate Linear Issue Cache
============================

Manually queries Linear API and creates the .linear_issue_cache.json file.
Use this when Linear is being rate-limited and agents can't fetch issues.

Usage:
    python populate_cache.py --project-dir ./generations/codearena

The cache will be used by subsequent agent sessions, reducing API calls.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)


LINEAR_API_URL = "https://api.linear.app/graphql"
CACHE_FILE = ".linear_issue_cache.json"
PROJECT_STATE_FILE = ".linear_project.json"


def get_linear_api_key() -> str:
    """Get Linear API key from environment or .env file."""
    key = os.environ.get("LINEAR_API_KEY")

    # Try loading from .env file if not in environment
    if not key:
        env_file = Path(__file__).parent / ".env"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    if line.startswith("LINEAR_API_KEY="):
                        key = line.split("=", 1)[1].strip()
                        break

    if not key:
        print("ERROR: LINEAR_API_KEY not found in environment or .env file")
        sys.exit(1)
    return key


def load_project_state(project_dir: Path) -> dict:
    """Load .linear_project.json to get project_id."""
    state_file = project_dir / PROJECT_STATE_FILE
    if not state_file.exists():
        print(f"ERROR: {PROJECT_STATE_FILE} not found in {project_dir}")
        print("Is this an initialized project?")
        sys.exit(1)

    with open(state_file) as f:
        return json.load(f)


def fetch_issues(api_key: str, project_id: str) -> list[dict]:
    """Fetch all issues from Linear for the given project."""
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
    page = 1

    print(f"Fetching issues for project {project_id}...")

    with httpx.Client(timeout=30.0) as client:
        while True:
            variables = {"projectId": project_id}
            if cursor:
                variables["after"] = cursor

            response = client.post(
                LINEAR_API_URL,
                headers=headers,
                json={"query": query, "variables": variables},
            )

            if response.status_code != 200:
                print(f"ERROR: Linear API returned {response.status_code}")
                print(response.text)
                sys.exit(1)

            data = response.json()

            if "errors" in data:
                print(f"ERROR: Linear API returned errors:")
                print(json.dumps(data["errors"], indent=2))
                sys.exit(1)

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

            print(f"  Page {page}: fetched {len(nodes)} issues (total: {len(all_issues)})")

            page_info = issues_data["pageInfo"]
            if not page_info["hasNextPage"]:
                break

            cursor = page_info["endCursor"]
            page += 1

    return all_issues


def find_meta_issue(issues: list[dict]) -> dict | None:
    """Find the META issue from the issue list."""
    for issue in issues:
        if "[META]" in issue.get("title", ""):
            return {
                "id": issue["id"],
                "identifier": issue["identifier"],
            }
    return None


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


def write_cache(project_dir: Path, project_id: str, issues: list[dict]) -> None:
    """Write the cache file."""
    cache_file = project_dir / CACHE_FILE

    meta_issue = find_meta_issue(issues)
    counts = count_by_status(issues)

    cache_data = {
        "cache_version": 1,
        "project_id": project_id,
        "cached_at": datetime.utcnow().isoformat() + "Z",
        "ttl_seconds": 180,
        "invalidated_at": None,
        "issues": issues,
        "counts": counts,
        "meta_issue": meta_issue,
    }

    with open(cache_file, "w") as f:
        json.dump(cache_data, f, indent=2)

    print(f"\nCache written to: {cache_file}")
    print(f"  Total issues: {counts['total']}")
    print(f"  Todo: {counts['todo']}")
    print(f"  In Progress: {counts['in_progress']}")
    print(f"  Done: {counts['done']}")
    if meta_issue:
        print(f"  META issue: {meta_issue['identifier']}")


def main():
    parser = argparse.ArgumentParser(
        description="Pre-populate Linear issue cache for agent sessions"
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        required=True,
        help="Project directory containing .linear_project.json",
    )
    parser.add_argument(
        "--ttl",
        type=int,
        default=180,
        help="Cache TTL in seconds (default: 180)",
    )

    args = parser.parse_args()

    if not args.project_dir.exists():
        print(f"ERROR: Project directory does not exist: {args.project_dir}")
        sys.exit(1)

    # Load project state
    project_state = load_project_state(args.project_dir)
    project_id = project_state.get("project_id")

    if not project_id:
        print("ERROR: No project_id found in .linear_project.json")
        sys.exit(1)

    print(f"Project: {project_state.get('project_name', 'Unknown')}")
    print(f"Project ID: {project_id}")

    # Get API key
    api_key = get_linear_api_key()

    # Fetch issues
    issues = fetch_issues(api_key, project_id)

    if not issues:
        print("WARNING: No issues found for this project")

    # Write cache
    write_cache(args.project_dir, project_id, issues)

    print("\nCache is ready! Subsequent agent sessions will use this cache.")
    print("Cache will be refreshed after 3 minutes or after status changes.")


if __name__ == "__main__":
    main()
