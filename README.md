# Autonomous Coding Agent Demo (Linear-Integrated)

A **truly autonomous** coding agent harness that runs continuously until project completion. Built with the Claude Agent SDK and Linear for project management.

## Key Features

### Core Functionality
- **Linear Integration**: All work is tracked as Linear issues, not local files
- **Real-time Visibility**: Watch agent progress directly in your Linear workspace
- **Session Handoff**: Agents communicate via Linear comments, not text files
- **Multi-Agent Pattern**: Initializer, coding, add-features, and add-spec agents
- **Browser Testing**: Puppeteer MCP for UI verification
- **Claude Opus 4.5**: Uses Claude's most capable model by default

### Autonomy Enhancements (NEW!)
- **Continuous Mode**: Zero delay between sessions (default) - truly autonomous operation
- **Intelligent Retry**: Exponential backoff with error classification
- **Health Monitoring**: Watchdog timers detect and recover from hung sessions
- **Adaptive Behavior**: Auto-pause on repeated errors to prevent rapid failure loops
- **Graceful Degradation**: Continues working when Linear is temporarily unavailable
- **Self-Healing Prompts**: Agents receive recovery instructions for common issues
- **Stale Issue Detection**: Automatically recovers orphaned "In Progress" issues
- **Status Dashboard**: Real-time visibility into autonomy state and session history
- **Pending Operations**: Tracks Linear operations for retry when API recovers

## Prerequisites

### 1. Install Claude Code CLI and Python SDK

```bash
# Install Claude Code CLI (latest version required)
npm install -g @anthropic-ai/claude-code

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Set Up Authentication

You need two authentication tokens:

**Claude Code OAuth Token:**
```bash
# Generate the token using Claude Code CLI
claude setup-token

# Set the environment variable
export CLAUDE_CODE_OAUTH_TOKEN='your-oauth-token-here'
```

**Linear API Key:**
```bash
# Get your API key from: https://linear.app/YOUR-TEAM/settings/api
export LINEAR_API_KEY='lin_api_xxxxxxxxxxxxx'
```

### 3. Verify Installation

```bash
claude --version  # Should be latest version
pip show claude-code-sdk  # Check SDK is installed
```

## Quick Start

```bash
python autonomous_agent_demo.py --project-dir ./my_project
```

For testing with limited iterations:
```bash
python autonomous_agent_demo.py --project-dir ./my_project --max-iterations 3
```

To add new features from an updated spec (after initial setup is complete):
```bash
# 1. Edit the app_spec.txt in your project directory with new features
# 2. Run with --add-features flag
python autonomous_agent_demo.py --project-dir ./my_project --add-features
```

To add 50 issues from a separate spec file:
```bash
# 1. Create a new spec file in your project directory (e.g., COMPLETE_SPEC.txt)
# 2. Run with --add-spec flag
python autonomous_agent_demo.py --project-dir ./my_project --add-spec COMPLETE_SPEC.txt
```

## How It Works

### Linear-Centric Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                    LINEAR-INTEGRATED WORKFLOW               │
├─────────────────────────────────────────────────────────────┤
│  app_spec.txt ──► Initializer Agent ──► Linear Issues (50) │
│                                              │               │
│                    ┌─────────────────────────▼──────────┐   │
│                    │        LINEAR WORKSPACE            │   │
│                    │  ┌────────────────────────────┐    │   │
│                    │  │ Issue: Auth - Login flow   │    │   │
│                    │  │ Status: Todo → In Progress │    │   │
│                    │  │ Comments: [session notes]  │    │   │
│                    │  └────────────────────────────┘    │   │
│                    └────────────────────────────────────┘   │
│                                              │               │
│                    Coding Agent queries Linear              │
│                    ├── Search for Todo issues               │
│                    ├── Update status to In Progress         │
│                    ├── Implement & test with Puppeteer      │
│                    ├── Add comment with implementation notes│
│                    └── Update status to Done                │
└─────────────────────────────────────────────────────────────┘
```

### Multi-Agent Pattern

1. **Initializer Agent (Session 1):**
   - Reads `app_spec.txt`
   - Lists teams and creates a new Linear project
   - Creates 50 Linear issues with detailed test steps
   - Creates a META issue for session tracking
   - Sets up project structure, `init.sh`, and git

2. **Coding Agent (Sessions 2+):**
   - Queries Linear for highest-priority Todo issue
   - Runs verification tests on previously completed features
   - Claims issue (status → In Progress)
   - Implements the feature
   - Tests via Puppeteer browser automation
   - Adds implementation comment to issue
   - Marks complete (status → Done)
   - Updates META issue with session summary

3. **Add Features Agent (On-demand via `--add-features`):**
   - Reads updated `app_spec.txt` with new sections
   - Audits existing Linear issues
   - Creates new issues ONLY for features not yet tracked
   - Updates META issue with feature addition summary
   - Continues with coding if time permits

4. **Add Spec Agent (On-demand via `--add-spec FILE`):**
   - Reads a specific spec file (e.g., `COMPLETE_SPEC.txt`)
   - Audits existing Linear issues to avoid duplicates
   - Creates 50 new issues from the spec file
   - Updates META issue with spec addition summary
   - Tracks which spec file generated which batch of issues

### Session Handoff via Linear

Instead of local text files, agents communicate through:
- **Issue Comments**: Implementation details, blockers, context
- **META Issue**: Session summaries and handoff notes
- **Issue Status**: Todo / In Progress / Done workflow

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude Code OAuth token (from `claude setup-token`) | Yes |
| `LINEAR_API_KEY` | Linear API key for MCP access | Yes |

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--project-dir` | Directory for the project | `./autonomous_demo_project` |
| `--max-iterations` | Max agent iterations | Unlimited |
| `--model` | Claude model to use | `claude-opus-4-5-20251101` |
| `--add-features` | Add new features from updated spec | False |
| `--add-spec FILE` | Create 50 issues from a specific spec file | None |
| `--no-auto-stop` | Keep running even after all issues are Done | False |
| `--skip-validation` | Skip Linear state validation on startup | False |
| `--no-continuous` | Disable continuous mode (adds delays for manual intervention) | False |

## Project Structure

```
linear-agent-harness/
├── autonomous_agent_demo.py  # Main entry point
├── agent.py                  # Agent session logic (enhanced with autonomy features)
├── autonomy.py               # NEW: Autonomy engine (retry, health, watchdog)
├── client.py                 # Claude SDK + MCP client configuration
├── security.py               # Bash command allowlist and validation
├── progress.py               # Progress tracking + pending operations
├── prompts.py                # Prompt loading utilities
├── linear_config.py          # Linear configuration constants
├── prompts/
│   ├── app_spec.txt          # Application specification
│   ├── initializer_prompt.md # First session prompt (creates Linear issues)
│   ├── coding_prompt.md      # Continuation session prompt (with self-healing)
│   ├── add_features_prompt.md # Add features prompt
│   └── add_spec_prompt.md    # Add spec prompt
└── requirements.txt          # Python dependencies
```

## Generated Project Structure

After running, your project directory will contain:

```
my_project/
├── .linear_project.json      # Linear project state (marker file)
├── .autonomy_state.json      # NEW: Autonomy state (session history, error counts)
├── .linear_pending.json      # NEW: Pending Linear operations (for degraded mode)
├── app_spec.txt              # Copied specification
├── init.sh                   # Environment setup script
├── .claude_settings.json     # Security settings
└── [application files]       # Generated application code
```

## MCP Servers Used

| Server | Transport | Purpose |
|--------|-----------|---------|
| **Linear** | HTTP (Streamable HTTP) | Project management - issues, status, comments |
| **Puppeteer** | stdio | Browser automation for UI testing |

## Security Model

This demo uses defense-in-depth security (see `security.py` and `client.py`):

1. **OS-level Sandbox:** Bash commands run in an isolated environment
2. **Filesystem Restrictions:** File operations restricted to project directory
3. **Bash Allowlist:** Only specific commands permitted (npm, node, git, etc.)
4. **MCP Permissions:** Tools explicitly allowed in security settings

## Linear Setup

Before running, ensure you have:

1. A Linear workspace with at least one team
2. An API key with read/write permissions (from Settings > API)
3. The agent will automatically detect your team and create a project

The initializer agent will create:
- A new Linear project named after your app
- 50 feature issues based on `app_spec.txt`
- 1 META issue for session tracking and handoff

All subsequent coding agents will work from this Linear project.

## Customization

### Changing the Application

Edit `prompts/app_spec.txt` to specify a different application to build.

### Adjusting Issue Count

Edit `prompts/initializer_prompt.md` and change "50 issues" to your desired count.

### Modifying Allowed Commands

Edit `security.py` to add or remove commands from `ALLOWED_COMMANDS`.

## Troubleshooting

**"CLAUDE_CODE_OAUTH_TOKEN not set"**
Run `claude setup-token` to generate a token, then export it.

**"LINEAR_API_KEY not set"**
Get your API key from `https://linear.app/YOUR-TEAM/settings/api`

**"Appears to hang on first run"**
Normal behavior. The initializer is creating a Linear project and 50 issues with detailed descriptions. Watch for `[Tool: mcp__linear__create_issue]` output.

**"Command blocked by security hook"**
The agent tried to run a disallowed command. Add it to `ALLOWED_COMMANDS` in `security.py` if needed.

**"MCP server connection failed"**
Verify your `LINEAR_API_KEY` is valid and has appropriate permissions. The Linear MCP server uses HTTP transport at `https://mcp.linear.app/mcp`.

## Viewing Progress

Open your Linear workspace to see:
- The project created by the initializer agent
- All 50 issues organized under the project
- Real-time status changes (Todo → In Progress → Done)
- Implementation comments on each issue
- Session summaries on the META issue

## Autonomy System

The autonomy system enables truly continuous operation without human intervention.

### Continuous Mode (Default)
By default, the agent runs in continuous mode with zero delay between sessions. This maximizes throughput and ensures the agent never stops unless:
- All issues are marked Done (auto-stop)
- Maximum iterations reached
- Fatal authentication error
- User interrupts (Ctrl+C)

Use `--no-continuous` to add delays between sessions for manual intervention.

### Intelligent Error Handling
Errors are classified into categories with appropriate retry strategies:

| Category | Examples | Retry Strategy |
|----------|----------|----------------|
| `TRANSIENT` | Network timeout, connection reset | Aggressive retry (10x, 1s initial) |
| `RATE_LIMIT` | 429 errors, throttling | Long backoff (5x, 30s initial) |
| `AUTH` | 401, invalid token | No retry (fatal) |
| `LINEAR_API` | Linear service issues | Extended retry (8x, 5s initial) |
| `PUPPETEER` | Browser crashes | Moderate retry (5x, 3s initial) |
| `VALIDATION` | Blocked commands | No retry (agent must adapt) |

### Adaptive Pause
After 5 consecutive errors, the system automatically pauses with exponential backoff (30s → 60s → 120s → max 600s). This prevents rapid failure loops while allowing recovery when issues resolve.

### Health Monitoring
Each session tracks health metrics:
- Tool calls and error rates
- Blocked command counts
- Linear and Puppeteer failure rates
- Session duration and activity timestamps

### Watchdog Timer
A 5-minute watchdog timer detects hung sessions. If no activity is recorded for 5 minutes, the session is flagged for restart.

### Graceful Degradation
When Linear becomes unavailable:
1. System enters "degraded mode"
2. Agent focuses on code implementation
3. Pending Linear operations saved to `.linear_pending.json`
4. Operations retried when Linear recovers
5. Normal mode restored on first successful Linear call

### Stale Issue Recovery
Issues left "In Progress" for over 2 hours are flagged as stale. Agents receive priority instructions to recover these issues before starting new work.

## Session Management

### Session Summaries
After each session, the harness prints a detailed summary including:
- Session number and duration
- Issues worked on (detected from Linear issue IDs in output)
- Session status (continue/error)
- Autonomy status dashboard (sessions, issues, error patterns)

### Auto-Stop on Completion
By default, the agent automatically stops when all issues in Linear are marked as Done. This prevents the agent from running indefinitely after completing all work. Use `--no-auto-stop` to disable this behavior if you want the agent to keep running.

### Linear State Validation
On startup (for existing projects), the harness validates that `.linear_project.json` is properly configured:
- Checks for required fields (team_id, project_id, meta_issue_id)
- Verifies total_issues is reasonable
- Warns about potential configuration issues

Use `--skip-validation` to bypass this check if needed.

### Autonomy State Persistence
The autonomy state (`.autonomy_state.json`) is saved after each session and restored on restart. This includes:
- Consecutive error/success counts
- Total sessions and issues completed
- Degraded mode status
- Recent session history (last 10 sessions)

## License

MIT License - see [LICENSE](LICENSE) for details.
