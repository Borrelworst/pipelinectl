import pytest
from unittest.mock import patch
from pipelinectl.ado_client import ADOClient


@pytest.fixture
def client():
    return ADOClient("myorg", "myproject", pat="mytoken")


def test_find_pipeline_by_numeric_id(client):
    fake = {"id": 42, "name": "Build"}
    with patch.object(client, "get_pipeline", return_value=fake) as mock:
        result = client.find_pipeline("42")
        mock.assert_called_once_with(42)
        assert result == fake


def test_find_pipeline_substring_match(client):
    pipelines = [{"id": 1, "name": "Build and Test"}, {"id": 2, "name": "Deploy"}]
    with patch.object(client, "list_pipelines", return_value=pipelines):
        result = client.find_pipeline("build")
        assert result["id"] == 1


def test_find_pipeline_case_insensitive(client):
    pipelines = [{"id": 1, "name": "Build and Test"}]
    with patch.object(client, "list_pipelines", return_value=pipelines):
        assert client.find_pipeline("BUILD") is not None
        assert client.find_pipeline("build and test") is not None


def test_find_pipeline_ambiguous(client):
    pipelines = [{"id": 1, "name": "Build Dev"}, {"id": 2, "name": "Build Prod"}]
    with patch.object(client, "list_pipelines", return_value=pipelines):
        with pytest.raises(ValueError, match="Ambiguous"):
            client.find_pipeline("build")


def test_find_pipeline_not_found(client):
    with patch.object(client, "list_pipelines", return_value=[]):
        assert client.find_pipeline("nonexistent") is None


def test_bearer_token_auth():
    c = ADOClient("myorg", "myproject", bearer_token="mybearer")
    assert c.headers["Authorization"] == "Bearer mybearer"


def test_pat_auth():
    import base64
    c = ADOClient("myorg", "myproject", pat="mytoken")
    expected = "Basic " + base64.b64encode(b":mytoken").decode()
    assert c.headers["Authorization"] == expected


def test_get_pending_approvals_filters_by_run_id(client):
    approvals = [
        {
            "id": "aaa",
            "status": "pending",
            "pipeline": {"owner": {"id": 100}},
            "steps": [{"initiatedOn": "2026-04-16T10:00:00Z"}],
            "_links": {},
        },
        {
            "id": "bbb",
            "status": "pending",
            "pipeline": {"owner": {"id": 999}},  # different run
            "steps": [{"initiatedOn": "2026-04-16T10:00:00Z"}],
            "_links": {},
        },
    ]
    with patch.object(client, "_get", return_value={"value": approvals}):
        result = client.get_pending_approvals(100)
        assert len(result) == 1
        assert result[0]["id"] == "aaa"


def test_get_pending_approvals_filters_uninitiated(client):
    approvals = [
        {
            "id": "aaa",
            "status": "pending",
            "pipeline": {"owner": {"id": 100}},
            "steps": [{"initiatedOn": None}],  # not yet initiated
            "_links": {},
        },
    ]
    with patch.object(client, "_get", return_value={"value": approvals}):
        result = client.get_pending_approvals(100)
        assert len(result) == 0


def test_get_pending_authorizations_returns_blocked_stages(client):
    auth_id = "auth-1"
    checkpoint_id = "cp-1"
    stage_id = "stage-1"
    timeline = {
        "records": [
            {"id": auth_id, "type": "Checkpoint.Authorization", "state": "inProgress",
             "parentId": checkpoint_id, "name": "Auth"},
            {"id": checkpoint_id, "type": "Checkpoint", "state": "inProgress",
             "parentId": stage_id, "name": "Checkpoint"},
            {"id": stage_id, "type": "Stage", "state": "inProgress",
             "parentId": None, "name": "Deploy"},
        ]
    }
    with patch.object(client, "get_timeline", return_value=timeline):
        result = client.get_pending_authorizations(42)
    assert len(result) == 1
    assert result[0]["stage"] == "Deploy"
    assert result[0]["id"] == auth_id


def test_get_pending_authorizations_empty_when_none_blocked(client):
    timeline = {
        "records": [
            {"id": "s1", "type": "Stage", "state": "completed", "parentId": None, "name": "Build"},
        ]
    }
    with patch.object(client, "get_timeline", return_value=timeline):
        result = client.get_pending_authorizations(42)
    assert result == []


def test_get_pending_authorizations_returns_empty_on_error(client):
    with patch.object(client, "get_timeline", side_effect=Exception("network error")):
        result = client.get_pending_authorizations(42)
    assert result == []
