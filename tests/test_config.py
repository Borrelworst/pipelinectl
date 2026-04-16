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


def test_validate_ado_missing_fields(capsys):
    cfg = Config({})
    with pytest.raises(SystemExit):
        cfg.validate_ado()
    captured = capsys.readouterr()
    assert "organization" in captured.err
