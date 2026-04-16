# pipelinectl

A minimal CLI to trigger and tail Azure DevOps pipelines directly from your terminal — no browser, no copy-paste.

## Why?

The typical workflow:
1. Push code
2. Open browser → select org → select project → select pipeline → select branch → click Run
3. Wait for logs to appear
4. Copy error → paste into Claude Code
5. Fix → repeat

With `pipelinectl`:
```bash
pipelinectl push-run build-and-test
# ^ pushes, triggers, tails logs, exits non-zero on failure
```

Claude Code sees the error output directly if the pipeline fails.

---

## Installation

```bash
pip install pipelinectl
```

For local development:
```bash
pip install --editable .
```

---

## Setup

```bash
pipelinectl init
```

Prompts for:
- Azure DevOps **organization** (e.g. `mycompany`)
- Azure DevOps **project** (e.g. `MyProject`)
- **Personal Access Token** (PAT) — needs *Build: Read & execute* and *Pipeline Resources: Use*
- **Default branch** (fallback when not inside a git repo)

Config is saved to `~/.pipelinectl/config.toml` with `chmod 600`.

Set `ADO_PAT` as an environment variable to override the PAT from config.

---

## Commands

### `pipelinectl run PIPELINE`

Trigger a pipeline and wait for it to finish.

```bash
pipelinectl run build-and-test                        # uses current git branch
pipelinectl run build-and-test --branch main          # explicit branch
pipelinectl run 42                                    # by numeric pipeline ID
pipelinectl run deploy -v ENV=staging -v REGION=westeurope  # queue-time variables
pipelinectl run install -P dev=true -P version=1.2   # YAML template parameters
pipelinectl run build-and-test --logs                 # stream live log output
pipelinectl run build-and-test --no-follow            # trigger only, don't wait
pipelinectl run build-and-test --push                 # git push first, then trigger
```

Branch resolution order: `--branch` flag → current git branch → config `default_branch`.

PIPELINE is matched by case-insensitive substring against pipeline names, or exact numeric ID. If multiple pipelines match, the command errors and lists them.

Exit code is `0` on success, `1` on failure.

**Approval gates** — when the pipeline reaches an approval gate, pipelinectl pauses and prompts you to approve or reject inline:
```
⏸  Approval required
   Approve? [y/N]:
```

---

### `pipelinectl push-run PIPELINE`

Shortcut for `run --push`. Pushes the current branch then triggers the pipeline.

```bash
pipelinectl push-run build-and-test
pipelinectl push-run build-and-test --logs
```

---

### `pipelinectl list`

List all pipelines in your project.

```bash
pipelinectl list
pipelinectl list --filter deploy
```

---

### `pipelinectl params PIPELINE`

Show queue-time variables and template parameters for a pipeline.

```bash
pipelinectl params build-and-test
pipelinectl params 42
```

---

### `pipelinectl status PIPELINE`

Show recent run history.

```bash
pipelinectl status build-and-test
pipelinectl status deploy --top 10
```

---

### `pipelinectl logs PIPELINE [RUN_ID]`

Fetch logs from a previous run without re-triggering.

```bash
pipelinectl logs build-and-test           # most recent run
pipelinectl logs build-and-test 98765     # specific run ID
pipelinectl logs build-and-test --last 2  # 2nd most recent
```

---

## Config file

`~/.pipelinectl/config.toml`:
```toml
[azure_devops]
organization   = "mycompany"
project        = "MyProject"
pat            = "xxxx"     # or use ADO_PAT env var
default_branch = "main"     # fallback when not in a git repo
```
