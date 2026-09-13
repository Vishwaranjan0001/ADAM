"""Tests for Phase 05 memory CLI commands."""

import json
from click.testing import CliRunner

from adam.cli import cli
from adam.db.session import get_session
from adam.memory.session import SessionManager


def test_cli_memory_session_lifecycle(cli_runner: CliRunner):
    """Test memory CLI session commands: list-sessions, show-session, delete-session, purge-expired."""
    runner = cli_runner
    session = get_session()
    manager = SessionManager(session)

    # 1. Create a session with turns
    sess = manager.create_session(user_id="cli_officer_1")
    manager.add_turn(
        session_id=sess.id,
        user_id="cli_officer_1",
        role="user",
        content="What is the pension revision date?",
    )
    manager.add_turn(
        session_id=sess.id,
        user_id="cli_officer_1",
        role="assistant",
        content="Pension revision effective from 01/01/2023.",
        cited_chunk_ids=["chk_pen_001"],
    )
    session.close()

    # 2. list-sessions
    res_list = runner.invoke(cli, ["memory", "list-sessions"])
    assert res_list.exit_code == 0
    assert sess.id in res_list.output
    assert "cli_officer_1" in res_list.output

    # 3. show-session with authorized user
    res_show = runner.invoke(cli, ["memory", "show-session", sess.id, "--user-id", "cli_officer_1"])
    assert res_show.exit_code == 0
    assert "pension revision date" in res_show.output
    assert "chk_pen_001" in res_show.output

    # 4. show-session with unauthorized user is blocked
    res_show_denied = runner.invoke(cli, ["memory", "show-session", sess.id, "--user-id", "attacker_user"])
    assert res_show_denied.exit_code != 0
    assert "Access denied" in res_show_denied.output

    # 5. delete-session
    res_del = runner.invoke(cli, ["memory", "delete-session", sess.id, "--user-id", "cli_officer_1"])
    assert res_del.exit_code == 0
    assert "successfully deleted" in res_del.output

    # 6. purge-expired
    res_purge = runner.invoke(cli, ["memory", "purge-expired"])
    assert res_purge.exit_code == 0
    assert "Purge complete" in res_purge.output


def test_cli_memory_preferences_lifecycle(cli_runner: CliRunner):
    """Test memory CLI preference commands: set-preference, get-preference, delete-preference."""
    runner = cli_runner

    # 1. set-preference without opt-in fails
    res_no_opt = runner.invoke(
        cli,
        [
            "memory",
            "set-preference",
            "user_pref_cli",
            "--purpose",
            "Display format",
            "--data",
            json.dumps({"lang": "hi"}),
            "--no-opt-in",
        ],
    )
    assert res_no_opt.exit_code != 0
    assert "opt-in consent" in res_no_opt.output

    # 2. set-preference with opt-in succeeds
    res_opt = runner.invoke(
        cli,
        [
            "memory",
            "set-preference",
            "user_pref_cli",
            "--purpose",
            "Display language and table density",
            "--data",
            json.dumps({"lang": "hi", "dense": True}),
            "--opt-in",
        ],
    )
    assert res_opt.exit_code == 0
    assert "successfully stored" in res_opt.output

    # 3. get-preference
    res_get = runner.invoke(cli, ["memory", "get-preference", "user_pref_cli"])
    assert res_get.exit_code == 0
    parsed = json.loads(res_get.output)
    assert parsed["lang"] == "hi"
    assert parsed["dense"] is True

    # 4. delete-preference
    res_del = runner.invoke(cli, ["memory", "delete-preference", "user_pref_cli"])
    assert res_del.exit_code == 0
    assert "permanently deleted" in res_del.output

    # 5. verify gone
    res_get_after = runner.invoke(cli, ["memory", "get-preference", "user_pref_cli"])
    assert "No active or opted-in preferences found" in res_get_after.output
