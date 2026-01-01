"""
Autonomous Operation Enhancements
=================================

This module provides advanced autonomy features for truly continuous agent operation:
- Intelligent retry with exponential backoff
- Error classification and adaptive behavior
- Health monitoring and heartbeat
- Stale issue detection and recovery
- Session resource awareness
- Watchdog timers
- Graceful degradation
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Callable, Any
import random


class ErrorCategory(Enum):
    """Classification of errors for adaptive retry behavior."""
    TRANSIENT = auto()      # Network issues, temporary failures - retry quickly
    RATE_LIMIT = auto()     # API rate limits - back off significantly
    AUTH = auto()           # Authentication issues - likely fatal
    RESOURCE = auto()       # Resource exhaustion (memory, context) - restart session
    LINEAR_API = auto()     # Linear-specific errors - may need graceful degradation
    PUPPETEER = auto()      # Browser automation errors - may need browser restart
    VALIDATION = auto()     # Command blocked by security - agent should adapt
    UNKNOWN = auto()        # Unclassified - use conservative retry


@dataclass
class RetryConfig:
    """Configuration for retry behavior per error category."""
    max_retries: int = 5
    initial_delay: float = 2.0
    max_delay: float = 300.0  # 5 minutes max
    exponential_base: float = 2.0
    jitter: bool = True  # Add randomness to prevent thundering herd

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt number."""
        delay = min(
            self.initial_delay * (self.exponential_base ** attempt),
            self.max_delay
        )
        if self.jitter:
            delay = delay * (0.5 + random.random())  # 50-150% of calculated delay
        return delay


# Default retry configs per error category
RETRY_CONFIGS = {
    ErrorCategory.TRANSIENT: RetryConfig(max_retries=10, initial_delay=1.0),
    ErrorCategory.RATE_LIMIT: RetryConfig(max_retries=5, initial_delay=30.0, max_delay=600.0),
    ErrorCategory.AUTH: RetryConfig(max_retries=1, initial_delay=0.0),  # Don't retry auth errors
    ErrorCategory.RESOURCE: RetryConfig(max_retries=3, initial_delay=5.0),
    ErrorCategory.LINEAR_API: RetryConfig(max_retries=8, initial_delay=5.0, max_delay=120.0),
    ErrorCategory.PUPPETEER: RetryConfig(max_retries=5, initial_delay=3.0),
    ErrorCategory.VALIDATION: RetryConfig(max_retries=0),  # Never retry - agent must adapt
    ErrorCategory.UNKNOWN: RetryConfig(max_retries=5, initial_delay=5.0),
}


def classify_error(error_text: str) -> ErrorCategory:
    """
    Classify an error based on its message/content.

    Args:
        error_text: The error message or response text

    Returns:
        The classified error category
    """
    error_lower = error_text.lower()

    # Auth errors
    if any(kw in error_lower for kw in ['unauthorized', '401', 'authentication', 'invalid token', 'expired token']):
        return ErrorCategory.AUTH

    # Rate limiting
    if any(kw in error_lower for kw in ['rate limit', '429', 'too many requests', 'throttl']):
        return ErrorCategory.RATE_LIMIT

    # Linear API specific
    if any(kw in error_lower for kw in ['linear', 'mcp__linear', 'graphql']):
        return ErrorCategory.LINEAR_API

    # Puppeteer/browser errors
    if any(kw in error_lower for kw in ['puppeteer', 'browser', 'chrome', 'timeout waiting for', 'navigation']):
        return ErrorCategory.PUPPETEER

    # Resource exhaustion
    if any(kw in error_lower for kw in ['out of memory', 'context', 'max_turns', 'resource']):
        return ErrorCategory.RESOURCE

    # Security/validation blocks
    if any(kw in error_lower for kw in ['blocked', 'not allowed', 'permission denied', 'security']):
        return ErrorCategory.VALIDATION

    # Transient network errors
    if any(kw in error_lower for kw in ['timeout', 'connection', 'network', 'temporary', 'econnreset', '503', '502']):
        return ErrorCategory.TRANSIENT

    return ErrorCategory.UNKNOWN


@dataclass
class SessionHealth:
    """Track health metrics for a session."""
    start_time: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    tool_calls: int = 0
    errors: int = 0
    blocked_commands: int = 0
    issues_worked: list = field(default_factory=list)
    linear_api_failures: int = 0
    puppeteer_failures: int = 0

    def record_activity(self):
        """Record that activity occurred."""
        self.last_activity = datetime.now()
        self.tool_calls += 1

    def record_error(self, category: ErrorCategory):
        """Record an error of the given category."""
        self.errors += 1
        self.last_activity = datetime.now()
        if category == ErrorCategory.LINEAR_API:
            self.linear_api_failures += 1
        elif category == ErrorCategory.PUPPETEER:
            self.puppeteer_failures += 1
        elif category == ErrorCategory.VALIDATION:
            self.blocked_commands += 1

    def is_healthy(self, max_idle_seconds: int = 300) -> bool:
        """Check if the session appears healthy."""
        idle_time = (datetime.now() - self.last_activity).total_seconds()

        # Unhealthy if idle too long
        if idle_time > max_idle_seconds:
            return False

        # Unhealthy if too many errors relative to activity
        if self.tool_calls > 0 and (self.errors / self.tool_calls) > 0.5:
            return False

        return True

    def get_summary(self) -> dict:
        """Get a summary of session health."""
        duration = (datetime.now() - self.start_time).total_seconds()
        return {
            "duration_seconds": duration,
            "tool_calls": self.tool_calls,
            "errors": self.errors,
            "error_rate": self.errors / max(1, self.tool_calls),
            "blocked_commands": self.blocked_commands,
            "linear_failures": self.linear_api_failures,
            "puppeteer_failures": self.puppeteer_failures,
            "issues_worked": self.issues_worked,
            "is_healthy": self.is_healthy(),
        }


@dataclass
class AutonomyState:
    """Global state for autonomous operation across sessions."""
    consecutive_errors: int = 0
    consecutive_successes: int = 0
    total_sessions: int = 0
    total_issues_completed: int = 0
    last_error_category: Optional[ErrorCategory] = None
    degraded_mode: bool = False  # True when operating without Linear
    pause_until: Optional[datetime] = None
    session_history: list = field(default_factory=list)  # Last N session summaries

    # Adaptive thresholds
    error_threshold_for_pause: int = 5
    success_threshold_to_reset: int = 3
    max_session_history: int = 10

    def record_session_result(self, success: bool, health: SessionHealth):
        """Record the result of a completed session."""
        self.total_sessions += 1

        if success:
            self.consecutive_successes += 1
            self.consecutive_errors = 0
            self.degraded_mode = False  # Exit degraded mode on success
        else:
            self.consecutive_errors += 1
            self.consecutive_successes = 0

        # Add to history
        summary = health.get_summary()
        summary["success"] = success
        summary["timestamp"] = datetime.now().isoformat()
        self.session_history.append(summary)

        # Trim history
        if len(self.session_history) > self.max_session_history:
            self.session_history = self.session_history[-self.max_session_history:]

        # Completed issues
        self.total_issues_completed += len(health.issues_worked)

    def should_pause(self) -> tuple[bool, float]:
        """
        Check if we should pause before next session.

        Returns:
            (should_pause, pause_duration_seconds)
        """
        # Check if already paused
        if self.pause_until and datetime.now() < self.pause_until:
            remaining = (self.pause_until - datetime.now()).total_seconds()
            return True, remaining

        # Calculate if we need to pause based on error pattern
        if self.consecutive_errors >= self.error_threshold_for_pause:
            # Exponential backoff: 30s, 60s, 120s, 240s, max 600s
            pause_duration = min(30 * (2 ** (self.consecutive_errors - self.error_threshold_for_pause)), 600)
            self.pause_until = datetime.now() + timedelta(seconds=pause_duration)
            return True, pause_duration

        return False, 0

    def enter_degraded_mode(self, reason: str):
        """Enter degraded mode (e.g., when Linear is unavailable)."""
        self.degraded_mode = True
        print(f"\n⚠️  ENTERING DEGRADED MODE: {reason}")
        print("   Agent will continue with limited functionality.")

    def exit_degraded_mode(self):
        """Exit degraded mode."""
        if self.degraded_mode:
            self.degraded_mode = False
            print("\n✓ Exiting degraded mode - full functionality restored.")

    def get_status(self) -> dict:
        """Get current autonomy status."""
        return {
            "total_sessions": self.total_sessions,
            "total_issues_completed": self.total_issues_completed,
            "consecutive_errors": self.consecutive_errors,
            "consecutive_successes": self.consecutive_successes,
            "degraded_mode": self.degraded_mode,
            "paused": self.pause_until and datetime.now() < self.pause_until,
            "recent_sessions": self.session_history[-3:] if self.session_history else [],
        }


class Watchdog:
    """
    Watchdog timer to detect stuck/hung sessions.

    If no activity is recorded within the timeout period, the watchdog
    triggers recovery actions.
    """

    def __init__(
        self,
        timeout_seconds: int = 300,
        on_timeout: Optional[Callable[[], None]] = None
    ):
        self.timeout_seconds = timeout_seconds
        self.on_timeout = on_timeout
        self.last_pet = time.time()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def pet(self):
        """Reset the watchdog timer (call this on activity)."""
        self.last_pet = time.time()

    async def _monitor(self):
        """Internal monitoring loop."""
        while self._running:
            elapsed = time.time() - self.last_pet
            if elapsed > self.timeout_seconds:
                print(f"\n⚠️  WATCHDOG TIMEOUT: No activity for {elapsed:.0f}s")
                if self.on_timeout:
                    self.on_timeout()
                self.pet()  # Reset after triggering
            await asyncio.sleep(10)  # Check every 10 seconds

    async def start(self):
        """Start the watchdog."""
        self._running = True
        self.pet()
        self._task = asyncio.create_task(self._monitor())

    async def stop(self):
        """Stop the watchdog."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


class StaleIssueDetector:
    """
    Detect and handle stale "In Progress" issues.

    Issues left in "In Progress" by crashed sessions need to be recovered.
    """

    STALE_THRESHOLD_HOURS = 2  # Issues in-progress for longer than this are stale

    @staticmethod
    def is_stale(issue_updated_at: str) -> bool:
        """Check if an issue is stale based on its last update time."""
        try:
            # Parse ISO timestamp
            updated = datetime.fromisoformat(issue_updated_at.replace('Z', '+00:00'))
            now = datetime.now(updated.tzinfo) if updated.tzinfo else datetime.now()
            age = now - updated
            return age > timedelta(hours=StaleIssueDetector.STALE_THRESHOLD_HOURS)
        except (ValueError, TypeError):
            return False  # Can't determine - assume not stale

    @staticmethod
    def get_recovery_prompt(issue_id: str, issue_title: str) -> str:
        """Generate a prompt for recovering a stale issue."""
        return f"""
## STALE ISSUE DETECTED - RECOVERY REQUIRED

Issue `{issue_id}` ("{issue_title}") has been "In Progress" for over {StaleIssueDetector.STALE_THRESHOLD_HOURS} hours.
This indicates a previous session may have crashed or been interrupted.

**Your first priority:**
1. Check the issue comments for any partial work notes
2. Review git log to see if any commits were made for this issue
3. Assess the current state of the implementation
4. Either:
   a. Complete the remaining work and mark Done, OR
   b. Add a detailed comment about what's missing and keep as In Progress

Do NOT start new issues until this stale issue is resolved.
"""


async def retry_with_backoff(
    func: Callable,
    *args,
    error_category: ErrorCategory = ErrorCategory.UNKNOWN,
    on_retry: Optional[Callable[[int, float], None]] = None,
    **kwargs
) -> Any:
    """
    Execute a function with intelligent retry and exponential backoff.

    Args:
        func: Async function to execute
        error_category: Category of expected errors (for retry config)
        on_retry: Optional callback(attempt, delay) called before each retry
        *args, **kwargs: Arguments to pass to func

    Returns:
        Result of func

    Raises:
        The last exception if all retries exhausted
    """
    config = RETRY_CONFIGS.get(error_category, RETRY_CONFIGS[ErrorCategory.UNKNOWN])
    last_exception = None

    for attempt in range(config.max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e

            # Reclassify error based on actual exception
            actual_category = classify_error(str(e))
            actual_config = RETRY_CONFIGS.get(actual_category, config)

            if attempt >= actual_config.max_retries:
                break

            delay = actual_config.get_delay(attempt)

            if on_retry:
                on_retry(attempt + 1, delay)

            print(f"   Retry {attempt + 1}/{actual_config.max_retries} in {delay:.1f}s...")
            await asyncio.sleep(delay)

    raise last_exception


def save_autonomy_state(project_dir: Path, state: AutonomyState):
    """Save autonomy state to disk for persistence across restarts."""
    state_file = project_dir / ".autonomy_state.json"

    data = {
        "consecutive_errors": state.consecutive_errors,
        "consecutive_successes": state.consecutive_successes,
        "total_sessions": state.total_sessions,
        "total_issues_completed": state.total_issues_completed,
        "degraded_mode": state.degraded_mode,
        "pause_until": state.pause_until.isoformat() if state.pause_until else None,
        "session_history": state.session_history,
        "last_updated": datetime.now().isoformat(),
    }

    with open(state_file, "w") as f:
        json.dump(data, f, indent=2)


def load_autonomy_state(project_dir: Path) -> AutonomyState:
    """Load autonomy state from disk."""
    state_file = project_dir / ".autonomy_state.json"
    state = AutonomyState()

    if not state_file.exists():
        return state

    try:
        with open(state_file, "r") as f:
            data = json.load(f)

        state.consecutive_errors = data.get("consecutive_errors", 0)
        state.consecutive_successes = data.get("consecutive_successes", 0)
        state.total_sessions = data.get("total_sessions", 0)
        state.total_issues_completed = data.get("total_issues_completed", 0)
        state.degraded_mode = data.get("degraded_mode", False)
        state.session_history = data.get("session_history", [])

        if data.get("pause_until"):
            state.pause_until = datetime.fromisoformat(data["pause_until"])
            # Clear if pause has expired
            if datetime.now() > state.pause_until:
                state.pause_until = None

    except (json.JSONDecodeError, IOError):
        pass

    return state


def print_autonomy_status(state: AutonomyState):
    """Print a formatted autonomy status dashboard."""
    status = state.get_status()

    print("\n" + "=" * 70)
    print("  AUTONOMY STATUS DASHBOARD")
    print("=" * 70)
    print(f"  Total Sessions:        {status['total_sessions']}")
    print(f"  Issues Completed:      {status['total_issues_completed']}")
    print(f"  Consecutive Successes: {status['consecutive_successes']}")
    print(f"  Consecutive Errors:    {status['consecutive_errors']}")
    print(f"  Mode:                  {'⚠️ DEGRADED' if status['degraded_mode'] else '✓ Normal'}")
    print(f"  Status:                {'⏸ PAUSED' if status['paused'] else '▶ Running'}")
    print("-" * 70)
