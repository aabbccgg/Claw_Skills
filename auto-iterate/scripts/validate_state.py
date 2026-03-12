#!/usr/bin/env python3
import argparse, json, re, sys
from pathlib import Path
import yaml

STATUS = {"running", "awaiting-result", "paused", "complete"}
EXECUTION_MODE = {"spawned-worker"}
PENDING = {"idle", "spawn", "advance", "pause", "complete", "resume"}
RESUME_MODE = {"none", "quota-auto", "user-resume"}
BLOCKED_BY = {"none", "claude-quota", "user-input", "repair-failed"}
POLL_COMPLEXITY = {"trivial", "simple", "moderate", "complex"}
CRON_PATH = {"native-first-cli-fallback"}
LOOP_STATUS = {"pending", "running", "paused", "complete"}
WORKER_STATUS = {"accepted", "running", "success", "no-change", "blocked", "failed", "timed-out", "stalled"}
ACTIVE_WORKER_STATUSES = {"accepted", "running"}


def load_yaml_from_state(path: Path):
    text = path.read_text()
    m = re.search(r"```yaml\n(.*?)\n```", text, re.S)
    body = m.group(1) if m else text
    return yaml.safe_load(body)


def err(errors, msg):
    errors.append(msg)


def main():
    ap = argparse.ArgumentParser(description='Validate auto-iterate STATE.md structure and required fields.')
    ap.add_argument("state_path", help='Path to STATE.md (fenced YAML or raw YAML).')
    ap.add_argument("--json", action="store_true", help='Emit machine-readable JSON result.')
    args = ap.parse_args()

    path = Path(args.state_path).expanduser()
    data = load_yaml_from_state(path)
    errors = []
    warnings = []

    for key in ["id", "task", "target", "status", "started_at", "workdir", "round", "loops_mode", "execution_mode", "origin", "coordination", "subagents", "progress", "resume", "cleanup"]:
        if key not in data:
            err(errors, f"missing top-level field: {key}")

    if data.get("status") not in STATUS:
        err(errors, f"invalid status: {data.get('status')}")
    if data.get("execution_mode") not in EXECUTION_MODE:
        err(errors, f"invalid execution_mode: {data.get('execution_mode')}")

    origin = data.get("origin", {})
    report_to = origin.get("report_to", {})
    for key in ["channel", "target"]:
        if key not in report_to:
            err(errors, f"origin.report_to missing: {key}")

    coord = data.get("coordination", {})
    for key in ["state_version", "writer_session", "lease_expires_at", "pending_transition", "last_cycle_at", "next_expected_wake_at", "current_wake_job_id", "next_wake_job_id", "watchdog_job_id", "cleanup_pending", "watchdog_tripped_count", "alert_needed", "alert_sent", "poll_streak", "poll_complexity", "cron_path"]:
        if key not in coord:
            err(errors, f"coordination missing: {key}")
    if coord.get("pending_transition") not in PENDING:
        err(errors, f"invalid pending_transition: {coord.get('pending_transition')}")
    if coord.get("poll_complexity") not in POLL_COMPLEXITY:
        err(errors, f"invalid poll_complexity: {coord.get('poll_complexity')}")
    if coord.get("cron_path") not in CRON_PATH:
        err(errors, f"invalid cron_path: {coord.get('cron_path')}")
    if not isinstance(coord.get("cleanup_pending", []), list):
        err(errors, "coordination.cleanup_pending must be a list")
    for key in ["alert_needed", "alert_sent"]:
        if key in coord and not isinstance(coord.get(key), bool):
            err(errors, f"coordination.{key} must be bool")

    progress = data.get("progress", {})
    for key in ["active_loop_ids", "last_subagent_result", "last_failure_reason", "completed_items", "in_progress_items", "commit_refs", "test_summary", "total_retry_count", "no_fix_rounds_total"]:
        if key not in progress:
            err(errors, f"progress missing: {key}")
    for key in ["active_loop_ids", "completed_items", "in_progress_items", "commit_refs"]:
        if not isinstance(progress.get(key, []), list):
            err(errors, f"progress.{key} must be a list")
    if 'pending_reports' in progress:
        if not isinstance(progress.get('pending_reports'), list):
            err(errors, 'progress.pending_reports must be a list when present')
        else:
            for i, item in enumerate(progress.get('pending_reports', [])):
                if not isinstance(item, dict):
                    err(errors, f'progress.pending_reports[{i}] must be an object')
                    continue
                for req in ['type', 'key']:
                    if req not in item:
                        err(errors, f'progress.pending_reports[{i}] missing: {req}')

    resume = data.get("resume", {})
    if resume.get("mode") not in RESUME_MODE:
        err(errors, f"invalid resume.mode: {resume.get('mode')}")
    if resume.get("blocked_by") not in BLOCKED_BY:
        err(errors, f"invalid resume.blocked_by: {resume.get('blocked_by')}")

    cleanup = data.get("cleanup", {})
    for key in ["terminal_report_sent", "wake_cleanup_complete"]:
        if key not in cleanup:
            err(errors, f"cleanup missing: {key}")
        elif not isinstance(cleanup.get(key), bool):
            err(errors, f"cleanup.{key} must be bool")

    subs = data.get("subagents", [])
    if not isinstance(subs, list):
        err(errors, "subagents must be a list")
        subs = []
    else:
        for i, sub in enumerate(subs):
            for key in ["child_session_key", "run_id", "loop_id", "branch_id", "status", "started_at", "timeout_at", "last_checked_at", "summary", "criteria_assessment", "next_action_hint"]:
                if key not in sub:
                    err(errors, f"subagents[{i}] missing: {key}")
            if sub.get("run_id") not in [None] and not isinstance(sub.get("run_id"), str):
                err(errors, f"subagents[{i}].run_id must be string or null")
            if sub.get("status") not in WORKER_STATUS:
                err(errors, f"invalid subagents[{i}].status: {sub.get('status')}")
            if sub.get("status") in ACTIVE_WORKER_STATUSES and not sub.get("run_id"):
                warnings.append(f"subagents[{i}] active spawned worker has null run_id")

    loops = data.get("loops", [])
    if not isinstance(loops, list):
        err(errors, "loops must be a list")
        loops = []
    else:
        for i, loop in enumerate(loops):
            if loop.get("status") not in LOOP_STATUS:
                err(errors, f"invalid loops[{i}].status: {loop.get('status')}")
            branches = loop.get("branches", []) or []
            if not isinstance(branches, list):
                err(errors, f"loops[{i}].branches must be a list")
                continue
            for j, branch in enumerate(branches):
                if branch.get("status") not in LOOP_STATUS:
                    err(errors, f"invalid loops[{i}].branches[{j}].status: {branch.get('status')}")

    # Lightweight invariants kept here; heavier ones live in validate_protocol.py
    active_subs = [s for s in subs if s.get("status") in ACTIVE_WORKER_STATUSES]
    status = data.get("status")
    if status == "complete" and active_subs:
        err(errors, "complete state must not have active workers")
    if cleanup.get("terminal_report_sent") and status not in {"complete", "paused"}:
        err(errors, "terminal_report_sent=true requires terminal status")
    if coord.get("alert_sent") and coord.get("alert_needed"):
        warnings.append("alert_sent and alert_needed are both true")

    ok = not errors
    result = {"ok": ok, "errors": errors, "warnings": warnings, "statePath": str(path)}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if ok:
            print(f"OK: {path}")
            for w in warnings:
                print(f"! {w}")
        else:
            print(f"INVALID: {path}")
            for e in errors:
                print(f"- {e}")
            for w in warnings:
                print(f"! {w}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
