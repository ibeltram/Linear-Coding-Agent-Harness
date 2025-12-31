#!/usr/bin/env python3
"""
Autonomous Coding Agent Demo
============================

A minimal harness demonstrating long-running autonomous coding with Claude.
This script implements the two-agent pattern (initializer + coding agent) and
incorporates all the strategies from the long-running agents guide.

Example Usage:
    python autonomous_agent_demo.py --project-dir ./claude_clone_demo
    python autonomous_agent_demo.py --project-dir ./claude_clone_demo --max-iterations 5
"""

import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from agent import run_autonomous_agent


# Configuration
# Using Claude Opus 4.5 as default for best coding and agentic performance
# See: https://www.anthropic.com/news/claude-opus-4-5
DEFAULT_MODEL = "claude-opus-4-5-20251101"


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Autonomous Coding Agent Demo - Long-running agent harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start fresh project
  python autonomous_agent_demo.py --project-dir ./claude_clone

  # Use a specific model
  python autonomous_agent_demo.py --project-dir ./claude_clone --model claude-sonnet-4-5-20250929

  # Limit iterations for testing
  python autonomous_agent_demo.py --project-dir ./claude_clone --max-iterations 5

  # Continue existing project
  python autonomous_agent_demo.py --project-dir ./claude_clone

  # Add new features from updated spec (creates new Linear issues)
  python autonomous_agent_demo.py --project-dir ./claude_clone --add-features

  # Add issues from a specific spec file
  python autonomous_agent_demo.py --project-dir ./claude_clone --add-spec COMPLETE_SPEC.txt

  # Keep running even after all issues are Done
  python autonomous_agent_demo.py --project-dir ./claude_clone --no-auto-stop

  # Skip Linear state validation on startup
  python autonomous_agent_demo.py --project-dir ./claude_clone --skip-validation

Environment Variables:
  CLAUDE_CODE_OAUTH_TOKEN    Claude Code OAuth token (required)
  LINEAR_API_KEY             Linear API key (required)
        """,
    )

    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path("./autonomous_demo_project"),
        help="Directory for the project (default: generations/autonomous_demo_project). Relative paths automatically placed in generations/ directory.",
    )

    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Maximum number of agent iterations (default: unlimited)",
    )

    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Claude model to use (default: {DEFAULT_MODEL})",
    )

    parser.add_argument(
        "--add-features",
        action="store_true",
        help="Add features mode: create new Linear issues from updated app_spec.txt",
    )

    parser.add_argument(
        "--add-spec",
        type=str,
        default=None,
        help="Add issues from a specific spec file (e.g., COMPLETE_SPEC.txt). Creates issues based on spec complexity.",
    )

    parser.add_argument(
        "--no-auto-stop",
        action="store_true",
        help="Don't automatically stop when all issues are marked Done",
    )

    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip Linear state validation on startup",
    )

    return parser.parse_args()


def main() -> None:
    """Main entry point."""
    # Load environment variables from .env file if present
    load_dotenv()

    args = parse_args()

    # Check for Claude Code OAuth token
    if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        print("Error: CLAUDE_CODE_OAUTH_TOKEN environment variable not set")
        print("\nRun 'claude setup-token' after installing the Claude Code CLI.")
        print("\nThen set it:")
        print("  export CLAUDE_CODE_OAUTH_TOKEN='your-token-here'")
        return

    # Check for Linear API key
    if not os.environ.get("LINEAR_API_KEY"):
        print("Error: LINEAR_API_KEY environment variable not set")
        print("\nGet your API key from: https://linear.app/YOUR-TEAM/settings/api")
        print("\nThen set it:")
        print("  export LINEAR_API_KEY='lin_api_xxxxxxxxxxxxx'")
        return

    # Automatically place projects in generations/ directory unless already specified
    project_dir = args.project_dir
    if not str(project_dir).startswith("generations/"):
        # Convert relative paths to be under generations/
        if project_dir.is_absolute():
            # If absolute path, use as-is
            pass
        else:
            # Prepend generations/ to relative paths
            project_dir = Path("generations") / project_dir

    # Run the agent
    try:
        asyncio.run(
            run_autonomous_agent(
                project_dir=project_dir,
                model=args.model,
                max_iterations=args.max_iterations,
                add_features=args.add_features,
                add_spec=args.add_spec,
                no_auto_stop=args.no_auto_stop,
                skip_validation=args.skip_validation,
            )
        )
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        print("To resume, run the same command again")
    except Exception as e:
        print(f"\nFatal error: {e}")
        raise


if __name__ == "__main__":
    main()
