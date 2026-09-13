"""Integration tests for Phase 04 CLI commands: adam model and adam agent."""

import pytest
from click.testing import CliRunner
from adam.cli import cli
from adam.model.registry import QWEN3_4B_INSTRUCT


def test_cli_model_list():
    """Verify 'adam model list' outputs registered canonical models."""
    runner = CliRunner()
    result = runner.invoke(cli, ["model", "list"])
    assert result.exit_code == 0
    assert "qwen3-4b-instruct-q4" in result.output
    assert "qwen3-1.7b-instruct-q4" in result.output
    assert "Apache-2.0" in result.output
    assert "PRIMARY" in result.output


def test_cli_model_info():
    """Verify 'adam model info' outputs SBOM, checksum, and licensing."""
    runner = CliRunner()
    result = runner.invoke(cli, ["model", "info", QWEN3_4B_INSTRUCT.id])
    assert result.exit_code == 0
    assert "Qwen/Qwen3-4B-Instruct" in result.output
    assert "SHA-256 Hash:" in result.output
    assert "Software Bill of Materials (SBOM):" in result.output
    assert "Apache-2.0" in result.output


def test_cli_model_budget():
    """Verify 'adam model budget' displays environment budgets and cache ceilings."""
    runner = CliRunner()
    result = runner.invoke(cli, ["model", "budget", "--profile", "MACBOOK_AIR_8GB"])
    assert result.exit_code == 0
    assert "MACBOOK_AIR_8GB" in result.output
    assert "macOS Headroom Reserved:     2.0 GB" in result.output
    assert "Total Disk Cache Ceiling:  10.0 GB" in result.output
    assert "Worker Mutual Exclusion:     ENFORCED" in result.output


def test_cli_model_promote():
    """Verify 'adam model promote' runs gate evaluation and reports outcome."""
    runner = CliRunner()
    result = runner.invoke(cli, [
        "model", "promote", QWEN3_4B_INSTRUCT.id,
        "--promoted-by", "records_officer_test",
        "--authority-ref", "GO/2024/TEST-PROM-01",
        "--fast",
    ])
    assert result.exit_code == 0
    assert "ADAM MODEL PROMOTION SCORECARD:" in result.output
    assert "PROMOTION GATE DECISION:           PROMOTED" in result.output


def test_cli_agent_query():
    """Verify 'adam agent query' executes bounded pipeline with citations and transitions."""
    runner = CliRunner()
    result = runner.invoke(cli, [
        "agent", "query",
        "What are the rules regarding Treasury Single Account?",
        "--verbose",
    ])
    assert result.exit_code == 0
    assert "STATE MACHINE TRANSITIONS" in result.output
    assert "ANSWER:" in result.output


def test_cli_agent_test_guardrails():
    """Verify 'adam agent test-guardrails' tests whitelist and forbidden tool interception."""
    runner = CliRunner()
    result = runner.invoke(cli, ["agent", "test-guardrails"])
    assert result.exit_code == 0
    assert "web_browse" in result.output
    assert "100% compliant" in result.output
