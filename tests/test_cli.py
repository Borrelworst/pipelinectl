from click.testing import CliRunner
from pipelinectl.cli import cli


def test_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "trigger" in result.output.lower()


def test_run_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--help"])
    assert result.exit_code == 0
    assert "--branch" in result.output
    assert "--logs" in result.output
    assert "--param" in result.output


def test_list_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["list", "--help"])
    assert result.exit_code == 0


def test_status_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["status", "--help"])
    assert result.exit_code == 0


def test_logs_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["logs", "--help"])
    assert result.exit_code == 0


def test_params_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["params", "--help"])
    assert result.exit_code == 0
