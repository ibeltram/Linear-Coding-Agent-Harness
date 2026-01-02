"""
Linear Configuration
====================

Configuration constants for Linear integration.
These values are used in prompts and for project state management.
"""

import os

# Environment variables (must be set before running)
LINEAR_API_KEY = os.environ.get("LINEAR_API_KEY")

# Issue count is now dynamic based on spec complexity
# Small spec: 20-40, Medium: 40-80, Large: 80-150+
# This constant is deprecated but kept for backwards compatibility
DEFAULT_ISSUE_COUNT = None  # Dynamic

# Issue status workflow (Linear default states)
STATUS_TODO = "Todo"
STATUS_IN_PROGRESS = "In Progress"
STATUS_DONE = "Done"

# Label categories (map to feature types)
LABEL_FUNCTIONAL = "functional"
LABEL_STYLE = "style"
LABEL_INFRASTRUCTURE = "infrastructure"

# Priority mapping (Linear uses 0-4 where 1=Urgent, 4=Low, 0=No priority)
PRIORITY_URGENT = 1
PRIORITY_HIGH = 2
PRIORITY_MEDIUM = 3
PRIORITY_LOW = 4

# Local marker file to track Linear project initialization
LINEAR_PROJECT_MARKER = ".linear_project.json"

# Issue cache configuration
LINEAR_ISSUE_CACHE_FILE = ".linear_issue_cache.json"
DEFAULT_CACHE_TTL_SECONDS = 180  # 3 minutes

# Meta issue title for project tracking and session handoff
META_ISSUE_TITLE = "[META] Project Progress Tracker"
