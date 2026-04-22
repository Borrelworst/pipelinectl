import os
import pytest
from unittest.mock import patch
from pipelinectl.config import Config


def test_pat_from_env_takes_precedence():
    cfg = Config({"azure_devops": {"pat": "from_file"}})
    with patch.dict(os.environ, {"ADO_PAT": "from_env"}):
        assert cfg.ado_pat == "from_env"


def test_pat_from_config_when_no_env():
    cfg = Config({"azure_devops": {"pat": "from_file"}})
    env = {k: v for k, v in os.environ.items() if k != "ADO_PAT"}
    with patch.dict(os.environ, env, clear=True):
        assert cfg.ado_pat == "from_file"


def test_default_branch_fallback():
    cfg = Config({})
    assert cfg.ado_default_branch == "main"


def test_default_auth_method():
    assert Config({}).auth_method == "pat"
    assert Config({"azure_devops": {"auth": "azcli"}}).auth_method == "azcli"


def test_validate_ado_missing_fields(capsys):
    cfg = Config({})
    with pytest.raises(SystemExit):
        cfg.validate_ado()
    captured = capsys.readouterr()
    assert "organization" in captured.err


def test_validate_ado_azcli_does_not_require_pat(capsys):
    cfg = Config({"azure_devops": {
        "organization": "myorg",
        "project": "myproject",
        "auth": "azcli",
    }})
    cfg.validate_ado()  # should not raise


def test_update_ado_sets_and_removes_keys(tmp_path, monkeypatch):
    from pipelinectl import config as cfg_module
    monkeypatch.setattr(cfg_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg_module, "CONFIG_FILE", tmp_path / "config.toml")

    cfg = Config({"azure_devops": {"organization": "myorg", "pat": "oldpat"}})
    cfg.update_ado(pat=None, auth="azcli")

    assert cfg._data["azure_devops"].get("pat") is None
    assert cfg._data["azure_devops"]["auth"] == "azcli"
