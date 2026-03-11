#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = [
    ROOT / 'references' / 'fixtures-running.yaml',
    ROOT / 'references' / 'fixtures-paused.yaml',
    ROOT / 'references' / 'fixtures-complete.yaml',
]


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text())


def render_mode_for_status(status: str) -> str:
    return {
        'running': 'progress',
        'awaiting-review': 'progress',
        'paused': 'pause',
        'complete': 'final',
    }[status]


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
            ['python3', str(ROOT / 'scripts' / 'render_progress.py'), str(fixture), '--mode', render_mode_for_status(status)],
        ]
        for cmd in commands:
            code, out, err = run(cmd)
            results.append({
                'fixture': fixture.name,
                'status': status,
                'command': ' '.join(cmd[:3]),
                'ok': code == 0,
                'stdout': out[:300],
                'stderr': err[:300],
            })
    print(json.dumps(results, indent=2))
    failed = [r for r in results if not r['ok']]
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
