"""pipelinectl — Azure DevOps pipeline CLI wrapper."""

import json
import os
import sys
import subprocess
from typing import Optional

import click

from .config import load_config, init_interactive, CONFIG_FILE
from .ado_client import ADOClient
from .output import (
    print_run_header,
    print_final_result,
    print_section,
    wait_for_completion,
    BOLD, CYAN, RESET, DIM, RED, GREEN, YELLOW,
)


def _get_azcli_token() -> str:
    try:
        result = subprocess.run(
            ["az", "account", "get-access-token", "--resource",
             "499b84ac-1321-427f-aa17-267ca6975798"],
            capture_output=True, text=True, check=True,
        )
    except FileNotFoundError:
        click.echo(f"{RED}[error]{RESET} Azure CLI not found. Install it or switch to PAT auth.", err=True)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        click.echo(f"{RED}[error]{RESET} Azure CLI token failed: {e.stderr.strip()}", err=True)
        click.echo("       Run `az login` to sign in.", err=True)
        sys.exit(1)
    return json.loads(result.stdout)["accessToken"]


def _make_client(cfg) -> ADOClient:
    cfg.validate_ado()
    if cfg.auth_method == "azcli":
        return ADOClient(cfg.ado_org, cfg.ado_project, bearer_token=_get_azcli_token())
    return ADOClient(cfg.ado_org, cfg.ado_project, pat=cfg.ado_pat)


def _run_url(org: str, project: str, pipeline_id: int, run_id: int) -> str:
    return (
        f"https://dev.azure.com/{org}/{project}/_build/results?buildId={run_id}"
    )


# ---------------------------------------------------------------------------
# CLI root
# ---------------------------------------------------------------------------

@click.group()
@click.version_option()
def cli():
    """pipelinectl — trigger and tail Azure DevOps pipelines from the terminal."""


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

@cli.command()
def init():
    """Interactive setup: configure org, project, and PAT."""
    init_interactive()


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@cli.command("list")
@click.option("--filter", "-f", "name_filter", default="", help="Filter by name substring.")
def list_pipelines(name_filter: str):
    """List available pipelines."""
    cfg = load_config()
    client = _make_client(cfg)

    try:
        pipelines = client.list_pipelines()
    except Exception as e:
        click.echo(f"{RED}[error]{RESET} Failed to fetch pipelines: {e}", err=True)
        sys.exit(1)

    if name_filter:
        pipelines = [p for p in pipelines if name_filter.lower() in p["name"].lower()]

    if not pipelines:
        click.echo("No pipelines found.")
        return

    click.echo(f"\n{'ID':>6}  {'Name'}")
    click.echo(f"{'─'*6}  {'─'*50}")
    for p in sorted(pipelines, key=lambda x: x["name"].lower()):
        click.echo(f"{p['id']:>6}  {p['name']}")
    click.echo()


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("pipeline", metavar="PIPELINE")
@click.option("--branch", "-b", default=None, help="Branch to run on (default from config).")
@click.option("--var", "-v", "variables", multiple=True, metavar="KEY=VALUE",
              help="Pipeline variables (can repeat).")
@click.option("--param", "-P", "parameters", multiple=True, metavar="KEY=VALUE",
              help="Template parameters (can repeat).")
@click.option("--no-follow", is_flag=True, default=False,
              help="Trigger the run but don't wait for completion.")
@click.option("--logs", "-l", "follow_logs", is_flag=True, default=False,
              help="Stream live log output (default: spinner only).")
@click.option("--push", "-p", is_flag=True, default=False,
              help="Git push the current branch before triggering.")
def run(pipeline: str, branch: Optional[str], variables: tuple, parameters: tuple, no_follow: bool, follow_logs: bool, push: bool):
    """Trigger a pipeline run and stream its logs.

    PIPELINE can be a pipeline name (substring match) or numeric ID.

    \b
    Examples:
      pipelinectl run build-and-test
      pipelinectl run 42 --branch feature/my-fix
      pipelinectl run deploy -v ENV=staging -v REGION=westeurope
      pipelinectl run build --push
    """
    cfg = load_config()
    client = _make_client(cfg)

    # Resolve branch: explicit flag > current git branch > config default
    if not branch:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, check=True,
            )
            branch = result.stdout.strip() or cfg.ado_default_branch
        except Exception:
            branch = cfg.ado_default_branch
    effective_branch = branch

    # Optional git push
    if push:
        click.echo(f"{DIM}$ git push{RESET}")
        result = subprocess.run(["git", "push"], capture_output=False)
        if result.returncode != 0:
            click.echo(f"{RED}[error]{RESET} git push failed — aborting.", err=True)
            sys.exit(result.returncode)

    # Resolve pipeline
    try:
        pipe = client.find_pipeline(pipeline)
    except ValueError as e:
        click.echo(f"{RED}[error]{RESET} {e}", err=True)
        sys.exit(1)

    if pipe is None:
        click.echo(f"{RED}[error]{RESET} Pipeline '{pipeline}' not found. "
                   "Run `pipelinectl list` to see available pipelines.", err=True)
        sys.exit(1)

    # Parse variables
    var_dict: dict[str, str] = {}
    for v in variables:
        if "=" not in v:
            click.echo(f"{RED}[error]{RESET} Variable '{v}' must be in KEY=VALUE format.", err=True)
            sys.exit(1)
        k, val = v.split("=", 1)
        var_dict[k] = val

    # Parse template parameters
    param_dict: dict[str, str] = {}
    for p in parameters:
        if "=" not in p:
            click.echo(f"{RED}[error]{RESET} Parameter '{p}' must be in KEY=VALUE format.", err=True)
            sys.exit(1)
        k, val = p.split("=", 1)
        param_dict[k] = val

    # Trigger
    click.echo(f"Triggering {BOLD}{pipe['name']}{RESET} on branch {CYAN}{effective_branch}{RESET} ...")
    try:
        run_data = client.run_pipeline(pipe["id"], effective_branch, var_dict or None, param_dict or None)
    except Exception as e:
        click.echo(f"{RED}[error]{RESET} Failed to trigger pipeline: {e}", err=True)
        sys.exit(1)

    run_id = run_data["id"]
    # ADO returns the pipeline run id which equals the build id
    build_id = run_id

    run_url = _run_url(cfg.ado_org, cfg.ado_project, pipe["id"], build_id)
    print_run_header(pipe["name"], effective_branch, run_id, run_url)

    if no_follow:
        click.echo("Run triggered. Use `pipelinectl logs` to fetch logs later.")
        return

    final_result = None
    log_offsets: dict = {}
    log_in_yaml: dict = {}
    seen_authorizations: set = set()
    try:
        while True:
            outcome = wait_for_completion(client, build_id, stream_logs=follow_logs,
                                          log_offsets=log_offsets, log_in_yaml=log_in_yaml)
            if outcome[0] == "authorization_pending":
                for auth in outcome[1]:
                    if auth["id"] not in seen_authorizations:
                        seen_authorizations.add(auth["id"])
                        click.echo(f"\n{YELLOW}{BOLD}⏸  Permission required{RESET}  "
                                   f"{DIM}stage: {auth['stage']}{RESET}")
                        click.echo("   This pipeline needs permission to access a protected resource.")
                        click.echo(f"   Grant access in Azure DevOps: {run_url}")
            elif outcome[0] == "approval_pending":
                approvals = outcome[1]
                for approval in approvals:
                    click.echo(f"\n{YELLOW}{BOLD}⏸  Approval required{RESET}  {DIM}(id: {approval['id']}){RESET}")
                    if approval.get("instructions"):
                        click.echo(f"   {approval['instructions']}")
                    approved = click.confirm("   Approve?", default=False)
                    comment = ""
                    if approved:
                        comment = click.prompt("   Comment (optional)", default="", show_default=False)
                    try:
                        client.resolve_approval(approval, approve=approved, comment=comment)
                        click.echo(f"   {GREEN}✓ {'Approved' if approved else 'Rejected'}{RESET}")
                    except Exception as e:
                        click.echo(f"   {RED}[error]{RESET} Could not resolve approval: {e}", err=True)
                        sys.exit(1)
            else:
                _, final_result, _ = outcome
                break
    except KeyboardInterrupt:
        click.echo(f"\n{YELLOW}Interrupted — run is still in progress.{RESET}")
        click.echo(f"  {run_url}")
        sys.exit(130)
    except Exception as e:
        click.echo(f"\n{RED}[error]{RESET} {e}", err=True)
        sys.exit(1)

    print_final_result(final_result, run_url)
    sys.exit(0 if final_result == "succeeded" else 1)


# ---------------------------------------------------------------------------
# logs  (re-fetch logs from a previous run)
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("pipeline", metavar="PIPELINE", required=False)
@click.option("--run-id", "-r", "run_id", type=int, default=None,
              help="Specific run/build ID to fetch logs from.")
@click.option("--last", "-n", default=1, show_default=True,
              help="Which run to fetch if --run-id is not given (1 = most recent).")
@click.option("--watch", "-w", is_flag=True, default=False,
              help="Stream live logs and exit when the run completes.")
def logs(pipeline: Optional[str], run_id: Optional[int], last: int, watch: bool):
    """Print logs from a previous run.

    \b
    Examples:
      pipelinectl logs build-and-test                 # logs from most recent run
      pipelinectl logs build-and-test --run-id 12345  # logs from specific run
      pipelinectl logs 11                             # pipeline by ID, most recent
      pipelinectl logs 11 --run-id 12345              # pipeline by ID, specific run
      pipelinectl logs --run-id 12345                 # logs by build ID only
      pipelinectl logs build-and-test --last 2        # logs from 2nd most recent run
      pipelinectl logs build-and-test --watch         # tail live logs until completion
    """
    cfg = load_config()
    client = _make_client(cfg)

    if pipeline is None and run_id is None:
        click.echo(f"{RED}[error]{RESET} Provide a PIPELINE name/ID or --run-id.", err=True)
        sys.exit(1)

    pipe = None
    if pipeline is not None:
        try:
            pipe = client.find_pipeline(pipeline)
        except ValueError as e:
            click.echo(f"{RED}[error]{RESET} {e}", err=True)
            sys.exit(1)

        if pipe is None:
            click.echo(f"{RED}[error]{RESET} Pipeline '{pipeline}' not found.", err=True)
            sys.exit(1)

    if run_id is None:
        runs = client.list_runs(pipe["id"], top=last + 1)
        if not runs:
            click.echo("No runs found for this pipeline.", err=True)
            sys.exit(1)
        run_data = runs[last - 1]
        build_id = run_data["id"]
        run_id = build_id
    else:
        build_id = run_id

    pipeline_name = pipe["name"] if pipe else f"build {build_id}"
    run_url = _run_url(cfg.ado_org, cfg.ado_project, pipe["id"] if pipe else 0, build_id)
    print_run_header(pipeline_name, "(historical)", run_id, run_url)

    if watch:
        final_result = None
        log_offsets: dict = {}
        log_in_yaml: dict = {}
        seen_authorizations: set = set()
        seen_approvals: set = set()
        try:
            while True:
                outcome = wait_for_completion(client, build_id, stream_logs=True,
                                              log_offsets=log_offsets, log_in_yaml=log_in_yaml)
                if outcome[0] == "authorization_pending":
                    for auth in outcome[1]:
                        if auth["id"] not in seen_authorizations:
                            seen_authorizations.add(auth["id"])
                            click.echo(f"\n{YELLOW}{BOLD}⏸  Permission required{RESET}  "
                                       f"{DIM}stage: {auth['stage']}{RESET}")
                            click.echo("   This pipeline needs permission to access a protected resource.")
                            click.echo(f"   Grant access in Azure DevOps: {run_url}")
                elif outcome[0] == "approval_pending":
                    for approval in outcome[1]:
                        if approval["id"] not in seen_approvals:
                            seen_approvals.add(approval["id"])
                            click.echo(f"\n{YELLOW}{BOLD}⏸  Approval required{RESET}  "
                                       f"{DIM}(id: {approval['id']}){RESET}")
                            if approval.get("instructions"):
                                click.echo(f"   {approval['instructions']}")
                            click.echo(f"   Approve in Azure DevOps: {run_url}")
                else:
                    _, final_result, _ = outcome
                    break
        except KeyboardInterrupt:
            click.echo(f"\n{YELLOW}Interrupted — run may still be in progress.{RESET}")
            click.echo(f"  {run_url}")
            sys.exit(130)
        except Exception as e:
            click.echo(f"\n{RED}[error]{RESET} {e}", err=True)
            sys.exit(1)
        print_final_result(final_result, run_url)
        sys.exit(0 if final_result == "succeeded" else 1)

    print_section("Logs")

    try:
        log_entries = client.get_build_logs(build_id)
    except Exception as e:
        click.echo(f"{RED}[error]{RESET} Failed to fetch logs: {e}", err=True)
        sys.exit(1)

    if not log_entries:
        click.echo("No logs found.")
        return

    for entry in log_entries:
        try:
            content = client.get_log_content(build_id, entry["id"])
            if content.strip():
                print(content)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# params
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("pipeline", metavar="PIPELINE")
def params(pipeline: str):
    """Show available parameters and variables for a pipeline.

    \b
    Examples:
      pipelinectl params build-and-test
      pipelinectl params 42
    """
    cfg = load_config()
    client = _make_client(cfg)

    try:
        pipe = client.find_pipeline(pipeline)
    except ValueError as e:
        click.echo(f"{RED}[error]{RESET} {e}", err=True)
        sys.exit(1)

    if pipe is None:
        click.echo(f"{RED}[error]{RESET} Pipeline '{pipeline}' not found.", err=True)
        sys.exit(1)

    try:
        defn = client.get_build_definition(pipe["id"])
    except Exception as e:
        click.echo(f"{RED}[error]{RESET} Failed to fetch pipeline definition: {e}", err=True)
        sys.exit(1)

    click.echo(f"\n{BOLD}{pipe['name']}{RESET}\n")

    # Template parameters (YAML `parameters:` block) — stored as JSON string
    import json
    raw_params = defn.get("parameters")
    if raw_params:
        try:
            parsed = json.loads(raw_params)
        except (json.JSONDecodeError, TypeError):
            parsed = None
        if parsed:
            click.echo(f"{BOLD}Template parameters{RESET} (pass with -P KEY=VALUE):")
            click.echo(f"  {'Name':30}  {'Default'}")
            click.echo(f"  {'─'*30}  {'─'*20}")
            for name, meta in parsed.items():
                default = meta.get("default", {}).get("value", "")
                click.echo(f"  {name:30}  {DIM}{default}{RESET}")
            click.echo()

    # Variables defined on the pipeline (settable at queue time)
    variables = {
        name: meta
        for name, meta in defn.get("variables", {}).items()
        if meta.get("allowOverride", False)
    }
    if variables:
        click.echo(f"{BOLD}Variables{RESET} (pass with -v KEY=VALUE, queue-time settable):")
        click.echo(f"  {'Name':30}  {'Default'}")
        click.echo(f"  {'─'*30}  {'─'*20}")
        for name, meta in variables.items():
            default = meta.get("value", "")
            click.echo(f"  {name:30}  {DIM}{default}{RESET}")
        click.echo()

    if not raw_params and not variables:
        click.echo(f"{DIM}No exposed parameters or queue-time variables found.{RESET}")
        click.echo(f"{DIM}YAML template parameters are not always returned by the API.{RESET}")
        click.echo(f"{DIM}Check the pipeline YAML for a 'parameters:' block.{RESET}")
    click.echo()


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("pipeline", metavar="PIPELINE")
@click.option("--top", "-n", default=5, show_default=True, help="Number of recent runs to show.")
def status(pipeline: str, top: int):
    """Show recent run status for a pipeline.

    \b
    Examples:
      pipelinectl status build-and-test
      pipelinectl status deploy --top 10
    """
    cfg = load_config()
    client = _make_client(cfg)

    try:
        pipe = client.find_pipeline(pipeline)
    except ValueError as e:
        click.echo(f"{RED}[error]{RESET} {e}", err=True)
        sys.exit(1)

    if pipe is None:
        click.echo(f"{RED}[error]{RESET} Pipeline '{pipeline}' not found.", err=True)
        sys.exit(1)

    runs = client.list_runs(pipe["id"], top=top)
    if not runs:
        click.echo("No runs found.")
        return

    click.echo(f"\n{BOLD}{pipe['name']}{RESET} — last {len(runs)} runs\n")
    click.echo(f"{'ID':>8}  {'State':12}  {'Result':12}  {'Branch'}")
    click.echo(f"{'─'*8}  {'─'*12}  {'─'*12}  {'─'*30}")

    for r in runs:
        state  = r.get("state", "?")
        result = r.get("result", "—")
        branch = r.get("resources", {}).get("repositories", {}).get("self", {}).get("refName", "?")
        branch = branch.replace("refs/heads/", "")
        run_id = r["id"]

        if result == "succeeded":
            col = GREEN
        elif result in ("failed", "abandoned"):
            col = RED
        elif result == "canceled":
            col = YELLOW
        else:
            col = CYAN

        click.echo(f"{run_id:>8}  {state:12}  {col}{result:12}{RESET}  {branch}")
    click.echo()


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

@cli.group()
def config():
    """Manage pipelinectl configuration."""


@config.command("show")
def config_show():
    """Show the current configuration."""
    cfg = load_config()

    click.echo(f"\n{BOLD}pipelinectl configuration{RESET}  {DIM}({CONFIG_FILE}){RESET}\n")
    click.echo(f"  {'organization':20}  {cfg.ado_org or f'{DIM}(not set){RESET}'}")
    click.echo(f"  {'project':20}  {cfg.ado_project or f'{DIM}(not set){RESET}'}")
    click.echo(f"  {'default_branch':20}  {cfg.ado_default_branch}")

    auth = cfg.auth_method
    if auth == "azcli":
        click.echo(f"  {'auth':20}  azcli")
    else:
        pat_raw = cfg.ado_pat
        pat_source = "env (ADO_PAT)" if os.environ.get("ADO_PAT") else str(CONFIG_FILE)
        if pat_raw:
            pat_display = f"{'*' * (len(pat_raw) - 4)}{pat_raw[-4:]}" if len(pat_raw) > 4 else "****"
        else:
            pat_display = f"{DIM}(not set){RESET}"
        click.echo(f"  {'auth':20}  pat  {DIM}({pat_display} [{pat_source}]){RESET}")
    click.echo()


@config.group("set")
def config_set():
    """Update configuration values."""


@config_set.group("auth")
def config_set_auth():
    """Configure the authentication method."""


@config_set_auth.command("pat")
@click.argument("pat_value", metavar="PAT")
def config_set_auth_pat(pat_value: str):
    """Store a Personal Access Token for authentication."""
    cfg = load_config()
    cfg.update_ado(pat=pat_value, auth=None)  # auth=None removes the key; pat is the default
    click.echo(f"PAT saved to {CONFIG_FILE} (permissions: 600)")


@config_set_auth.command("azcli")
def config_set_auth_azcli():
    """Use Azure CLI for authentication (removes PAT from config)."""
    cfg = load_config()
    cfg.update_ado(pat=None, auth="azcli")
    click.echo(f"Auth method set to azcli, PAT removed from {CONFIG_FILE}")
    click.echo("Run `az login` if not already signed in.")


# ---------------------------------------------------------------------------
# push-run  (convenience alias)
# ---------------------------------------------------------------------------

@cli.command("push-run")
@click.argument("pipeline", metavar="PIPELINE")
@click.option("--branch", "-b", default=None)
@click.option("--var", "-v", "variables", multiple=True, metavar="KEY=VALUE")
@click.option("--param", "-P", "parameters", multiple=True, metavar="KEY=VALUE")
@click.option("--logs", "-l", "follow_logs", is_flag=True, default=False)
@click.pass_context
def push_run(ctx, pipeline: str, branch: Optional[str], variables: tuple, parameters: tuple, follow_logs: bool):
    """Git push then trigger a pipeline run (shortcut for `run --push`).

    \b
    Example:
      pipelinectl push-run build-and-test --branch feature/my-fix
    """
    ctx.invoke(run, pipeline=pipeline, branch=branch,
               variables=variables, parameters=parameters, no_follow=False, follow_logs=follow_logs, push=True)
