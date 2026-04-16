# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development setup

```bash
pip install --editable .   # installs the pipelinectl command in the active venv
```

No build step. Editable install means code changes are reflected immediately without reinstalling.

## Architecture

Four modules, each with a single responsibility:

- **`cli.py`** — All Click commands (`init`, `list`, `run`, `push-run`, `status`, `logs`, `params`). Orchestrates the other modules; contains no API or I/O logic.
- **`ado_client.py`** — Thin wrapper around the Azure DevOps REST API. All HTTP calls live here. Key non-obvious behaviours:
  - `find_pipeline()` does case-insensitive substring match; raises `ValueError` on ambiguous match.
  - `get_pending_approvals()` filters client-side because the ADO `runId` query param is ignored by the API — it returns all pending approvals for the pipeline, so we match on `pipeline.owner.id == run_id`.
  - `resolve_approval()` must use the **batch** endpoint (`PATCH /approvals` with array body) — the per-approval endpoint returns 400 due to an undocumented `updateParameters` requirement.
  - `get_log_lines()` uses `startLine` for incremental fetching (1-indexed).
- **`config.py`** — Reads/writes `~/.pipelinectl/config.toml`. PAT is read from `ADO_PAT` env var first, then config.
- **`output.py`** — Terminal rendering and the polling loop (`wait_for_completion`). The loop polls every 2 seconds, optionally streams logs, and surfaces approval gates only when `steps[].initiatedOn` is set (ADO pre-creates approval records at queue time before the gate is actually reached).

## Key ADO API quirks documented in the code

- Approvals API ignores `runId` filter — filter client-side by `pipeline.owner.id`
- Approval resolution requires the batch endpoint with array body, not the per-approval PATCH
- Log content supports `startLine` for incremental streaming
- `pipeline.owner.id` in the approval object equals the build ID of the run that needs approval
