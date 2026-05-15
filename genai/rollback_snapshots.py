"""
rollback_snapshots.py
======================
Pre-execution DB snapshot capture and SQL inverse derivation for database-change
actions. Enables data-safe rollback: before a mutation runs, we capture the
current state and derive the inverse SQL so operators can revert with one click.

Snapshot lifecycle:
  1. `capture_pre_execution_snapshot(command, service, environment)`
     — called in execute_command_view before dispatching a DB-change command
     — parses SQL, runs SELECT snapshot via psql, derives inverse SQL
     — returns a dict stored in ExecutionIntent.rollback_snapshot_json

  2. `build_rollback_command_from_snapshot(snapshot, original_command)`
     — called in rollback_execution_intent_view
     — produces the best available rollback command using the snapshot
     — returns (rollback_command_str, feasibility) where feasibility is
       "exact", "approximate", or "manual"

SQL coverage:
  UPDATE — exact inverse derivable (restore pre-mutation column values)
  DELETE — pre-state captured; inverse INSERT constructed per row
  INSERT — inverse DELETE by primary key (if pk detectable)
  ALTER/DROP/TRUNCATE — snapshot captured; manual rollback required

Non-fatal: all errors are caught; snapshot failure must never block execution.
"""

from __future__ import annotations

import json
import logging
import re
import shlex
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("egap.rollback_snapshots")

_TIMEOUT = 10  # seconds for SELECT snapshot queries


# ---------------------------------------------------------------------------
# SQL parsing utilities
# ---------------------------------------------------------------------------

_UPDATE_RE = re.compile(
    r"^\s*UPDATE\s+(?P<table>\S+)\s+SET\s+(?P<assignments>.+?)\s+WHERE\s+(?P<where>.+)$",
    re.IGNORECASE | re.DOTALL,
)
_DELETE_RE = re.compile(
    r"^\s*DELETE\s+FROM\s+(?P<table>\S+)(?:\s+WHERE\s+(?P<where>.+))?$",
    re.IGNORECASE | re.DOTALL,
)
_INSERT_RE = re.compile(
    r"^\s*INSERT\s+INTO\s+(?P<table>\S+)\s*\((?P<cols>[^)]+)\)\s*VALUES\s*\((?P<vals>[^)]+)\)",
    re.IGNORECASE | re.DOTALL,
)
_PSQL_CMD_RE = re.compile(
    r"psql\b.*?-c\s+['\"](?P<sql>[^'\"]+)['\"]",
    re.IGNORECASE | re.DOTALL,
)
_PSQL_CONN_RE = re.compile(
    r"psql\s+(?P<conn_args>.*?)\s+-c",
    re.IGNORECASE,
)


def _extract_sql(command: str) -> str:
    """Extract bare SQL from a psql -c '...' invocation, or return command as-is."""
    m = _PSQL_CMD_RE.search(command)
    if m:
        return m.group("sql").strip()
    return command.strip()


def _extract_psql_conn_args(command: str) -> List[str]:
    """Extract psql connection arguments for running the snapshot SELECT."""
    try:
        parts = shlex.split(command)
    except ValueError:
        return []
    conn_args: List[str] = []
    skip_next = False
    for i, part in enumerate(parts):
        if skip_next:
            skip_next = False
            continue
        if part == "-c":
            break  # everything after -c is the SQL, not conn args
        if part.startswith("-"):
            conn_args.append(part)
            if part in ("-h", "-p", "-U", "-d", "-W"):
                skip_next = True
                if i + 1 < len(parts):
                    conn_args.append(parts[i + 1])
        elif part.lower().startswith("psql"):
            continue
        else:
            conn_args.append(part)
    return conn_args


def _parse_assignments(assignments_str: str) -> List[Tuple[str, str]]:
    """Parse 'col1 = val1, col2 = val2' into [(col, val), ...]."""
    result: List[Tuple[str, str]] = []
    for part in re.split(r",\s*(?=[a-zA-Z_])", assignments_str):
        if "=" in part:
            col, _, val = part.partition("=")
            result.append((col.strip(), val.strip()))
    return result


def _derive_select_query(sql: str) -> Optional[str]:
    """
    Derive the SELECT query that captures the rows an UPDATE/DELETE will affect.
    Returns None for INSERTs and DDL (no pre-state to capture).
    """
    m = _UPDATE_RE.match(sql)
    if m:
        assignments = _parse_assignments(m.group("assignments"))
        cols = ", ".join(col for col, _ in assignments)
        return f"SELECT {cols} FROM {m.group('table')} WHERE {m.group('where')}"

    m = _DELETE_RE.match(sql)
    if m:
        where_clause = f"WHERE {m.group('where')}" if m.group("where") else ""
        return f"SELECT * FROM {m.group('table')} {where_clause}".strip()

    return None


def _derive_inverse_sql(sql: str, snapshot_rows: List[Dict[str, Any]]) -> Tuple[str, str]:
    """
    Derive inverse SQL statement from original SQL + captured pre-execution rows.
    Returns (inverse_sql, feasibility) where feasibility is "exact", "approximate", or "manual".
    """
    m = _UPDATE_RE.match(sql)
    if m:
        table = m.group("table")
        where = m.group("where")
        if not snapshot_rows:
            return (
                f"-- No rows matched WHERE {where}; no rollback required.",
                "exact",
            )
        # Build restore SET clause from captured values (first row as representative)
        row = snapshot_rows[0]
        set_parts = ", ".join(f"{col} = {_quote_value(val)}" for col, val in row.items())
        if len(snapshot_rows) == 1:
            return (
                f"UPDATE {table} SET {set_parts} WHERE {where};",
                "exact",
            )
        # Multiple rows: generate one UPDATE per row if we have unique identifiers
        statements = []
        for r in snapshot_rows:
            s = ", ".join(f"{col} = {_quote_value(val)}" for col, val in r.items())
            statements.append(f"UPDATE {table} SET {s} WHERE {where};")
        return ("\n".join(statements), "approximate")

    m = _DELETE_RE.match(sql)
    if m:
        table = m.group("table")
        if not snapshot_rows:
            return ("-- No rows matched DELETE; no rollback required.", "exact")
        inserts = []
        for row in snapshot_rows:
            cols = ", ".join(row.keys())
            vals = ", ".join(_quote_value(v) for v in row.values())
            inserts.append(f"INSERT INTO {table} ({cols}) VALUES ({vals});")
        return ("\n".join(inserts), "exact" if len(snapshot_rows) <= 100 else "approximate")

    m = _INSERT_RE.match(sql)
    if m:
        table = m.group("table")
        cols = [c.strip() for c in m.group("cols").split(",")]
        vals = [v.strip() for v in m.group("vals").split(",")]
        # Try to detect an 'id' column for the DELETE
        if cols and cols[0].lower() in ("id", "pk", f"{table}_id"):
            return (
                f"DELETE FROM {table} WHERE {cols[0]} = {vals[0]};",
                "approximate",
            )
        return (
            f"-- Manual rollback required for INSERT INTO {table}.\n"
            f"-- Original INSERT: {sql[:200]}",
            "manual",
        )

    # DDL or unrecognized
    return (
        f"-- Automatic rollback not available for: {sql[:200]}\n"
        "-- Manual review required.",
        "manual",
    )


def _quote_value(val: Any) -> str:
    """Safely quote a value for SQL output."""
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    escaped = str(val).replace("'", "''")
    return f"'{escaped}'"


# ---------------------------------------------------------------------------
# Snapshot capture via psql subprocess
# ---------------------------------------------------------------------------

def _run_select_snapshot(
    select_sql: str,
    psql_conn_args: List[str],
    timeout: int = _TIMEOUT,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Execute the SELECT query and return parsed rows.
    Returns (rows, error_message).  rows is [] on failure.
    Uses psql JSON output mode for machine-parseable results.
    """
    try:
        cmd = ["psql"] + psql_conn_args + [
            "--no-psqlrc",
            "--tuples-only",
            "--no-align",
            "-c", f"SELECT row_to_json(t) FROM ({select_sql}) t",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return [], f"psql exit {result.returncode}: {result.stderr[:200]}"
        rows = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return rows, ""
    except subprocess.TimeoutExpired:
        return [], f"Snapshot SELECT timed out after {timeout}s"
    except FileNotFoundError:
        return [], "psql not found in PATH; snapshot skipped"
    except Exception as exc:
        return [], str(exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def capture_pre_execution_snapshot(
    command: str,
    service: str = "",
    environment: str = "",
) -> Dict[str, Any]:
    """
    Capture the pre-execution state for a database-change command.

    Parses the SQL, runs a SELECT snapshot to record the rows that will be
    mutated, and derives the inverse SQL. Returns a dict suitable for storing
    in ExecutionIntent.rollback_snapshot_json.

    Always non-fatal: returns an error snapshot dict if anything goes wrong.
    """
    snapshot: Dict[str, Any] = {
        "captured_at": time.time(),
        "service": service,
        "environment": environment,
        "original_command": command[:500],
        "sql": "",
        "select_query": None,
        "rows_captured": 0,
        "rows": [],
        "inverse_sql": "",
        "feasibility": "manual",
        "error": None,
    }

    try:
        sql = _extract_sql(command)
        snapshot["sql"] = sql[:500]

        select_sql = _derive_select_query(sql)
        snapshot["select_query"] = select_sql

        if select_sql:
            conn_args = _extract_psql_conn_args(command)
            if conn_args:
                rows, err = _run_select_snapshot(select_sql, conn_args)
                if err:
                    snapshot["error"] = err
                    logger.warning("[ROLLBACK-SNAPSHOT] SELECT failed for %s: %s", service, err)
                else:
                    snapshot["rows"] = rows
                    snapshot["rows_captured"] = len(rows)
            else:
                snapshot["error"] = "No psql connection args found; SELECT skipped."
                rows = []
        else:
            rows = []

        inverse_sql, feasibility = _derive_inverse_sql(sql, rows)
        snapshot["inverse_sql"] = inverse_sql
        snapshot["feasibility"] = feasibility

    except Exception as exc:
        snapshot["error"] = str(exc)
        logger.warning("[ROLLBACK-SNAPSHOT] Snapshot capture failed (non-fatal): %s", exc)

    return snapshot


def build_rollback_command_from_snapshot(
    snapshot: Dict[str, Any],
    original_command: str = "",
) -> Tuple[str, str]:
    """
    Build the best available rollback command using a captured snapshot.

    Returns (rollback_command, feasibility):
      "exact"       — inverse SQL derived from captured pre-mutation state
      "approximate" — best-effort inverse (review before running)
      "manual"      — only a comment; human intervention required

    The returned command is a ready-to-run psql invocation if psql conn args
    can be extracted from the original command, otherwise bare SQL.
    """
    inverse_sql = (snapshot or {}).get("inverse_sql", "")
    feasibility = (snapshot or {}).get("feasibility", "manual")

    if not inverse_sql or feasibility == "manual":
        return (
            f"-- Automatic rollback not available.\n"
            f"-- Review pre-execution snapshot and perform manual restore.\n"
            f"-- Original: {original_command[:200]}",
            "manual",
        )

    # Try to reconstruct a full psql command
    conn_args = _extract_psql_conn_args(original_command or snapshot.get("original_command", ""))
    if conn_args:
        safe_sql = inverse_sql.replace("'", "'\\''")
        rollback_cmd = f"psql {' '.join(conn_args)} -c '{safe_sql}'"
    else:
        rollback_cmd = inverse_sql

    return rollback_cmd, feasibility
