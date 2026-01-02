"""
Security Hooks for Autonomous Coding Agent
==========================================

Pre-tool-use hooks that validate bash commands for security.
Uses an allowlist approach - only explicitly permitted commands can run.
"""

import os
import shlex


# Allowed commands for development tasks
# Minimal set needed for the autonomous coding demo
ALLOWED_COMMANDS = {
    # File inspection
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "grep",
    # File operations (agent uses SDK tools for most file ops, but cp/mkdir needed occasionally)
    "cp",
    "mkdir",
    "chmod",  # For making scripts executable; validated separately
    # Directory
    "pwd",
    # Node.js development
    "npm",
    "pnpm",
    "node",
    "npx",
    # Version control
    "git",
    # Process management (Unix)
    "ps",
    "lsof",
    "sleep",
    "pkill",  # For killing dev servers; validated separately
    # Process management (Windows)
    "taskkill",  # Windows equivalent of pkill; validated separately
    "netstat",  # For checking port usage on Windows
    "findstr",  # Windows equivalent of grep
    # Shell builtins (needed for || true patterns and output)
    "true",
    "false",
    "echo",
    # Script execution
    "init.sh",  # Init scripts; validated separately
}

# Commands that need additional validation even when in the allowlist
COMMANDS_NEEDING_EXTRA_VALIDATION = {"pkill", "taskkill", "chmod", "init.sh"}


def split_command_segments(command_string: str) -> list[str]:
    """
    Split a compound command into individual command segments.

    Handles command chaining (&&, ||, ;) but not pipes (those are single commands).

    Args:
        command_string: The full shell command

    Returns:
        List of individual command segments
    """
    import re

    # Split on && and || while preserving the ability to handle each segment
    # This regex splits on && or || that aren't inside quotes
    segments = re.split(r"\s*(?:&&|\|\|)\s*", command_string)

    # Further split on semicolons
    result = []
    for segment in segments:
        sub_segments = re.split(r'(?<!["\'])\s*;\s*(?!["\'])', segment)
        for sub in sub_segments:
            sub = sub.strip()
            if sub:
                result.append(sub)

    return result


def extract_commands(command_string: str) -> list[str]:
    """
    Extract command names from a shell command string.

    Handles pipes, command chaining (&&, ||, ;), and subshells.
    Returns the base command names (without paths).

    Args:
        command_string: The full shell command

    Returns:
        List of command names found in the string
    """
    commands = []

    # shlex doesn't treat ; as a separator, so we need to pre-process
    import re

    # Split on semicolons that aren't inside quotes (simple heuristic)
    # This handles common cases like "echo hello; ls"
    segments = re.split(r'(?<!["\'])\s*;\s*(?!["\'])', command_string)

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        try:
            tokens = shlex.split(segment)
        except ValueError:
            # Malformed command (unclosed quotes, etc.)
            # Return empty to trigger block (fail-safe)
            return []

        if not tokens:
            continue

        # Track when we expect a command vs arguments
        expect_command = True

        for token in tokens:
            # Shell operators indicate a new command follows
            if token in ("|", "||", "&&", "&"):
                expect_command = True
                continue

            # Skip shell keywords that precede commands
            if token in (
                "if",
                "then",
                "else",
                "elif",
                "fi",
                "for",
                "while",
                "until",
                "do",
                "done",
                "case",
                "esac",
                "in",
                "!",
                "{",
                "}",
            ):
                continue

            # Skip flags/options
            if token.startswith("-"):
                continue

            # Skip variable assignments (VAR=value)
            if "=" in token and not token.startswith("="):
                continue

            if expect_command:
                # Extract the base command name (handle paths like /usr/bin/python)
                cmd = os.path.basename(token)
                commands.append(cmd)
                expect_command = False

    return commands


def validate_pkill_command(command_string: str) -> tuple[bool, str]:
    """
    Validate pkill commands - only allow killing dev-related processes.

    Uses shlex to parse the command, avoiding regex bypass vulnerabilities.

    Returns:
        Tuple of (is_allowed, reason_if_blocked)
    """
    # Allowed process names for pkill (without -f flag)
    allowed_process_names = {
        "node",
        "npm",
        "npx",
        "pnpm",
        "vite",
        "next",
        "tsx",
        "turbo",
    }

    # When using -f flag, these base patterns are TOO BROAD and need more specificity
    # "pkill -f node" kills everything with "node" in command line including puppeteer
    dangerous_if_alone = {"node", "npm", "npx", "pnpm"}

    # Safe patterns that are specific enough for -f flag
    # These indicate dev server processes that are safe to kill
    safe_patterns = {
        "next dev", "next start", "next build",
        "vite", "vite dev", "vite build",
        "tsx watch", "tsx",
        "turbo dev", "turbo run",
        "npm run dev", "npm run start", "npm run build",
        "pnpm dev", "pnpm run dev",
        "npx next", "npx vite", "npx tsx",
    }

    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse pkill command"

    if not tokens:
        return False, "Empty pkill command"

    # Check if -f flag is present
    has_f_flag = "-f" in tokens

    # Separate flags from arguments
    args = []
    for token in tokens[1:]:
        if not token.startswith("-"):
            args.append(token)

    if not args:
        return False, "pkill requires a process name"

    # The target is typically the last non-flag argument
    target = args[-1]
    target_lower = target.lower()

    # For -f flag, validate pattern specificity
    if has_f_flag:
        # Check if it's a known safe pattern
        if target_lower in safe_patterns:
            return True, ""

        # Check for patterns with path components (e.g., "node.*apps/api", "apps/web")
        # These are specific enough to be safe
        if "/" in target or "apps/" in target or "packages/" in target:
            return True, ""

        # Check if it contains a safe keyword that makes it specific
        safe_keywords = {"dev", "watch", "start", "build", "serve", "server", "api", "web"}
        if any(kw in target_lower for kw in safe_keywords):
            return True, ""

        # Extract first word for validation
        first_word = target.split()[0] if " " in target else target

        # Block overly broad patterns
        if first_word in dangerous_if_alone and " " not in target and "/" not in target:
            return False, (
                f"pkill -f '{target}' is too broad and may kill critical processes. "
                f"Use a more specific pattern like 'pkill -f \"next dev\"' or 'pkill -f \"tsx watch\"'"
            )

        # Allow if first word is a known dev tool
        if first_word in allowed_process_names:
            return True, ""

    else:
        # Without -f, just check the process name
        if target in allowed_process_names:
            return True, ""

    return False, f"pkill only allowed for dev processes: {allowed_process_names}"


def validate_taskkill_command(command_string: str) -> tuple[bool, str]:
    """
    Validate taskkill commands (Windows) - only allow killing dev-related processes.

    Returns:
        Tuple of (is_allowed, reason_if_blocked)
    """
    # Allowed image names for taskkill /IM
    allowed_image_names = {
        "node.exe",
        "npm.exe",
        "npx.exe",
    }

    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse taskkill command"

    if not tokens:
        return False, "Empty taskkill command"

    # taskkill typically uses /F (force) and /IM (image name) or /PID
    # We only allow /IM with specific process names
    has_im_flag = False
    image_name = None

    i = 0
    while i < len(tokens):
        token = tokens[i].upper()

        if token == "/IM" and i + 1 < len(tokens):
            has_im_flag = True
            image_name = tokens[i + 1].lower()
            i += 2
            continue

        # Also handle /IM:name format
        if token.startswith("/IM:"):
            has_im_flag = True
            image_name = tokens[i][4:].lower()
            i += 1
            continue

        i += 1

    if not has_im_flag or not image_name:
        return False, "taskkill only allowed with /IM flag and image name"

    if image_name not in allowed_image_names:
        return False, f"taskkill only allowed for dev processes: {allowed_image_names}"

    return True, ""


def validate_chmod_command(command_string: str) -> tuple[bool, str]:
    """
    Validate chmod commands - only allow making files executable with +x.

    Returns:
        Tuple of (is_allowed, reason_if_blocked)
    """
    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse chmod command"

    if not tokens or tokens[0] != "chmod":
        return False, "Not a chmod command"

    # Look for the mode argument
    # Valid modes: +x, u+x, a+x, etc. (anything ending with +x for execute permission)
    mode = None
    files = []

    for token in tokens[1:]:
        if token.startswith("-"):
            # Skip flags like -R (we don't allow recursive chmod anyway)
            return False, "chmod flags are not allowed"
        elif mode is None:
            mode = token
        else:
            files.append(token)

    if mode is None:
        return False, "chmod requires a mode"

    if not files:
        return False, "chmod requires at least one file"

    # Only allow +x variants (making files executable)
    # This matches: +x, u+x, g+x, o+x, a+x, ug+x, etc.
    import re

    if not re.match(r"^[ugoa]*\+x$", mode):
        return False, f"chmod only allowed with +x mode, got: {mode}"

    return True, ""


def validate_init_script(command_string: str) -> tuple[bool, str]:
    """
    Validate init.sh script execution - only allow ./init.sh.

    Returns:
        Tuple of (is_allowed, reason_if_blocked)
    """
    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse init script command"

    if not tokens:
        return False, "Empty command"

    # The command should be exactly ./init.sh (possibly with arguments)
    script = tokens[0]

    # Allow ./init.sh or paths ending in /init.sh
    if script == "./init.sh" or script.endswith("/init.sh"):
        return True, ""

    return False, f"Only ./init.sh is allowed, got: {script}"


def get_command_for_validation(cmd: str, segments: list[str]) -> str:
    """
    Find the specific command segment that contains the given command.

    Args:
        cmd: The command name to find
        segments: List of command segments

    Returns:
        The segment containing the command, or empty string if not found
    """
    for segment in segments:
        segment_commands = extract_commands(segment)
        if cmd in segment_commands:
            return segment
    return ""


async def bash_security_hook(input_data, tool_use_id=None, context=None):
    """
    Pre-tool-use hook that validates bash commands using an allowlist.

    Only commands in ALLOWED_COMMANDS are permitted.

    Args:
        input_data: Dict containing tool_name and tool_input
        tool_use_id: Optional tool use ID
        context: Optional context

    Returns:
        Empty dict to allow, or {"decision": "block", "reason": "..."} to block
    """
    if input_data.get("tool_name") != "Bash":
        return {}

    command = input_data.get("tool_input", {}).get("command", "")
    if not command:
        return {}

    # Extract all commands from the command string
    commands = extract_commands(command)

    if not commands:
        # Could not parse - fail safe by blocking
        return {
            "decision": "block",
            "reason": f"Could not parse command for security validation: {command}",
        }

    # Split into segments for per-command validation
    segments = split_command_segments(command)

    # Check each command against the allowlist
    for cmd in commands:
        if cmd not in ALLOWED_COMMANDS:
            return {
                "decision": "block",
                "reason": f"Command '{cmd}' is not in the allowed commands list",
            }

        # Additional validation for sensitive commands
        if cmd in COMMANDS_NEEDING_EXTRA_VALIDATION:
            # Find the specific segment containing this command
            cmd_segment = get_command_for_validation(cmd, segments)
            if not cmd_segment:
                cmd_segment = command  # Fallback to full command

            if cmd == "pkill":
                allowed, reason = validate_pkill_command(cmd_segment)
                if not allowed:
                    return {"decision": "block", "reason": reason}
            elif cmd == "taskkill":
                allowed, reason = validate_taskkill_command(cmd_segment)
                if not allowed:
                    return {"decision": "block", "reason": reason}
            elif cmd == "chmod":
                allowed, reason = validate_chmod_command(cmd_segment)
                if not allowed:
                    return {"decision": "block", "reason": reason}
            elif cmd == "init.sh":
                allowed, reason = validate_init_script(cmd_segment)
                if not allowed:
                    return {"decision": "block", "reason": reason}

    return {}
