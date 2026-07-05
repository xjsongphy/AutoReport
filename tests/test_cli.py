"""Tests for typer CLI interface."""

from unittest.mock import patch

from autoreport.app import app


class TestCLIOptions:
    """CLI argument parsing via typer."""

    def test_help_option(self):
        """--help should show usage and exit 0."""
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "AutoReport" in result.output

    def test_unknown_option(self):
        """Unknown options should produce an error."""
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(app, ["--nonexistent"])
        assert result.exit_code != 0
        assert "No such option" in result.output


class TestCLISyncPresets:
    """--sync-presets command behavior."""

    def test_sync_success(self):
        """Successful sync should print message and exit 0."""
        from typer.testing import CliRunner

        runner = CliRunner()
        with patch("autoreport.app._try_sync_presets", return_value=True):
            with patch("autoreport.app.setup_logging"):
                with patch("autoreport.config.presets.load_presets", return_value=["p1", "p2"]):
                    result = runner.invoke(app, ["--sync-presets"])
                    assert result.exit_code == 0
                    assert "2 presets" in result.output

    def test_sync_failure(self):
        """Failed sync should exit 1."""
        from typer.testing import CliRunner

        runner = CliRunner()
        with patch("autoreport.app._try_sync_presets", return_value=False):
            with patch("autoreport.app.setup_logging"):
                result = runner.invoke(app, ["--sync-presets"])
                assert result.exit_code == 1

    def test_sync_presets_flag_parsed(self):
        """--sync-presets should be recognized as a valid option."""
        from typer.testing import CliRunner

        runner = CliRunner()
        with patch("autoreport.app._try_sync_presets", return_value=True):
            with patch("autoreport.app.setup_logging"):
                with patch("autoreport.config.presets.load_presets", return_value=[]):
                    result = runner.invoke(app, ["--sync-presets"])
                    assert "No such option" not in result.output

    def test_verbose_flag_parsed(self):
        """--verbose / -v should not produce 'unknown option' error."""
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert "--verbose" in result.output

    def test_debug_agent_flag_parsed(self):
        """--debug-agent should appear in help output."""
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert "--debug-agent" in result.output
