"""
Agent Session Logic
===================

Core agent interaction functions for running autonomous coding sessions.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from claude_code_sdk import ClaudeSDKClient

from client import create_client
from progress import (
    print_session_header,
    print_progress_summary,
    print_session_summary,
    is_linear_initialized,
    validate_linear_state,
    print_validation_result,
    check_completion_status,
)
from prompts import get_initializer_prompt, get_coding_prompt, get_add_features_prompt, get_add_spec_prompt, copy_spec_to_project


# Configuration
AUTO_CONTINUE_DELAY_SECONDS = 3


async def run_agent_session(
    client: ClaudeSDKClient,
    message: str,
    project_dir: Path,
) -> tuple[str, str]:
    """
    Run a single agent session using Claude Agent SDK.

    Args:
        client: Claude SDK client
        message: The prompt to send
        project_dir: Project directory path

    Returns:
        (status, response_text) where status is:
        - "continue" if agent should continue working
        - "error" if an error occurred
    """
    print("Sending prompt to Claude Agent SDK...\n")

    try:
        # Send the query
        await client.query(message)

        # Collect response text and show tool use
        response_text = ""
        async for msg in client.receive_response():
            msg_type = type(msg).__name__

            # Handle AssistantMessage (text and tool use)
            if msg_type == "AssistantMessage" and hasattr(msg, "content"):
                for block in msg.content:
                    block_type = type(block).__name__

                    if block_type == "TextBlock" and hasattr(block, "text"):
                        response_text += block.text
                        print(block.text, end="", flush=True)
                    elif block_type == "ToolUseBlock" and hasattr(block, "name"):
                        print(f"\n[Tool: {block.name}]", flush=True)
                        if hasattr(block, "input"):
                            input_str = str(block.input)
                            if len(input_str) > 200:
                                print(f"   Input: {input_str[:200]}...", flush=True)
                            else:
                                print(f"   Input: {input_str}", flush=True)

            # Handle UserMessage (tool results)
            elif msg_type == "UserMessage" and hasattr(msg, "content"):
                for block in msg.content:
                    block_type = type(block).__name__

                    if block_type == "ToolResultBlock":
                        result_content = getattr(block, "content", "")
                        is_error = getattr(block, "is_error", False)

                        # Check if command was blocked by security hook
                        if "blocked" in str(result_content).lower():
                            print(f"   [BLOCKED] {result_content}", flush=True)
                        elif is_error:
                            # Show errors (truncated)
                            error_str = str(result_content)[:500]
                            print(f"   [Error] {error_str}", flush=True)
                        else:
                            # Tool succeeded - just show brief confirmation
                            print("   [Done]", flush=True)

        print("\n" + "-" * 70 + "\n")
        return "continue", response_text

    except Exception as e:
        print(f"Error during agent session: {e}")
        return "error", str(e)


async def run_autonomous_agent(
    project_dir: Path,
    model: str,
    max_iterations: Optional[int] = None,
    add_features: bool = False,
    add_spec: Optional[str] = None,
    no_auto_stop: bool = False,
    skip_validation: bool = False,
) -> None:
    """
    Run the autonomous agent loop.

    Args:
        project_dir: Directory for the project
        model: Claude model to use
        max_iterations: Maximum number of iterations (None for unlimited)
        add_features: If True, run add-features mode to create issues from updated spec
        add_spec: If provided, create issues from this spec file
        no_auto_stop: If True, don't auto-stop when all issues are complete
        skip_validation: If True, skip Linear state validation on startup
    """
    print("\n" + "=" * 70)
    if add_spec:
        print("  ADD SPEC MODE")
    elif add_features:
        print("  ADD FEATURES MODE")
    else:
        print("  AUTONOMOUS CODING AGENT DEMO")
    print("=" * 70)
    print(f"\nProject directory: {project_dir}")
    print(f"Model: {model}")
    if max_iterations:
        print(f"Max iterations: {max_iterations}")
    else:
        print("Max iterations: Unlimited (will run until completion)")
    print()

    # Create project directory
    project_dir.mkdir(parents=True, exist_ok=True)

    # Check if this is a fresh start or continuation
    # We use .linear_project.json as the marker for initialization
    is_first_run = not is_linear_initialized(project_dir)

    # Handle add-spec mode
    if add_spec:
        if is_first_run:
            print("ERROR: Cannot add spec - project not initialized yet.")
            print("Run without --add-spec first to initialize the project.")
            return
        # Verify spec file exists
        spec_path = project_dir / add_spec
        if not spec_path.exists():
            print(f"ERROR: Spec file not found: {spec_path}")
            return
        print(f"Add Spec Mode - creating issues from {add_spec}")
        print()
        print("=" * 70)
        print("  The agent will:")
        print(f"  1. Read {add_spec}")
        print("  2. Audit existing Linear issues")
        print("  3. Create new issues from the spec")
        print("=" * 70)
        print()
        print_progress_summary(project_dir)
    # Handle add-features mode
    elif add_features:
        if is_first_run:
            print("ERROR: Cannot add features - project not initialized yet.")
            print("Run without --add-features first to initialize the project.")
            return
        print("Add Features Mode - will create issues from updated spec")
        print()
        print("=" * 70)
        print("  The agent will:")
        print("  1. Read the updated app_spec.txt")
        print("  2. Compare against existing Linear issues")
        print("  3. Create new issues for new features only")
        print("=" * 70)
        print()
        print_progress_summary(project_dir)
    elif is_first_run:
        print("Fresh start - will use initializer agent")
        print()
        print("=" * 70)
        print("  NOTE: First session takes 10-20+ minutes!")
        print("  The agent is creating Linear issues and setting up the project.")
        print("  This may appear to hang - it's working. Watch for [Tool: ...] output.")
        print("=" * 70)
        print()
        # Copy the app spec into the project directory for the agent to read
        copy_spec_to_project(project_dir)
    else:
        print("Continuing existing project (Linear initialized)")
        print_progress_summary(project_dir)

    # Validate Linear state on startup (unless skipped or first run)
    if not is_first_run and not skip_validation:
        is_valid, warnings = validate_linear_state(project_dir)
        print_validation_result(is_valid, warnings)
        if not is_valid:
            print("\n  Warning: Linear state validation found issues.")
            print("  The agent will attempt to continue, but you may want to check Linear.")
            print("  Use --skip-validation to suppress this check.\n")

    # Main loop
    iteration = 0

    while True:
        iteration += 1

        # Check max iterations
        if max_iterations and iteration > max_iterations:
            print(f"\nReached max iterations ({max_iterations})")
            print("To continue, run the script again without --max-iterations")
            break

        # Print session header
        print_session_header(iteration, is_first_run)

        # Track session start time
        session_start = datetime.now()

        # Create client (fresh context)
        client = create_client(project_dir, model)

        # Choose prompt based on session type
        if add_spec:
            prompt = get_add_spec_prompt(add_spec)
            add_spec = None  # Only use add-spec prompt for first iteration
        elif add_features:
            prompt = get_add_features_prompt()
            add_features = False  # Only use add-features prompt for first iteration
        elif is_first_run:
            prompt = get_initializer_prompt()
            is_first_run = False  # Only use initializer once
        else:
            prompt = get_coding_prompt()

        # Run session with async context manager
        async with client:
            status, response = await run_agent_session(client, prompt, project_dir)

        # Print session summary
        print_session_summary(
            session_num=iteration,
            start_time=session_start,
            response_text=response,
            status=status,
            project_dir=project_dir,
        )

        # Check for completion (auto-stop when all issues done)
        if not no_auto_stop and status == "continue":
            is_complete, completion_msg = check_completion_status(project_dir)
            print(f"\n  {completion_msg}")
            if is_complete:
                print("\n" + "=" * 70)
                print("  PROJECT COMPLETE!")
                print("=" * 70)
                print("\n  All issues have been marked as Done in Linear.")
                print("  The agent is stopping automatically.")
                print("  Use --no-auto-stop to continue running after completion.")
                break

        # Handle status
        if status == "continue":
            print(f"\nAgent will auto-continue in {AUTO_CONTINUE_DELAY_SECONDS}s...")
            print_progress_summary(project_dir)
            await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)

        elif status == "error":
            print("\nSession encountered an error")
            print("Will retry with a fresh session...")
            await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)

        # Small delay between sessions
        if max_iterations is None or iteration < max_iterations:
            print("\nPreparing next session...\n")
            await asyncio.sleep(1)

    # Final summary
    print("\n" + "=" * 70)
    print("  SESSION COMPLETE")
    print("=" * 70)
    print(f"\nProject directory: {project_dir}")
    print_progress_summary(project_dir)

    # Print instructions for running the generated application
    print("\n" + "-" * 70)
    print("  TO RUN THE GENERATED APPLICATION:")
    print("-" * 70)
    print(f"\n  cd {project_dir.resolve()}")
    print("  ./init.sh           # Run the setup script")
    print("  # Or manually:")
    print("  npm install && npm run dev")
    print("\n  Then open http://localhost:3000 (or check init.sh for the URL)")
    print("-" * 70)

    print("\nDone!")
