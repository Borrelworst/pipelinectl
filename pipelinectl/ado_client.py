"""Azure DevOps REST API client."""

import base64
import time
from typing import Optional
import requests


class ADOClient:
    """Thin wrapper around the Azure DevOps REST API."""

    def __init__(self, org: str, project: str, pat: str):
        self.org = org
        self.project = project
        self.base = f"https://dev.azure.com/{org}/{project}/_apis"
        token = base64.b64encode(f":{pat}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Pipelines
    # ------------------------------------------------------------------

    def list_pipelines(self) -> list[dict]:
        url = f"{self.base}/pipelines?api-version=7.1"
        r = self._get(url)
        return r.get("value", [])

    def get_pipeline(self, pipeline_id: int) -> dict:
        url = f"{self.base}/pipelines/{pipeline_id}?api-version=7.1"
        return self._get(url)

    def find_pipeline(self, name_or_id: str) -> Optional[dict]:
        """Find a pipeline by name (substring match) or numeric ID."""
        if name_or_id.isdigit():
            return self.get_pipeline(int(name_or_id))
        pipelines = self.list_pipelines()
        name_lower = name_or_id.lower()
        matches = [p for p in pipelines if name_lower in p["name"].lower()]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(
                f"Ambiguous pipeline name '{name_or_id}'. Matches:\n"
                + "\n".join(f"  [{p['id']}] {p['name']}" for p in matches)
            )
        return None

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    def run_pipeline(
        self,
        pipeline_id: int,
        branch: str,
        variables: Optional[dict] = None,
        parameters: Optional[dict] = None,
    ) -> dict:
        url = f"{self.base}/pipelines/{pipeline_id}/runs?api-version=7.1"
        body: dict = {
            "resources": {
                "repositories": {
                    "self": {"refName": f"refs/heads/{branch}"}
                }
            }
        }
        if variables:
            body["variables"] = {k: {"value": v} for k, v in variables.items()}
        if parameters:
            body["templateParameters"] = parameters
        r = requests.post(url, json=body, headers=self.headers, timeout=30)
        r.raise_for_status()
        return r.json()

    def get_run(self, pipeline_id: int, run_id: int) -> dict:
        url = f"{self.base}/pipelines/{pipeline_id}/runs/{run_id}?api-version=7.1"
        return self._get(url)

    def list_runs(self, pipeline_id: int, top: int = 10) -> list[dict]:
        url = f"{self.base}/pipelines/{pipeline_id}/runs?api-version=7.1&$top={top}"
        return self._get(url).get("value", [])

    # ------------------------------------------------------------------
    # Build logs  (build API, which backs pipeline runs)
    # ------------------------------------------------------------------

    def get_pending_approvals(self, run_id: int) -> list[dict]:
        url = (
            f"https://dev.azure.com/{self.org}/{self.project}/_apis/pipelines/approvals"
            f"?runId={run_id}&state=pending&$expand=steps&api-version=7.1-preview.1"
        )
        approvals = self._get(url).get("value", [])
        # ADO ignores the runId filter and returns all pending approvals for the
        # pipeline. Filter client-side to only approvals that belong to this run
        # and have actually been initiated (not just pre-created).
        return [
            a for a in approvals
            if a.get("pipeline", {}).get("owner", {}).get("id") == run_id
            and any(step.get("initiatedOn") for step in a.get("steps", []))
        ]

    def resolve_approval(self, approval: dict, approve: bool, comment: str = "") -> dict:
        # Use the batch endpoint with the project GUID from the approval's self-link.
        # The per-approval PATCH endpoint requires an undocumented updateParameters
        # wrapper; the batch endpoint with an array body is the reliable format.
        self_href = approval.get("_links", {}).get("self", {}).get("href", "")
        if self_href:
            # Extract base up to /_apis/ and build the collection approvals URL
            base = self_href.split("/_apis/")[0]
            url = f"{base}/_apis/pipelines/approvals?api-version=7.1-preview.1"
        else:
            url = f"https://dev.azure.com/{self.org}/{self.project}/_apis/pipelines/approvals?api-version=7.1-preview.1"
        body = [{"approvalId": approval["id"], "status": "approved" if approve else "rejected", "comment": comment}]
        r = requests.patch(url, json=body, headers=self.headers, timeout=30)
        r.raise_for_status()
        return r.json()

    def get_build_definition(self, definition_id: int) -> dict:
        url = f"https://dev.azure.com/{self.org}/{self.project}/_apis/build/definitions/{definition_id}?api-version=7.1"
        return self._get(url)

    def get_build(self, build_id: int) -> dict:
        url = f"https://dev.azure.com/{self.org}/{self.project}/_apis/build/builds/{build_id}?api-version=7.1"
        return self._get(url)

    def get_build_logs(self, build_id: int) -> list[dict]:
        url = f"https://dev.azure.com/{self.org}/{self.project}/_apis/build/builds/{build_id}/logs?api-version=7.1"
        return self._get(url).get("value", [])

    def get_log_content(self, build_id: int, log_id: int) -> str:
        url = f"https://dev.azure.com/{self.org}/{self.project}/_apis/build/builds/{build_id}/logs/{log_id}?api-version=7.1"
        r = requests.get(url, headers={**self.headers, "Accept": "text/plain"}, timeout=30)
        r.raise_for_status()
        return r.text

    def get_log_lines(self, build_id: int, log_id: int, start_line: int) -> list[str]:
        """Fetch log lines starting from start_line (1-indexed). Returns new lines only."""
        url = (
            f"https://dev.azure.com/{self.org}/{self.project}/_apis/build/builds/{build_id}"
            f"/logs/{log_id}?startLine={start_line}&api-version=7.1"
        )
        r = requests.get(url, headers={**self.headers, "Accept": "text/plain"}, timeout=30)
        r.raise_for_status()
        return r.text.splitlines()

    def get_timeline(self, build_id: int) -> dict:
        url = f"https://dev.azure.com/{self.org}/{self.project}/_apis/build/builds/{build_id}/timeline?api-version=7.1"
        return self._get(url)

    # ------------------------------------------------------------------
    # Polling helpers
    # ------------------------------------------------------------------

    def wait_for_run(
        self,
        pipeline_id: int,
        run_id: int,
        poll_interval: float = 5.0,
        on_status: callable = None,
    ) -> dict:
        """Block until the run finishes, calling on_status on each poll."""
        terminal = {"succeeded", "failed", "canceled", "skipped", "abandoned"}
        while True:
            run = self.get_run(pipeline_id, run_id)
            state = run.get("state", "unknown")
            result = run.get("result", "")
            if on_status:
                on_status(state, result, run)
            if state == "completed" or result in terminal:
                return run
            time.sleep(poll_interval)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get(self, url: str) -> dict:
        r = requests.get(url, headers=self.headers, timeout=30)
        r.raise_for_status()
        return r.json()
