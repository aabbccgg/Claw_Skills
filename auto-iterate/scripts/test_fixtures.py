#!/usr/bin/env python3
# Regression harness for auto-iterate fixture states.
# Positive fixtures must pass all checks.
# Expected-negative fixtures must fail the designated validator while the rest still pass.
import json
import subprocess
from pathlib import Path
import yaml
import os

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = [
    ROOT / 'scripts' / 'fixtures' / 'running.yaml',
    ROOT / 'scripts' / 'fixtures' / 'paused.yaml',
    ROOT / 'scripts' / 'fixtures' / 'complete.yaml',
    ROOT / 'scripts' / 'fixtures' / 'nested.yaml',
    ROOT / 'scripts' / 'fixtures' / 'parallel.yaml',
    ROOT / 'scripts' / 'fixtures' / 'worker-awaiting-result.yaml',
    ROOT / 'scripts' / 'fixtures' / 'watchdog-repair.yaml',
    ROOT / 'scripts' / 'fixtures' / 'final-report-retry.yaml',
    ROOT / 'scripts' / 'fixtures' / 'branch-worker-conflict.yaml',
    ROOT / 'scripts' / 'fixtures' / 'custom-user-criterion.yaml',
    ROOT / 'scripts' / 'fixtures' / 'broken-wake-backlog.yaml',
    ROOT / 'scripts' / 'fixtures' / 'quota-resumed.yaml',
    ROOT / 'scripts' / 'fixtures' / 'watchdog-direct-alert.yaml',
    ROOT / 'scripts' / 'fixtures' / 'no-dispatch-no-reschedule.yaml',
    ROOT / 'scripts' / 'fixtures' / 'repair-verification-incomplete.yaml',
    ROOT / 'scripts' / 'fixtures' / 'worker-dispatch-accepted.yaml',
    ROOT / 'scripts' / 'fixtures' / 'profile-reuse-dispatch-accepted.yaml',
    ROOT / 'scripts' / 'fixtures' / 'worker-dispatch-timeout-misclassified.yaml',
    ROOT / 'scripts' / 'fixtures' / 'worker-result-ready.yaml',
    ROOT / 'scripts' / 'fixtures' / 'worker-redundant-redispatch.yaml',
    ROOT / 'scripts' / 'fixtures' / 'milestone-pending-report.yaml',
    ROOT / 'scripts' / 'fixtures' / 'repair-pending-report.yaml',
    ROOT / 'scripts' / 'fixtures' / 'ingest-only-recovery.yaml',
    ROOT / 'scripts' / 'fixtures' / 'dispatch-only-recovery.yaml',
    ROOT / 'scripts' / 'fixtures' / 'repair-only-recovery.yaml',
    ROOT / 'scripts' / 'fixtures' / 'invalid-cron-path.yaml',
]


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text())


MODE_OVERRIDES = {
    'quota-resumed.yaml': 'resume',
    'watchdog-repair.yaml': 'repair',
    'watchdog-direct-alert.yaml': 'repair',
    'repair-pending-report.yaml': 'repair',
}


DOC_CONTRACTS = [
    (ROOT / 'SKILL.md', ['Cron path:', 'native cron first', 'CLI fallback second', 'resolve_agent_profile.py', 'expected primary model', 'effective model']),
    (ROOT / 'references' / 'script-interfaces.md', ['Cron path:', 'native cron first', 'openclaw cron', 'CLI fallback second', 'prefer exact id/name match', 'report ambiguity instead of guessing']),
    (ROOT / 'references' / 'recovery.md', ['Cron path is native first', 'CLI fallback second', 'openclaw cron', 'reply with `NO_REPLY`', 'send one direct repair alert immediately']),
    (ROOT / 'references' / 'examples.md', ['Cron path is native first', 'CLI fallback second', '--session isolated', '--no-deliver', '--agent <own_agent_id>', 'openclaw cron remove <job-id>', 'Agent-profile reuse example', 'Do not reuse a live session', 'resolve_agent_profile.py', 'expected_primary_model', 'effective_model', 'Watchdog healthy', 'NO_REPLY']),
    (ROOT / 'references' / 'state-schema.md', ['cron_path: native-first-cli-fallback']),
]

EXPECTED_CRON_PATH = 'native-first-cli-fallback'

EXPECTED_FAILURES = {
    ('branch-worker-conflict.yaml', 'validate_protocol.py'),
    ('broken-wake-backlog.yaml', 'validate_protocol.py'),
    ('no-dispatch-no-reschedule.yaml', 'validate_protocol.py'),
    ('repair-verification-incomplete.yaml', 'validate_protocol.py'),
    ('worker-dispatch-timeout-misclassified.yaml', 'validate_protocol.py'),
    ('worker-redundant-redispatch.yaml', 'validate_protocol.py'),
    ('repair-only-recovery.yaml', 'validate_protocol.py'),
    ('invalid-cron-path.yaml', 'validate_state.py'),
    ('invalid-cron-path.yaml', 'validate_protocol.py'),
    ('profile-reuse-dispatch-accepted.yaml', 'resolve_agent_profile.py'),
}


def render_mode_for_state(state: dict, fixture_name: str) -> str:
    if fixture_name in MODE_OVERRIDES:
        return MODE_OVERRIDES[fixture_name]
    if (state.get('coordination') or {}).get('alert_needed'):
        return 'repair'
    return {
        'running': 'progress',
        'awaiting-result': 'progress',
        'paused': 'pause',
        'complete': 'final',
    }[state['status']]


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def main():
    results = []
    doc_checks = []
    for doc_path, fragments in DOC_CONTRACTS:
        content = doc_path.read_text()
        missing = [fragment for fragment in fragments if fragment not in content]
        ok = not missing
        doc_checks.append({
            "fixture": "__docs__",
            "status": "n/a",
            "command": f"contains-all:{len(fragments)}-fragments",
            "ok": ok,
            "expected_ok": True,
            "stdout": str(doc_path),
            "stderr": "" if ok else f"missing fragments in {doc_path}: {missing}",
        })
    for fixture in FIXTURES:
        state = load_yaml(fixture)
        status = state['status']
        fixture_cron_path = ((state.get('coordination') or {}).get('cron_path'))
        if fixture.name != 'invalid-cron-path.yaml' and fixture_cron_path != EXPECTED_CRON_PATH:
            results.append({
                'fixture': fixture.name,
                'status': status,
                'command': 'fixture cron_path check',
                'ok': False,
                'expected_ok': True,
                'stdout': fixture_cron_path or '',
                'stderr': f'fixture cron_path mismatch: expected {EXPECTED_CRON_PATH}',
            })
        if fixture.name == 'profile-reuse-dispatch-accepted.yaml':
            subagents = state.get('subagents') or []
            first = subagents[0] if subagents else {}
            expected_model = str(first.get('expected_primary_model') or '')
            effective_model = str(first.get('effective_model') or '')
            ok = (
                state.get('execution_mode') == 'spawned-worker'
                and bool(first.get('run_id'))
                and 'subagent' in str(first.get('child_session_key') or '')
                and str(first.get('requested_agent_profile') or '') == 'developer'
                and expected_model == 'anthropic/claude-opus-4-6'
                and (effective_model == expected_model or bool(first.get('model_fallback_reason')))
                and 'named agent profile developer' in str((state.get('progress') or {}).get('last_subagent_result') or '').lower()
            )
            results.append({
                'fixture': fixture.name,
                'status': status,
                'command': 'fixture profile-reuse invariant',
                'ok': ok,
                'expected_ok': True,
                'stdout': str(first.get('child_session_key') or ''),
                'stderr': '' if ok else 'profile-reuse fixture must preserve requested_agent_profile, expected_primary_model, and either matching effective_model or explicit model_fallback_reason',
            })
        commands = [
            ['python3', str(ROOT / 'scripts' / 'validate_state.py'), str(fixture)],
            ['python3', str(ROOT / 'scripts' / 'validate_protocol.py'), str(fixture)],
            ['python3', str(ROOT / 'scripts' / 'compute_next_poll.py'), '--state-path', str(fixture)],
            ['python3', str(ROOT / 'scripts' / 'evaluate_progress.py'), str(fixture), '--json'],
            ['python3', str(ROOT / 'scripts' / 'check_stall.py'), str(fixture), '--json'],
            ['python3', str(ROOT / 'scripts' / 'render_progress.py'), str(fixture), '--mode', render_mode_for_state(state, fixture.name)],
        ]
        if fixture.name == 'profile-reuse-dispatch-accepted.yaml':
            commands.append([
                'python3', str(ROOT / 'scripts' / 'resolve_agent_profile.py'),
                '--requested', 'developer',
                '--agents-json', str(ROOT / 'scripts' / 'fixtures' / 'agents-main-only.json'),
                '--openclaw-json', os.path.expanduser('~/.openclaw/openclaw.json'),
                '--json',
            ])
        for cmd in commands:
            code, out, err = run(cmd)
            script_name = Path(cmd[1]).name
            expected_ok = (fixture.name, script_name) not in EXPECTED_FAILURES
            results.append({
                'fixture': fixture.name,
                'status': status,
                'command': ' '.join(cmd[:3]),
                'ok': (code == 0) == expected_ok,
                'expected_ok': expected_ok,
                'stdout': out[:300],
                'stderr': err[:300],
            })
    results.extend(doc_checks)
    failed = [r for r in results if not r['ok']]
    summary = {
        'fixtureRuns': len(results),
        'fixtures': sorted({r['fixture'] for r in results}),
        'unexpectedFailures': len(failed),
        'expectedNegativeCases': sum(1 for r in results if not r['expected_ok']),
    }
    print(json.dumps({'summary': summary, 'results': results}, indent=2))
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
