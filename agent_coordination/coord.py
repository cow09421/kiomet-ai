#!/usr/bin/env python3
"""Kiomet peer-agent coordination; stdlib only, SQLite is authoritative."""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import textwrap

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "coord.db"
AGENTS = {"GPT", "MUSE"}
STATUSES = {"READY", "CLAIMED", "IN_PROGRESS", "REVIEW", "BLOCKED", "ESCALATED", "DONE"}
MODES = {"SINGLE", "REVIEW", "RACE"}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path, timeout=10, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=5000")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript("""
      CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
        milestone TEXT NOT NULL, priority INTEGER NOT NULL CHECK(priority BETWEEN 0 AND 3),
        status TEXT NOT NULL CHECK(status IN ('READY','CLAIMED','IN_PROGRESS','REVIEW','BLOCKED','ESCALATED','DONE')),
        primary_agent TEXT, reviewer_agent TEXT,
        mode TEXT NOT NULL CHECK(mode IN ('SINGLE','REVIEW','RACE')),
        category TEXT NOT NULL, runtime_required INTEGER NOT NULL DEFAULT 0,
        parallel_safe INTEGER NOT NULL DEFAULT 0, created_by TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        depends_on TEXT NOT NULL DEFAULT '[]', result_summary TEXT NOT NULL DEFAULT '',
        path_patterns TEXT NOT NULL DEFAULT '[]'
      );
      CREATE TABLE IF NOT EXISTS path_claims (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL REFERENCES tasks(id), agent TEXT NOT NULL,
        path_pattern TEXT NOT NULL, claimed_at TEXT NOT NULL,
        heartbeat_at TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('ACTIVE','RELEASED')),
        UNIQUE(task_id, agent, path_pattern)
      );
      CREATE INDEX IF NOT EXISTS idx_path_claims_active ON path_claims(state, agent);
      CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_agent TEXT NOT NULL, to_agent TEXT NOT NULL, priority TEXT NOT NULL,
        task_id TEXT, subject TEXT NOT NULL, body TEXT NOT NULL,
        created_at TEXT NOT NULL, acked_at TEXT
      );
      CREATE TABLE IF NOT EXISTS heartbeats (
        agent TEXT PRIMARY KEY, current_task TEXT, phase TEXT NOT NULL,
        updated_at TEXT NOT NULL, note TEXT NOT NULL DEFAULT ''
      );
      CREATE TABLE IF NOT EXISTS decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, decision_key TEXT NOT NULL UNIQUE,
        decision TEXT NOT NULL, rationale TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ACTIVE',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
      );
    """)
    return con


def require_agent(agent: str) -> str:
    agent = agent.upper()
    if agent not in AGENTS:
        raise ValueError(f"unknown agent: {agent}; expected GPT or MUSE")
    return agent


def normalize_pattern(pattern: str) -> str:
    value = pattern.strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    if not value or value.startswith("/") or re.match(r"^[a-zA-Z]:", value):
        raise ValueError(f"path must be relative to the project: {pattern!r}")
    parts = value.rstrip("/").split("/")
    if any(part in ("", "..") for part in parts):
        raise ValueError(f"invalid relative path pattern: {pattern!r}")
    return value.rstrip("/").casefold()


def _pattern_prefix(pattern: str) -> str:
    positions = [pattern.find(ch) for ch in "*?[" if pattern.find(ch) >= 0]
    prefix = pattern[:min(positions)] if positions else pattern
    return prefix.rstrip("/")


def patterns_overlap(left: str, right: str) -> bool:
    a, b = normalize_pattern(left), normalize_pattern(right)
    if a == b or fnmatch.fnmatchcase(a, b) or fnmatch.fnmatchcase(b, a):
        return True
    if not any(ch in a for ch in "*?[") and not any(ch in b for ch in "*?["):
        return a.startswith(b + "/") or b.startswith(a + "/")
    pa, pb = _pattern_prefix(a), _pattern_prefix(b)
    # Wildcard overlap is deliberately conservative: a shared literal directory
    # prefix may overlap even when proving glob intersection would be expensive.
    return bool(pa and pb and (pa == pb or pa.startswith(pb + "/") or pb.startswith(pa + "/")))


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(content, encoding="utf-8")
    os.replace(temp, path)


def write_status(agent: str, heartbeat: sqlite3.Row | None) -> None:
    if heartbeat:
        body = (f"# {agent} 狀態\n\n- 階段：{heartbeat['phase']}\n"
                f"- 任務：{heartbeat['current_task'] or '無'}\n"
                f"- 更新時間：{heartbeat['updated_at']}\n"
                f"- 備註：{heartbeat['note'] or '無'}\n")
    else:
        body = f"# {agent} 狀態\n\n尚未收到此代理的協作區心跳。\n"
    _atomic_write(ROOT / "status" / f"{agent}.md", body)


def add_task(con: sqlite3.Connection, *, task_id: str, title: str, description: str,
             priority: int, category: str, paths: list[str], parallel_safe: bool,
             runtime_required: bool = False, mode: str = "SINGLE",
             reviewer: str | None = None, created_by: str = "GPT",
             status: str = "READY", depends_on: list[str] | None = None) -> None:
    for path in paths:
        normalize_pattern(path)
    timestamp = now()
    con.execute("""INSERT OR IGNORE INTO tasks
      (id,title,description,milestone,priority,status,primary_agent,reviewer_agent,mode,
       category,runtime_required,parallel_safe,created_by,created_at,updated_at,depends_on,
       result_summary,path_patterns)
      VALUES(?,?,?,'AUTONOMOUS_PVP_V0',?,?,NULL,?,?,?,?,?,?,?,?,?,'',?)""",
      (task_id, title, description, priority, status, reviewer, mode, category,
       int(runtime_required), int(parallel_safe), created_by, timestamp, timestamp,
       json.dumps(depends_on or []), json.dumps(paths)))


def seed(con: sqlite3.Connection) -> None:
    con.execute("BEGIN IMMEDIATE")
    try:
        add_task(con, task_id="PVP-RT11-TESTS", priority=1,
                 title="補強 Round 11 多威脅安全迴歸測試",
                 description=("把正式 evaluator（評估器）的第二波威脅、未知 ETA、特殊單位與來源安全結果，"
                              "寫成精確且可重現的 regression tests（迴歸測試）；只新增 tests/test_round11_regression.py。"),
                 category="TESTS", paths=["tests/test_round11_regression.py"],
                 parallel_safe=True, created_by="GPT")
        add_task(con, task_id="PVP-RUNTIME-VALIDATION", priority=0,
                 title="PvP v0 執行期整合驗證",
                 description=("依 Round 11 驗證計畫確認 Runtime（執行期）中的整合證據、派兵後驗證與重新規劃。"
                              "此工作可能需要正在運行的遊戲，需先確認可用的唯讀證據；本次不把它當成 GPT 的平行安全任務。"),
                 category="RUNTIME_VALIDATION", paths=[], parallel_safe=False,
                 runtime_required=True, created_by="GPT")
        decisions = [
          ("unknown-never-zero", "UNKNOWN 永遠不能轉成 0", "Round 11 安全閘門與 PvP 合約；未知資料必須棄權。"),
          ("same-tick-unsupported", "未經 Runtime 驗證的同節拍援軍必須棄權", "Round 11 temporal contract；到達順序尚未驗證。"),
          ("special-units-disabled", "PvP v0 禁用特殊單位", "v0 evaluator（評估器）支援範圍限制。"),
          ("official-ui-events-only", "正式遊戲操作只走官方 UI 事件路徑", "保持既有遊戲控制安全邊界。"),
          ("verify-before-next-dispatch", "驗證上一個動作後才能送出下一個派兵動作", "防止重複派兵、過期提案與雙重花費。"),
        ]
        for key, decision, rationale in decisions:
            stamp = now()
            con.execute("INSERT OR IGNORE INTO decisions(decision_key,decision,rationale,status,created_at,updated_at) VALUES(?,?,?,'ACTIVE',?,?)",
                        (key, decision, rationale, stamp, stamp))
        for agent, phase, note in [
          ("GPT", "IDLE", "協作啟動；等待原子認領工作。"),
          ("MUSE", "UNKNOWN", "使用者提供的目前方向是 PvP v0 Runtime Integration；Git 檢查未見 dirty paths，仍待 MUSE 回報。"),
        ]:
            con.execute("INSERT OR IGNORE INTO heartbeats(agent,current_task,phase,updated_at,note) VALUES(?,NULL,?,?,?)",
                        (agent, phase, now(), note))
        con.commit()
    except Exception:
        con.rollback()
        raise


def _task_rows(con: sqlite3.Connection, where: str = "1=1") -> list[sqlite3.Row]:
    return con.execute(f"SELECT * FROM tasks WHERE {where} ORDER BY priority,id").fetchall()


def render_board(con: sqlite3.Connection) -> str:
    tasks = _task_rows(con)
    heartbeats = {r["agent"]: r for r in con.execute("SELECT * FROM heartbeats")}
    messages = con.execute("SELECT * FROM messages ORDER BY id DESC LIMIT 10").fetchall()
    lines = ["# Kiomet Agent 協作看板", "", "- 目前里程碑：`AUTONOMOUS_PVP_V0`", "",
             "## Agent 狀態", ""]
    for agent in sorted(AGENTS):
        hb = heartbeats.get(agent)
        if hb:
            lines.append(f"- **{agent}**：{hb['phase']}；任務 `{hb['current_task'] or '無'}`；{hb['note'] or '無備註'}（{hb['updated_at']}）")
        else:
            lines.append(f"- **{agent}**：尚無心跳")
    lines.extend(["", "## 任務", "", "| ID | 優先級 | 狀態 | Agent | 平行安全 | 執行期 | 任務 | 路徑 |",
                  "|---|---:|---|---|---|---|---|---|"])
    for task in tasks:
        paths = ", ".join(json.loads(task["path_patterns"])) or "（無寫入路徑）"
        lines.append(f"| `{task['id']}` | P{task['priority']} | {task['status']} | {task['primary_agent'] or '—'} | {bool(task['parallel_safe'])} | {bool(task['runtime_required'])} | {task['title']} | `{paths}` |")
    lines.extend(["", "## 最近 Agent 訊息", ""])
    if not messages:
        lines.append("- 尚無訊息。")
    for msg in messages:
        lines.append(f"- #{msg['id']} **{msg['from_agent']} → {msg['to_agent']}** [{msg['priority']}] {msg['subject']}（{msg['created_at']}）：{msg['body']}")
    lines.extend(["", "## 協作規則", "", "SQLite `coord.db` 為權威狀態；任務與路徑認領都透過交易式 `coord.py` 更新。看到未認領的外部修改時，先當成 `FOREIGN_ACTIVE`，不得覆蓋。", ""])
    board = "\n".join(lines)
    _atomic_write(ROOT / "BOARD.md", board)
    return board


def cmd_bootstrap(con: sqlite3.Connection) -> None:
    for name in ("status", "inbox/GPT", "inbox/MUSE", "results", "decisions", "escalations", "snapshots"):
        (ROOT / name).mkdir(parents=True, exist_ok=True)
    seed(con)
    for agent in sorted(AGENTS):
        write_status(agent, con.execute("SELECT * FROM heartbeats WHERE agent=?", (agent,)).fetchone())
    render_board(con)
    print(f"COORDINATION_READY: {ROOT}")


def cmd_claim(con: sqlite3.Connection, task_id: str, agent: str) -> int:
    agent = require_agent(agent)
    con.execute("BEGIN IMMEDIATE")
    try:
        task = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if task is None:
            con.rollback()
            print("TASK_NOT_FOUND")
            return 2
        if task["status"] != "READY" or task["primary_agent"]:
            con.rollback()
            print(f"ALREADY_CLAIMED: status={task['status']} agent={task['primary_agent'] or 'unknown'}")
            return 3
        paths = json.loads(task["path_patterns"])
        active = con.execute("SELECT task_id,agent,path_pattern FROM path_claims WHERE state='ACTIVE' AND agent<>?", (agent,)).fetchall()
        collisions = [(r["task_id"], r["agent"], r["path_pattern"], requested)
                      for r in active for requested in paths
                      if patterns_overlap(r["path_pattern"], requested)]
        if collisions:
            con.rollback()
            print("PATH_CONFLICT: " + json.dumps(collisions, ensure_ascii=False))
            return 4
        stamp = now()
        con.execute("UPDATE tasks SET status='CLAIMED',primary_agent=?,updated_at=? WHERE id=?",
                    (agent, stamp, task_id))
        for pattern in paths:
            con.execute("""INSERT INTO path_claims
              (task_id,agent,path_pattern,claimed_at,heartbeat_at,state)
              VALUES(?,?,?,?,?,'ACTIVE')
              ON CONFLICT(task_id,agent,path_pattern) DO UPDATE SET
                claimed_at=excluded.claimed_at,
                heartbeat_at=excluded.heartbeat_at,
                state='ACTIVE'""",
              (task_id, agent, normalize_pattern(pattern), stamp, stamp))
        con.execute("UPDATE heartbeats SET current_task=?,phase='CLAIMED',updated_at=?,note=? WHERE agent=?",
                    (task_id, stamp, task["title"], agent))
        con.commit()
    except Exception:
        con.rollback()
        raise
    write_status(agent, con.execute("SELECT * FROM heartbeats WHERE agent=?", (agent,)).fetchone())
    render_board(con)
    print(f"CLAIMED: {task_id} by {agent}; paths={json.dumps(paths, ensure_ascii=False)}")
    return 0


def _owned_task(con: sqlite3.Connection, task_id: str, agent: str) -> sqlite3.Row:
    task = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if task is None:
        raise ValueError(f"TASK_NOT_FOUND: {task_id}")
    if task["primary_agent"] != agent:
        raise ValueError(f"NOT_TASK_OWNER: {task_id} belongs to {task['primary_agent'] or 'nobody'}")
    return task


def cmd_start(con: sqlite3.Connection, task_id: str, agent: str) -> None:
    agent = require_agent(agent)
    con.execute("BEGIN IMMEDIATE")
    try:
        task = _owned_task(con, task_id, agent)
        if task["status"] not in ("CLAIMED", "IN_PROGRESS"):
            raise ValueError(f"CANNOT_START_FROM: {task['status']}")
        stamp = now()
        con.execute("UPDATE tasks SET status='IN_PROGRESS',updated_at=? WHERE id=?", (stamp, task_id))
        con.execute("UPDATE path_claims SET heartbeat_at=? WHERE task_id=? AND agent=? AND state='ACTIVE'", (stamp, task_id, agent))
        con.execute("UPDATE heartbeats SET current_task=?,phase='IN_PROGRESS',updated_at=?,note=? WHERE agent=?",
                    (task_id, stamp, task["title"], agent))
        con.commit()
    except Exception:
        con.rollback()
        raise
    write_status(agent, con.execute("SELECT * FROM heartbeats WHERE agent=?", (agent,)).fetchone())
    render_board(con)
    print(f"IN_PROGRESS: {task_id}")


def cmd_heartbeat(con: sqlite3.Connection, agent: str, phase: str | None, note: str | None,
                  task_id: str | None = None) -> None:
    agent = require_agent(agent)
    current = con.execute("SELECT * FROM heartbeats WHERE agent=?", (agent,)).fetchone()
    task_id = task_id if task_id is not None else (current["current_task"] if current else None)
    if task_id:
        task = con.execute("SELECT * FROM tasks WHERE id=? AND primary_agent=?", (task_id, agent)).fetchone()
        if not task:
            raise ValueError(f"NOT_TASK_OWNER: {task_id}")
    new_phase = phase or (current["phase"] if current else "WORKING")
    new_note = note if note is not None else (current["note"] if current else "")
    stamp = now()
    con.execute("BEGIN IMMEDIATE")
    try:
        con.execute("INSERT INTO heartbeats(agent,current_task,phase,updated_at,note) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(agent) DO UPDATE SET current_task=excluded.current_task,phase=excluded.phase,updated_at=excluded.updated_at,note=excluded.note",
                    (agent, task_id, new_phase, stamp, new_note))
        if task_id:
            con.execute("UPDATE path_claims SET heartbeat_at=? WHERE task_id=? AND agent=? AND state='ACTIVE'",
                        (stamp, task_id, agent))
        con.commit()
    except Exception:
        con.rollback()
        raise
    write_status(agent, con.execute("SELECT * FROM heartbeats WHERE agent=?", (agent,)).fetchone())
    render_board(con)
    print(f"HEARTBEAT: {agent} {new_phase} task={task_id or 'none'}")


def cmd_done(con: sqlite3.Connection, task_id: str, agent: str, summary: str) -> None:
    agent = require_agent(agent)
    con.execute("BEGIN IMMEDIATE")
    try:
        task = _owned_task(con, task_id, agent)
        final_status = "REVIEW" if task["mode"] == "REVIEW" and task["reviewer_agent"] else "DONE"
        stamp = now()
        con.execute("UPDATE tasks SET status=?,result_summary=?,updated_at=? WHERE id=?",
                    (final_status, summary, stamp, task_id))
        con.execute("UPDATE path_claims SET state='RELEASED',heartbeat_at=? WHERE task_id=? AND agent=? AND state='ACTIVE'",
                    (stamp, task_id, agent))
        con.execute("UPDATE heartbeats SET current_task=NULL,phase=?,updated_at=?,note=? WHERE agent=?",
                    (final_status, stamp, f"{task_id}: {summary}", agent))
        con.commit()
    except Exception:
        con.rollback()
        raise
    write_status(agent, con.execute("SELECT * FROM heartbeats WHERE agent=?", (agent,)).fetchone())
    render_board(con)
    print(f"{final_status}: {task_id}")


def cmd_block(con: sqlite3.Connection, task_id: str, agent: str, reason: str, status: str = "BLOCKED") -> None:
    agent = require_agent(agent)
    con.execute("BEGIN IMMEDIATE")
    try:
        task = _owned_task(con, task_id, agent)
        stamp = now()
        con.execute("UPDATE tasks SET status=?,result_summary=?,updated_at=? WHERE id=?",
                    (status, reason, stamp, task_id))
        con.execute("UPDATE heartbeats SET current_task=?,phase=?,updated_at=?,note=? WHERE agent=?",
                    (task_id, status, stamp, reason, agent))
        con.commit()
    except Exception:
        con.rollback()
        raise
    write_status(agent, con.execute("SELECT * FROM heartbeats WHERE agent=?", (agent,)).fetchone())
    render_board(con)
    print(f"{status}: {task_id}")


def cmd_release(con: sqlite3.Connection, task_id: str, agent: str) -> None:
    agent = require_agent(agent)
    con.execute("BEGIN IMMEDIATE")
    try:
        task = _owned_task(con, task_id, agent)
        if task["status"] == "DONE":
            raise ValueError("CANNOT_RELEASE_DONE_TASK")
        stamp = now()
        con.execute("UPDATE path_claims SET state='RELEASED',heartbeat_at=? WHERE task_id=? AND agent=? AND state='ACTIVE'",
                    (stamp, task_id, agent))
        con.execute("UPDATE tasks SET status='READY',primary_agent=NULL,result_summary=?,updated_at=? WHERE id=?",
                    (f"先前工作代理已釋放認領（{task['status']}）。未完成工作需重新核對。", stamp, task_id))
        con.execute("UPDATE heartbeats SET current_task=NULL,phase='IDLE',updated_at=?,note=? WHERE agent=?",
                    (stamp, f"已釋放 {task_id}", agent))
        con.commit()
    except Exception:
        con.rollback()
        raise
    write_status(agent, con.execute("SELECT * FROM heartbeats WHERE agent=?", (agent,)).fetchone())
    render_board(con)
    print(f"RELEASED: {task_id}; status=READY")


def cmd_message(con: sqlite3.Connection, from_agent: str, to_agent: str,
                priority: str, subject: str, body: str, task_id: str | None = None) -> None:
    from_agent, to_agent = require_agent(from_agent), require_agent(to_agent)
    if priority.upper() not in {"P0", "P1", "P2", "P3", "INFO"}:
        raise ValueError("priority must be P0/P1/P2/P3/INFO")
    stamp = now()
    cur = con.execute("INSERT INTO messages(from_agent,to_agent,priority,task_id,subject,body,created_at) VALUES(?,?,?,?,?,?,?)",
                      (from_agent, to_agent, priority.upper(), task_id, subject, body, stamp))
    msg_id = cur.lastrowid
    inbox = ROOT / "inbox" / to_agent / f"{msg_id:06d}.md"
    _atomic_write(inbox, f"# {subject}\n\n- ID：{msg_id}\n- From：{from_agent}\n- Priority：{priority.upper()}\n- Task：{task_id or '無'}\n- Created：{stamp}\n\n{body}\n")
    render_board(con)
    print(f"MESSAGE_SENT: #{msg_id} {from_agent}->{to_agent}")


def cmd_inbox(con: sqlite3.Connection, agent: str, show_all: bool = False) -> None:
    agent = require_agent(agent)
    where = "to_agent=?" if show_all else "to_agent=? AND acked_at IS NULL"
    rows = con.execute(f"SELECT * FROM messages WHERE {where} ORDER BY id", (agent,)).fetchall()
    if not rows:
        print(f"INBOX {agent}: empty")
        return
    for row in rows:
        print(f"#{row['id']} [{row['priority']}] {row['from_agent']} → {agent}: {row['subject']} (task={row['task_id'] or 'none'})\n{row['body']}\n")
    if not show_all:
        con.execute("UPDATE messages SET acked_at=? WHERE to_agent=? AND acked_at IS NULL", (now(), agent))


def cmd_snapshot(con: sqlite3.Connection, db_path: Path) -> None:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "snapshots"
    out.mkdir(parents=True, exist_ok=True)
    db_copy = out / f"coord-{stamp}.db"
    target = sqlite3.connect(db_copy)
    try:
        con.backup(target)
    finally:
        target.close()
    def git(args: list[str]) -> str:
        result = subprocess.run(["git", *args], cwd=ROOT.parent, capture_output=True, text=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else f"unavailable: {result.stderr.strip()}"
    summary = {
      "created_at": now(), "database_snapshot": db_copy.name,
      "branch": git(["branch", "--show-current"]), "head": git(["log", "-1", "--format=%h %ad %s", "--date=iso-strict"]),
      "status_porcelain": git(["status", "--short"]), "diff_name_only": git(["diff", "--name-only"]),
    }
    _atomic_write(out / f"coord-{stamp}.json", json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(f"SNAPSHOT: {db_copy}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kiomet transactional peer-agent coordination")
    parser.add_argument("--db", type=Path, default=DB_PATH, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap")
    sub.add_parser("board")
    sub.add_parser("tasks")
    inbox = sub.add_parser("inbox"); inbox.add_argument("agent"); inbox.add_argument("--all", action="store_true")
    claim = sub.add_parser("claim"); claim.add_argument("task_id"); claim.add_argument("agent")
    start = sub.add_parser("start"); start.add_argument("task_id"); start.add_argument("agent")
    hb = sub.add_parser("heartbeat"); hb.add_argument("agent"); hb.add_argument("--phase"); hb.add_argument("--note"); hb.add_argument("--task")
    done = sub.add_parser("done"); done.add_argument("task_id"); done.add_argument("agent"); done.add_argument("--summary", default="")
    block = sub.add_parser("block"); block.add_argument("task_id"); block.add_argument("agent"); block.add_argument("reason", nargs="+")
    escalate = sub.add_parser("escalate"); escalate.add_argument("task_id"); escalate.add_argument("agent"); escalate.add_argument("reason", nargs="+")
    release = sub.add_parser("release"); release.add_argument("task_id"); release.add_argument("agent")
    message = sub.add_parser("message"); message.add_argument("to_agent"); message.add_argument("priority"); message.add_argument("subject"); message.add_argument("body"); message.add_argument("--from-agent", default="GPT"); message.add_argument("--task")
    add = sub.add_parser("add"); add.add_argument("--id", required=True); add.add_argument("--title", required=True); add.add_argument("--description", required=True); add.add_argument("--priority", type=int, required=True); add.add_argument("--category", default="ENGINEERING"); add.add_argument("--path", action="append", default=[]); add.add_argument("--parallel-safe", action="store_true"); add.add_argument("--runtime-required", action="store_true"); add.add_argument("--mode", choices=sorted(MODES), default="SINGLE"); add.add_argument("--created-by", default="GPT")
    sub.add_parser("snapshot")
    args = parser.parse_args(argv)
    try:
        con = connect(args.db)
        if args.command == "bootstrap": cmd_bootstrap(con)
        elif args.command == "board": print(render_board(con))
        elif args.command == "tasks":
            for row in _task_rows(con):
                print(f"{row['id']} P{row['priority']} {row['status']} agent={row['primary_agent'] or '-'} parallel_safe={bool(row['parallel_safe'])} runtime_required={bool(row['runtime_required'])} paths={row['path_patterns']} :: {row['title']}")
        elif args.command == "inbox": cmd_inbox(con, args.agent, args.all)
        elif args.command == "claim": return cmd_claim(con, args.task_id, args.agent)
        elif args.command == "start": cmd_start(con, args.task_id, args.agent)
        elif args.command == "heartbeat": cmd_heartbeat(con, args.agent, args.phase, args.note, args.task)
        elif args.command == "done": cmd_done(con, args.task_id, args.agent, args.summary)
        elif args.command == "block": cmd_block(con, args.task_id, args.agent, " ".join(args.reason))
        elif args.command == "escalate": cmd_block(con, args.task_id, args.agent, " ".join(args.reason), "ESCALATED")
        elif args.command == "release": cmd_release(con, args.task_id, args.agent)
        elif args.command == "message": cmd_message(con, args.from_agent, args.to_agent, args.priority, args.subject, args.body, args.task)
        elif args.command == "add":
            agent = require_agent(args.created_by)
            con.execute("BEGIN IMMEDIATE")
            try:
                add_task(con, task_id=args.id, title=args.title, description=args.description,
                         priority=args.priority, category=args.category, paths=args.path,
                         parallel_safe=args.parallel_safe, runtime_required=args.runtime_required,
                         mode=args.mode, created_by=agent)
                con.commit()
            except Exception:
                con.rollback(); raise
            render_board(con); print(f"TASK_ADDED: {args.id}")
        elif args.command == "snapshot": cmd_snapshot(con, args.db)
        con.close()
        return 0
    except (ValueError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
