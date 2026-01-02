"""
Prompt Loading Utilities
========================

Functions for loading prompt templates from the prompts directory.
"""

import json
import re
import shutil
from pathlib import Path


# Default port if detection fails
DEFAULT_DEV_PORT = 3000


def detect_dev_port(project_dir: Path) -> int:
    """
    Detect the development server port from project configuration.

    Checks in order:
    1. package.json "dev" script for -p or --port flag
    2. Falls back to DEFAULT_DEV_PORT (3000)

    Args:
        project_dir: Path to the project directory

    Returns:
        The detected port number
    """
    # Try package.json first
    package_json = project_dir / "package.json"
    if package_json.exists():
        try:
            with open(package_json) as f:
                pkg = json.load(f)

            dev_script = pkg.get("scripts", {}).get("dev", "")

            # Match patterns like: -p 3008, --port 3008, -p=3008, --port=3008
            port_match = re.search(r'(?:-p|--port)[=\s]+(\d+)', dev_script)
            if port_match:
                return int(port_match.group(1))
        except (json.JSONDecodeError, ValueError, IOError):
            pass

    return DEFAULT_DEV_PORT


PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompt_path = PROMPTS_DIR / f"{name}.md"
    return prompt_path.read_text()


def get_initializer_prompt() -> str:
    """Load the initializer prompt."""
    return load_prompt("initializer_prompt")


def get_coding_prompt() -> str:
    """Load the coding agent prompt."""
    return load_prompt("coding_prompt")


def get_add_features_prompt() -> str:
    """Load the add features prompt for extending existing projects."""
    return load_prompt("add_features_prompt")


def get_add_spec_prompt(spec_file: str) -> str:
    """Load the add spec prompt and substitute the spec filename."""
    prompt = load_prompt("add_spec_prompt")
    return prompt.replace("{SPEC_FILE}", spec_file)


def copy_spec_to_project(project_dir: Path) -> None:
    """Copy the app spec file into the project directory for the agent to read."""
    spec_source = PROMPTS_DIR / "app_spec.txt"
    spec_dest = project_dir / "app_spec.txt"
    if not spec_dest.exists():
        shutil.copy(spec_source, spec_dest)
        print("Copied app_spec.txt to project directory")
