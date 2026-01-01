"""
Agent Session Logic
===================

Core agent interaction functions for running autonomous coding sessions.
Enhanced with comprehensive autonomy features for truly continuous operation.
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
    print_pending_operations_summary,
    get_pending_operation_count,
)
from prompts import get_initializer_prompt, get_coding_prompt, get_add_features_prompt, get_add_spec_prompt, copy_spec_to_project
from autonomy import (
    AutonomyState,
    SessionHealth,
    Watchdog,
    StaleIssueDetector,
    ErrorCategory,
    classify_error,
    load_autonomy_state,
    save_autonomy_state,
    print_autonomy_status,
)


# Configuration
# Set to 0 for true autonomy (no delay between sessions)
# Set higher for ability to manually intervene (e.g., 3 seconds)
AUTO_CONTINUE_DELAY_SECONDS = 0  # CHANGED: Zero delay for true autonomy

# Maximum session duration before forcing clean exit (prevents stuck sessions)
MAX_SESSION_DURATION_SECONDS = 1800  # 30 minutes

# Watchdog timeout - if no activity for this long, assume session is hung
WATCHDOG_TIMEOUT_SECONDS = 300  # 5 minutes


async def run_agent_session(
    client: ClaudeSDKClient,
    message: str,
    project_dir: Path,
    health: SessionHealth,
    watchdog: Optional[Watchdog] = None,
) -> tuple[str, str]:
    """
    Run a single agent session using Claude Agent SDK.

    Args:
        client: Claude SDK client
        message: The prompt to send
        project_dir: Project directory path
        health: Session health tracker
        watchdog: Optional watchdog timer to pet on activity

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

            # Pet the watchdog on any activity
            if watchdog:
                watchdog.pet()
            health.record_activity()

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
                            health.record_error(ErrorCategory.VALIDATION)
                        elif is_error:
                            # Show errors (truncated)
                            error_str = str(result_content)[:500]
                            print(f"   [Error] {error_str}", flush=True)
                            error_cat = classify_error(error_str)
                            health.record_error(error_cat)
                        else:
                            # Tool succeeded - just show brief confirmation
                            print("   [Done]", flush=True)

        print("\n" + "-" * 70 + "\n")
        return "continue", response_text

    except Exception as e:
        error_text = str(e)
        error_category = classify_error(error_text)
        health.record_error(error_category)
        print(f"Error during agent session: {e}")
        print(f"   Error category: {error_category.name}")
        return "error", error_text


def build_enhanced_prompt(
    base_prompt: str,
    autonomy_state: AutonomyState,
    project_dir: Path,
) -> str:
    """
    Enhance the base prompt with autonomy-aware instructions.

    Args:
        base_prompt: The original prompt (initializer/coding/etc)
        autonomy_state: Current autonomy state
        project_dir: Project directory

    Returns:
        Enhanced prompt with additional context and instructions
    """
    enhancements = []

    # Add context about session history
    if autonomy_state.total_sessions > 0:
        enhancements.append(f"""
## AUTONOMY CONTEXT
This is session #{autonomy_state.total_sessions + 1} of the autonomous agent.
- Total issues completed across all sessions: {autonomy_state.total_issues_completed}
- Consecutive successful sessions: {autonomy_state.consecutive_successes}
- Recent error pattern: {autonomy_state.consecutive_errors} consecutive errors
""")

    # Add pending operations context
    pending_count = get_pending_operation_count(project_dir)
    if pending_count > 0:
        enhancements.append(f"""
## PENDING LINEAR OPERATIONS
There are {pending_count} pending Linear operations from previous sessions.
Check `.linear_pending.json` and try to process these first if Linear is available.
If Linear is still unavailable, continue with code work and these will be retried later.
""")

    # Add degraded mode instructions
    if autonomy_state.degraded_mode:
        enhancements.append("""
## ⚠️ DEGRADED MODE ACTIVE
Linear API may be unavailable. Adapt your workflow:
1. Try Linear operations, but if they fail, continue with local work
2. Keep detailed notes in git commits about what Linear updates are needed
3. Focus on code implementation that doesn't require Linear status updates
4. Create a .linear_pending.json file to track operations that need to be retried
""")

    # Add self-healing instructions
    enhancements.append("""
## SELF-HEALING BEHAVIORS

If you encounter errors, adapt your approach:

**Linear API Errors:**
- Retry 2-3 times with brief pauses
- If still failing, note the intended operation and continue with code work
- Update status later when Linear becomes available

**Puppeteer/Browser Errors:**
- If navigation fails, check if the dev server is running
- Kill and restart the dev server if needed
- If browser is unresponsive, the session will restart automatically

**Blocked Commands:**
- If a bash command is blocked, find an alternative approach
- Use the allowed commands listed (ls, cat, npm, git, etc.)
- For file operations, prefer using Write/Edit/Read tools

**Context Running Low:**
- If you notice you've done many operations, start wrapping up
- Commit your work, update META issue, and end cleanly
- It's better to end early than to get cut off mid-operation

**Port Conflicts:**
- Use `pkill -f "next dev"` or `pkill -f "vite"` to kill dev servers
- NEVER use `pkill -f node` (kills critical processes)
- If port still in use, check with `lsof -i :3000`
""")

    # Combine
    if enhancements:
        enhanced = base_prompt + "\n\n" + "\n".join(enhancements)
        return enhanced

    return base_prompt


async def run_autonomous_agent(
    project_dir: Path,
    model: str,
    max_iterations: Optional[int] = None,
    add_features: bool = False,
    add_spec: Optional[str] = None,
    no_auto_stop: bool = False,
    skip_validation: bool = False,
    continuous_mode: bool = True,  # NEW: Enable truly continuous operation
) -> None:
    """
    Run the autonomous agent loop with enhanced autonomy features.

    Args:
        project_dir: Directory for the project
        model: Claude model to use
        max_iterations: Maximum number of iterations (None for unlimited)
        add_features: If True, run add-features mode to create issues from updated spec
        add_spec: If provided, create issues from this spec file
        no_auto_stop: If True, don't auto-stop when all issues are complete
        skip_validation: If True, skip Linear state validation on startup
        continuous_mode: If True, run with zero delays and enhanced autonomy
    """
    print("\n" + "=" * 70)
    if add_spec:
        print("  ADD SPEC MODE")
    elif add_features:
        print("  ADD FEATURES MODE")
    else:
        print("  AUTONOMOUS CODING AGENT DEMO")
        if continuous_mode:
            print("  [CONTINUOUS MODE - TRULY AUTONOMOUS]")
    print("=" * 70)
    print(f"\nProject directory: {project_dir}")
    print(f"Model: {model}")
    if max_iterations:
        print(f"Max iterations: {max_iterations}")
    else:
        print("Max iterations: Unlimited (will run until completion)")
    if continuous_mode:
        print("Continuous mode: ENABLED (zero delay between sessions)")
    print()

    # Create project directory
    project_dir.mkdir(parents=True, exist_ok=True)

    # Load or initialize autonomy state
    autonomy_state = load_autonomy_state(project_dir)
    print_autonomy_status(autonomy_state)

    # Check if this is a fresh start or continuation
    is_first_run = not is_linear_initialized(project_dir)

    # Handle add-spec mode
    if add_spec:
        if is_first_run:
            print("ERROR: Cannot add spec - project not initialized yet.")
            print("Run without --add-spec first to initialize the project.")
            return
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

    # Setup watchdog for hung session detection
    watchdog = Watchdog(
        timeout_seconds=WATCHDOG_TIMEOUT_SECONDS,
        on_timeout=lambda: print("\n⚠️  Session appears hung - will restart on next iteration")
    )

    # Main loop
    iteration = 0

    while True:
        iteration += 1

        # Check max iterations
        if max_iterations and iteration > max_iterations:
            print(f"\nReached max iterations ({max_iterations})")
            print("To continue, run the script again without --max-iterations")
            break

        # Check if we should pause (due to error patterns)
        should_pause, pause_duration = autonomy_state.should_pause()
        if should_pause:
            print(f"\n⏸  ADAPTIVE PAUSE: Waiting {pause_duration:.0f}s due to error pattern...")
            print("   This helps prevent rapid failure loops.")
            await asyncio.sleep(pause_duration)

        # Print session header
        print_session_header(iteration, is_first_run)

        # Track session health
        session_health = SessionHealth()
        session_start = datetime.now()

        # Start watchdog
        await watchdog.start()

        try:
            # Create client (fresh context)
            client = create_client(project_dir, model)

            # Choose base prompt based on session type
            if add_spec:
                base_prompt = get_add_spec_prompt(add_spec)
                add_spec = None  # Only use add-spec prompt for first iteration
            elif add_features:
                base_prompt = get_add_features_prompt()
                add_features = False  # Only use add-features prompt for first iteration
            elif is_first_run:
                base_prompt = get_initializer_prompt()
                is_first_run = False  # Only use initializer once
            else:
                base_prompt = get_coding_prompt()

            # Enhance prompt with autonomy context
            enhanced_prompt = build_enhanced_prompt(base_prompt, autonomy_state, project_dir)

            # Run session with async context manager and timeout
            async with client:
                try:
                    status, response = await asyncio.wait_for(
                        run_agent_session(client, enhanced_prompt, project_dir, session_health, watchdog),
                        timeout=MAX_SESSION_DURATION_SECONDS
                    )
                except asyncio.TimeoutError:
                    print(f"\n⚠️  Session timeout after {MAX_SESSION_DURATION_SECONDS}s")
                    print("   Forcing clean restart...")
                    status = "timeout"
                    response = "Session exceeded maximum duration"

        except Exception as e:
            print(f"\n❌ Session creation error: {e}")
            status = "error"
            response = str(e)
            error_cat = classify_error(response)
            session_health.record_error(error_cat)

            # Check for specific error patterns
            if error_cat == ErrorCategory.AUTH:
                print("\n🚫 Authentication error - cannot continue")
                print("   Please check your CLAUDE_CODE_OAUTH_TOKEN and LINEAR_API_KEY")
                break
            elif error_cat == ErrorCategory.LINEAR_API:
                autonomy_state.enter_degraded_mode("Linear API unavailable")

        finally:
            # Stop watchdog
            await watchdog.stop()

        # Print session summary
        print_session_summary(
            session_num=iteration,
            start_time=session_start,
            response_text=response,
            status=status,
            project_dir=project_dir,
        )

        # Record session result
        session_success = status == "continue"
        autonomy_state.record_session_result(session_success, session_health)
        save_autonomy_state(project_dir, autonomy_state)

        # Print updated autonomy status
        print_autonomy_status(autonomy_state)

        # Check for completion (auto-stop when all issues done)
        if not no_auto_stop and status == "continue":
            is_complete, completion_msg = check_completion_status(project_dir)
            print(f"\n  {completion_msg}")
            if is_complete:
                print("\n" + "=" * 70)
                print("  🎉 PROJECT COMPLETE!")
                print("=" * 70)
                print("\n  All issues have been marked as Done in Linear.")
                print("  The agent is stopping automatically.")
                print("  Use --no-auto-stop to continue running after completion.")
                break

        # Handle status and prepare for next iteration
        if status == "continue":
            if not continuous_mode and AUTO_CONTINUE_DELAY_SECONDS > 0:
                print(f"\nAgent will auto-continue in {AUTO_CONTINUE_DELAY_SECONDS}s...")
                await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)
            else:
                print("\n✓ Continuing immediately (continuous mode)...")
            print_progress_summary(project_dir)
            print_pending_operations_summary(project_dir)

        elif status == "timeout":
            print("\nSession timed out - restarting with fresh context...")
            # Short delay to allow cleanup
            await asyncio.sleep(2)

        elif status == "error":
            print("\n⚠️  Session encountered an error")
            print("   Will retry with a fresh session...")
            # Delay handled by adaptive pause mechanism above
            await asyncio.sleep(1)

        # Minimal delay between sessions for stability
        if max_iterations is None or iteration < max_iterations:
            print("\n─" * 35)
            print("  Preparing next session...")
            print("─" * 35 + "\n")

    # Final summary
    print("\n" + "=" * 70)
    print("  AUTONOMOUS AGENT COMPLETE")
    print("=" * 70)
    print(f"\nProject directory: {project_dir}")
    print_progress_summary(project_dir)
    print_autonomy_status(autonomy_state)

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
