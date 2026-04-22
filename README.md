```
       _            _ _                 _   _
 _ __ (_)_ __   ___| (_)_ __   ___  ___| |_| |
| '_ \| | '_ \ / _ \ | | '_ \ / _ \/ __| __| |
| |_) | | |_) |  __/ | | | | |  __/ (__| |_| |
| .__/|_| .__/ \___|_|_|_| |_|\___|\___|\__|_|
|_|     |_|              trigger · tail · ship
```

![demo](demo/demo.gif)

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
# Homebrew (macOS, recommended)
brew tap Borrelworst/pipelinectl
brew install Borrelworst/pipelinectl/pipelinectl

# PyPI
pip install pipelinectl
```

For local development:
```bash
pip install --editable ".[dev]"
```

---

## Commands

### `pipelinectl init`

Interactive setup wizard. Run once after installing.

```bash
pipelinectl init
```

Prompts for organization, project, default branch, and authentication method (see [Authentication](#authentication) below). Config is saved to `~/.pipelinectl/config.toml` with `chmod 600`.

---

### `pipelinectl list`

List all pipelines in your project.

```bash
pipelinectl list
pipelinectl list --filter deploy
```

---

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

**Permission gates** — when a pipeline needs access to a protected resource for the first time, pipelinectl detects it and prints the ADO URL to grant access:
```
⏸  Permission required  stage: Deploy
   Grant access in Azure DevOps: https://dev.azure.com/...
```

---

### `pipelinectl push-run PIPELINE`

Shortcut for `run --push`. Pushes the current branch then triggers the pipeline.

```bash
pipelinectl push-run build-and-test
pipelinectl push-run build-and-test --logs
```

---

### `pipelinectl status PIPELINE`

Show recent run history.

```bash
pipelinectl status build-and-test
pipelinectl status deploy --top 10
```

---

### `pipelinectl logs PIPELINE`

Fetch logs from a previous run without re-triggering.

```bash
pipelinectl logs build-and-test                 # most recent run
pipelinectl logs build-and-test --run-id 98765  # specific run ID
pipelinectl logs build-and-test --last 2        # 2nd most recent
pipelinectl logs --run-id 98765                 # by build ID only, no pipeline needed
pipelinectl logs build-and-test --watch         # tail live logs until completion
```

---

### `pipelinectl params PIPELINE`

Show queue-time variables and template parameters for a pipeline.

```bash
pipelinectl params build-and-test
pipelinectl params 42
```

---

### `pipelinectl config`

View and update configuration without editing the file directly.

```bash
pipelinectl config show                        # show current config
pipelinectl config set auth pat <PAT>          # switch to PAT authentication
pipelinectl config set auth azcli             # switch to Azure CLI authentication
```

---

## Authentication

pipelinectl supports two authentication methods.

### Personal Access Token (PAT)

Create a PAT in Azure DevOps with *Build: Read & execute* and *Pipeline Resources: Use* permissions, then configure it:

```bash
pipelinectl init          # enter PAT during setup
# or
pipelinectl config set auth pat <your-token>
# or
export ADO_PAT=<your-token>   # env var takes precedence over config
```

### Azure CLI

If you're already signed in with the Azure CLI (`az login`), you can use it instead of a PAT — no token management required:

```bash
az login                          # sign in once
pipelinectl config set auth azcli # switch pipelinectl to use az cli
```

pipelinectl will call `az account get-access-token` automatically on each command. This is the recommended method in environments where you're already using the Azure CLI.

---

## Config file

`~/.pipelinectl/config.toml`:
```toml
[azure_devops]
organization   = "mycompany"
project        = "MyProject"
default_branch = "main"     # fallback when not in a git repo

# PAT auth (default):
pat            = "xxxx"     # or use ADO_PAT env var

# Azure CLI auth (alternative to PAT):
# auth           = "azcli"
```

