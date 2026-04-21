"""Log streaming and terminal output helpers."""

import re
import sys
import time

# ANSI colours — fall back to empty strings if not a TTY
def _c(code: str) -> str:
    return code if sys.stdout.isatty() else ""

RESET  = _c("\033[0m")
BOLD   = _c("\033[1m")
DIM    = _c("\033[2m")
RED    = _c("\033[31m")
GREEN  = _c("\033[32m")
YELLOW = _c("\033[33m")
CYAN   = _c("\033[36m")
BLUE   = _c("\033[34m")


def status_color(state: str, result: str) -> str:
    if result in ("failed", "canceled", "abandoned"):
        return RED
    if result == "succeeded":
        return GREEN
    if state in ("inProgress", "notStarted"):
        return CYAN
    return YELLOW


def print_run_header(pipeline_name: str, branch: str, run_id: int, url: str):
    print(f"\n{BOLD}Pipeline : {CYAN}{pipeline_name}{RESET}")
    print(f"{BOLD}Branch   : {CYAN}{branch}{RESET}")
    print(f"{BOLD}Run ID   : {CYAN}{run_id}{RESET}")
    print(f"{BOLD}URL      : {DIM}{url}{RESET}")
    print()


def print_status_line(state: str, result: str):
    col = status_color(state, result)
    label = result if result else state
    print(f"\r{BOLD}Status   : {col}{label.upper()}{RESET}          ", end="", flush=True)


def print_section(title: str):
    bar = "─" * 60
    print(f"\n{DIM}{bar}{RESET}")
    print(f"{BOLD}{BLUE}{title}{RESET}")
    print(f"{DIM}{bar}{RESET}")


_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s?")


def _strip_timestamp(line: str) -> str:
    return _TIMESTAMP_RE.sub("", line)


def wait_for_completion(client, build_id: int, poll_interval: float = 2.0, stream_logs: bool = False,
                        log_offsets: dict = None, log_in_yaml: dict = None):
    """
    Poll until the build completes or an approval is needed.

    Returns:
      ("completed", result_str, build)  — pipeline finished
      ("approval_pending", approvals)   — one or more approvals are waiting

    Pass log_offsets and log_in_yaml from a previous call to avoid re-streaming
    already-seen lines (needed when re-entering after an approval gate).
    """
    tick = 0
    spinner = ["|", "/", "-", "\\"]
    if log_offsets is None:
        log_offsets = {}
    if log_in_yaml is None:
        log_in_yaml = {}

    while True:
        try:
            build = client.get_build(build_id)
        except Exception:
            time.sleep(poll_interval)
            continue

        build_status = build.get("status", "notStarted")
        build_result = build.get("result", "")

        if stream_logs:
            try:
                log_entries = client.get_build_logs(build_id)
                for entry in log_entries:
                    log_id = entry["id"]
                    start = log_offsets.get(log_id, 1)
                    in_yaml = log_in_yaml.get(log_id, False)
                    lines = client.get_log_lines(build_id, log_id, start_line=start)
                    if lines:
                        for line in lines:
                            clean = _strip_timestamp(line)
                            if "##[group]YAML being run" in clean:
                                in_yaml = True
                                continue
                            if in_yaml:
                                if "##[endgroup]" in clean:
                                    in_yaml = False
                                continue
                            print(clean)
                        log_offsets[log_id] = start + len(lines)
                        log_in_yaml[log_id] = in_yaml
            except Exception:
                pass
        else:
            if sys.stdout.isatty():
                spin = spinner[tick % len(spinner)]
                print(f"\r{DIM}{spin} running...{RESET}", end="", flush=True)

        if build_status == "completed":
            if sys.stdout.isatty():
                print("\r" + " " * 20 + "\r", end="")
            return "completed", build_result, build

        # Check for pending authorizations and approvals every few ticks.
        # Authorization (resource permission) is checked first — it blocks before
        # approvals become active (Checkpoint.Approval steps won't have initiatedOn
        # until Checkpoint.Authorization completes).
        if tick % 4 == 0:
            try:
                auth_stages = client.get_pending_authorizations(build_id)
                if auth_stages:
                    if sys.stdout.isatty():
                        print("\r" + " " * 20 + "\r", end="")
                    return "authorization_pending", auth_stages
                approvals = client.get_pending_approvals(build_id)
                if approvals:
                    if sys.stdout.isatty():
                        print("\r" + " " * 20 + "\r", end="")
                    return "approval_pending", approvals
            except Exception:
                pass

        tick += 1
        time.sleep(poll_interval)


def print_final_result(result: str, run_url: str):
    print()
    if result == "succeeded":
        print(f"\n{GREEN}{BOLD}✓ Pipeline succeeded{RESET}")
    elif result == "canceled":
        print(f"\n{YELLOW}{BOLD}⊘ Pipeline canceled{RESET}")
    else:
        print(f"\n{RED}{BOLD}✗ Pipeline failed  ({result}){RESET}")
    print(f"  {DIM}{run_url}{RESET}\n")
