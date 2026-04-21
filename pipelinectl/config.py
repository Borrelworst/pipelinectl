"""Config management — reads/writes ~/.pipelinectl/config.toml"""

import os
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # fallback
    except ImportError:
        tomllib = None  # type: ignore

try:
    import tomli_w
except ImportError:
    tomli_w = None  # type: ignore

CONFIG_DIR = Path.home() / ".pipelinectl"
CONFIG_FILE = CONFIG_DIR / "config.toml"

DEFAULT_CONFIG = """\
# pipelinectl configuration
# Run `pipelinectl init` to create this interactively.

[azure_devops]
organization = ""          # e.g. "mycompany"
project      = ""          # e.g. "MyProject"
pat          = ""          # Personal Access Token (read: Build, Pipeline)
default_branch = "main"   # branch used when --branch is not given
"""


class Config:
    def __init__(self, data: dict):
        self._data = data

    # --- Azure DevOps -------------------------------------------------

    @property
    def ado_org(self) -> str:
        return self._data.get("azure_devops", {}).get("organization", "")

    @property
    def ado_project(self) -> str:
        return self._data.get("azure_devops", {}).get("project", "")

    @property
    def ado_pat(self) -> str:
        return (
            os.environ.get("ADO_PAT")
            or self._data.get("azure_devops", {}).get("pat", "")
        )

    @property
    def ado_default_branch(self) -> str:
        return self._data.get("azure_devops", {}).get("default_branch", "main")

    @property
    def auth_method(self) -> str:
        return self._data.get("azure_devops", {}).get("auth", "pat")

    def validate_ado(self):
        missing = []
        if not self.ado_org:
            missing.append("organization")
        if not self.ado_project:
            missing.append("project")
        if self.auth_method == "pat" and not self.ado_pat:
            missing.append("pat (or set ADO_PAT env var)")
        if missing:
            print(
                f"[error] Missing Azure DevOps config: {', '.join(missing)}\n"
                f"        Run `pipelinectl init` or edit {CONFIG_FILE}",
                file=sys.stderr,
            )
            sys.exit(1)


def load_config() -> Config:
    if not CONFIG_FILE.exists():
        return Config({})
    if tomllib is None:
        print(
            "[error] TOML parser not available. Install tomli: pip install tomli",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(CONFIG_FILE, "rb") as f:
        return Config(tomllib.load(f))


def save_config(data: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if tomli_w is None:
        # Fallback: write a simple TOML manually for basic structures
        lines = []
        for section, values in data.items():
            lines.append(f"[{section}]")
            for k, v in values.items():
                lines.append(f'{k} = "{v}"')
            lines.append("")
        CONFIG_FILE.write_text("\n".join(lines))
    else:
        with open(CONFIG_FILE, "wb") as f:
            tomli_w.dump(data, f)
    # Restrict permissions so the PAT isn't world-readable
    CONFIG_FILE.chmod(0o600)


def init_interactive():
    """Walk the user through creating a config file."""
    print("=== pipelinectl init ===\n")
    print(f"Config will be saved to: {CONFIG_FILE}\n")

    existing: dict = {}
    if CONFIG_FILE.exists() and tomllib is not None:
        with open(CONFIG_FILE, "rb") as f:
            existing = tomllib.load(f)

    ado = existing.get("azure_devops", {})

    def ask(prompt: str, default: str = "") -> str:
        hint = f" [{default}]" if default else ""
        val = input(f"{prompt}{hint}: ").strip()
        return val if val else default

    org = ask("Azure DevOps organization", ado.get("organization", ""))
    project = ask("Azure DevOps project", ado.get("project", ""))

    current_auth = ado.get("auth", "pat")
    auth_method = ask("Authentication method (pat/azcli)", current_auth)
    while auth_method not in ("pat", "azcli"):
        print("  Please enter 'pat' or 'azcli'.")
        auth_method = ask("Authentication method (pat/azcli)", current_auth)

    ado_section: dict = {
        "organization": org,
        "project": project,
        "default_branch": ask("Default branch", ado.get("default_branch", "main")),
    }

    if auth_method == "azcli":
        ado_section["auth"] = "azcli"
        print("  Using Azure CLI auth — run `az login` if not already signed in.")
    else:
        pat = ask("Personal Access Token (PAT)", ado.get("pat", ""))
        ado_section["pat"] = pat

    save_config({"azure_devops": ado_section})
    print(f"\n✓ Config saved to {CONFIG_FILE} (permissions: 600)")
    if auth_method == "pat":
        print("  Tip: you can also set ADO_PAT as an env var to avoid storing the token on disk.")
