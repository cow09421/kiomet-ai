"""協作路徑認領必須涵蓋資料夾、檔案和 glob pattern。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_coordination import coord
from agent_coordination.coord import normalize_pattern, patterns_overlap


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("tests/", "tests/test_a.py"),
        ("src/kiomet_ai", "src/kiomet_ai/pvp_live.py"),
        ("tests/*.py", "tests/test_a.py"),
        ("src/*/pvp.py", "src/kiomet_ai/pvp.py"),
        ("agent_coordination/", "agent_coordination/inbox/MUSE/1.md"),
    ],
)
def test_overlapping_path_patterns_are_detected(left, right):
    assert patterns_overlap(left, right)
    assert patterns_overlap(right, left)


def test_disjoint_paths_remain_claimable_in_parallel():
    assert not patterns_overlap("tests/test_a.py", "tests/test_b.py")
    assert not patterns_overlap("src/kiomet_ai/a.py", "tests/test_a.py")


@pytest.mark.parametrize("path", ["../outside.py", "/absolute/file.py", "C:/outside.py"])
def test_path_claims_cannot_escape_project_root(path):
    with pytest.raises(ValueError):
        normalize_pattern(path)


def test_released_paths_can_be_claimed_again(monkeypatch, tmp_path, capsys):
    con = coord.connect(tmp_path / "coord.db")
    coord.add_task(
        con, task_id="RECLAIM", title="reclaim", description="test",
        priority=1, category="TEST", paths=["tests/test_reclaim.py"],
        parallel_safe=True)
    stamp = coord.now()
    con.execute(
        "INSERT INTO heartbeats(agent,current_task,phase,updated_at,note) "
        "VALUES('GPT',NULL,'IDLE',?,'')", (stamp,))
    con.execute(
        "INSERT INTO path_claims(task_id,agent,path_pattern,claimed_at,"
        "heartbeat_at,state) VALUES(?,?,?,?,?,'RELEASED')",
        ("RECLAIM", "GPT", "tests/test_reclaim.py", stamp, stamp))
    monkeypatch.setattr(coord, "write_status", lambda *_args: None)
    monkeypatch.setattr(coord, "render_board", lambda *_args: "")

    assert coord.cmd_claim(con, "RECLAIM", "GPT") == 0
    capsys.readouterr()
    claims = con.execute(
        "SELECT state FROM path_claims WHERE task_id='RECLAIM' "
        "AND agent='GPT'").fetchall()
    assert [row["state"] for row in claims] == ["ACTIVE"]
    claimed = con.execute(
        "SELECT status,primary_agent FROM tasks WHERE id='RECLAIM'").fetchone()
    assert (claimed["status"], claimed["primary_agent"]) == ("CLAIMED", "GPT")

    coord.cmd_release(con, "RECLAIM", "GPT")
    capsys.readouterr()
    assert coord.cmd_claim(con, "RECLAIM", "GPT") == 0
    capsys.readouterr()
    claims = con.execute(
        "SELECT state FROM path_claims WHERE task_id='RECLAIM' "
        "AND agent='GPT'").fetchall()
    assert [row["state"] for row in claims] == ["ACTIVE"]
    assert con.execute(
        "SELECT COUNT(*) FROM path_claims WHERE task_id='RECLAIM' "
        "AND agent='GPT'").fetchone()[0] == 1
    con.close()
