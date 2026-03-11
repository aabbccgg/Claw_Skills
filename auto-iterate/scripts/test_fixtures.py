#!/usr/bin/env python3
# Regression harness for auto-iterate fixture states.
# Positive fixtures must pass all checks.
# Expected-negative fixtures must fail the designated validator while the rest still pass.
import json
import subprocess
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = [
    ROOT / 'scripts' / 'fixtures' / 'running.yaml',
    ROOT / 'scripts' / 'fixtures' / 'paused.yaml',
    ROOT / 'scripts' / 'fixtures' / 'complete.yaml',
    ROOT / 'scripts' / 'fixtures' / 'nested.yaml',
    ROOT / 'scripts' / 'fixtures' / 'parallel.yaml',
    ROOT / 'scripts' / 'fixtures' / 'existing-agent.yaml',
    ROOT / 'scripts' / 'fixtures' / 'watchdog-repair.yaml',
    ROOT / 'scripts' / 'fixtures' / 'final-report-retry.yaml',
    ROOT / 'scripts' / 'fixtures' / 'branch-worker-conflict.yaml',
    ROOT / 'scripts' / 'fixtures' / 'custom-user-criterion.yaml',
    ROOT / 'scripts' / 'fixtures' / 'broken-wake-backlog.yaml',
    ROOT / 'scripts' / 'fixtures' / 'deadline-exceeded.yaml',
    ROOT / 'scripts' / 'fixtures' / 'quota-resumed.yaml',
    ROOT / 'scripts' / 'fixtures' / 'watchdog-direct-alert.yaml',
    ROOT / 'scripts' / 'fixtures' / 'no-dispatch-no-reschedule.yaml',
    ROOT / 'scripts' / 'fixtures' / 'repair-verification-incomplete.yaml',
]


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text())


MODE_OVERRIDES = {
    'quota-resumed.yaml': 'resume',
    'watchdog-repair.yaml': 'repair',
    'watchdog-direct-alert.yaml': 'repair',
}

EXPECTED_FAILURES = {
    ('branch-worker-conflict.yaml', 'validate_protocol.py'),
    ('broken-wake-backlog.yaml', 'validate_protocol.py'),
    ('no-dispatch-no-reschedule.yaml', 'validate_protocol.py'),
    ('repair-verification-incomplete.yaml', 'validate_protocol.py'),
}


def render_mode_for_state(state: dict, fixture_name: str) -> str:
    if fixture_name in MODE_OVERRIDES:
        return MODE_OVERRIDES[fixture_name]
    if (state.get('coordination') or {}).get('alert_needed'):
        return 'repair'
    return {
        'running': 'progress',
        'awaiting-review': 'progress',
        'paused': 'pause',
        'complete': 'final',
    }[state['status']]


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def main():
    results = []
    for fixture in FIXTURES:
        state = load_yaml(fixture)
        status = state['status']
        commands = [
            ['python3', str(ROOT / 'scripts' / 'validate_state.py'), str(fixture)],
            ['python3', str(ROOT / 'scripts' / 'validate_protocol.py'), str(fixture)],
            ['python3', str(ROOT / 'scripts' / 'compute_next_poll.py'), '--state-path', str(fixture)],
            ['python3', str(ROOT / 'scripts' / 'evaluate_progress.py'), str(fixture), '--json'],
            ['python3', str(ROOT / 'scripts' / 'check_stall.py'), str(fixture), '--json'],
            ['python3', str(ROOT / 'scripts' / 'render_progress.py'), str(fixture), '--mode', render_mode_for_state(state, fixture.name)],
        ]
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
