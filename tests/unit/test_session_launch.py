"""Building the command that starts a paired agent session."""
import os

import pytest

from claudlet.core import session_launch as S


def test_a_new_id_is_a_uuid():
    sid = S.new_session_id()
    assert len(sid) == 36 and sid.count("-") == 4


def test_ids_do_not_repeat():
    assert len({S.new_session_id() for _ in range(50)}) == 50


def test_the_command_carries_the_session_id():
    cmd = S.build_command("abc-123", "/tmp")
    assert "--session-id 'abc-123'" in cmd


def test_the_command_starts_in_the_right_directory():
    assert S.build_command("x", "/tmp/work").startswith("cd '/tmp/work' &&")


def test_a_directory_with_spaces_stays_one_argument():
    assert "cd '/tmp/my work' &&" in S.build_command("x", "/tmp/my work")


def test_a_quote_in_the_path_cannot_break_out():
    cmd = S.build_command("x", "/tmp/it's here")
    assert "'/tmp/it'\\''s here'" in cmd


def test_no_cd_when_no_directory_is_given():
    assert not S.build_command("x").startswith("cd ")


def test_the_agent_binary_is_configurable():
    assert "'codex'" in S.build_command("x", None, "codex", session_flag="--sid")


def test_an_agent_without_the_flag_gets_a_plain_command():
    """A wrong flag opens a terminal that just errors; emit none instead."""
    cmd = S.build_command("x", "/tmp", "codex", session_flag=None)
    assert "--session-id" not in cmd
    assert "'codex'" in cmd


def test_extra_arguments_are_appended():
    assert S.build_command("x", None, "claude", extra=["--verbose"]).endswith("--verbose")


def test_quoting_is_reversible_by_a_shell():
    import subprocess
    weird = "it's a \"test\" $HOME"
    out = subprocess.run(["bash", "-c", "printf %s " + S.shell_quote(weird)],
                         capture_output=True, text=True)
    assert out.stdout == weird


def test_an_existing_directory_is_kept():
    assert S.resolve_cwd("/tmp") == "/tmp"


def test_a_missing_directory_falls_back():
    assert S.resolve_cwd("/no/such/place/here") == os.getcwd()


def test_no_directory_means_the_current_one():
    assert S.resolve_cwd(None) == os.getcwd()
