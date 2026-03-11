#!/usr/bin/env python3
import argparse
import json
import math
import re
from pathlib import Path
import yaml

BASE = {
    'trivial': 120,
    'simple': 240,
    'moderate': 360,
    'complex': 480,
}


def load_state(path: Path):
    text = path.read_text()
    m = re.search(r"```yaml\n(.*?)\n```", text, re.S)
    body = m.group(1) if m else text
    return yaml.safe_load(body)


def compute(complexity, poll_streak):
    base = BASE[complexity]
    if poll_streak <= 0:
        factor = 1.0
    elif poll_streak == 1:
        factor = 0.75
    else:
        factor = 0.5
    delay = max(60, int(math.floor(base * factor)))
    return {
        'complexity': complexity,
        'pollStreak': poll_streak,
        'baseSeconds': base,
        'factor': factor,
        'delaySeconds': delay,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--complexity', choices=sorted(BASE))
    ap.add_argument('--poll-streak', type=int)
    ap.add_argument('--state-path')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    complexity = args.complexity
    poll_streak = args.poll_streak

    if args.state_path:
        state = load_state(Path(args.state_path).expanduser())
        coord = state.get('coordination', {}) or {}
        complexity = complexity or coord.get('poll_complexity')
        if poll_streak is None:
            poll_streak = coord.get('poll_streak', 0)

    if complexity not in BASE:
        raise SystemExit('complexity must be provided directly or via coordination.poll_complexity in state')
    if poll_streak is None:
        poll_streak = 0

    result = compute(complexity, poll_streak)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(result['delaySeconds'])


if __name__ == '__main__':
    main()
