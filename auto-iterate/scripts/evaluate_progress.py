#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path
import yaml


def load_state(path: Path):
    text = path.read_text()
    m = re.search(r"```yaml\n(.*?)\n```", text, re.S)
    body = m.group(1) if m else text
    return yaml.safe_load(body)


def active_worker_count(subs, loop_id, branch_id):
    return sum(1 for sub in subs if sub.get('loop_id') == loop_id and sub.get('branch_id') == branch_id and sub.get('status') in {'accepted', 'running'})


def first_incomplete_top_level(loops):
    for loop in loops:
        if not loop.get('parent') and loop.get('status') != 'complete':
            return loop.get('id')
    return None


def active_child_loops(loops, parent_id):
    return [loop for loop in loops if loop.get('parent') == parent_id and loop.get('status') in {'pending', 'running', 'paused'}]


def loop_action(loop, state):
    loop_id = loop.get('id')
    kind = loop.get('kind')
    branches = loop.get('branches') or []
    subs = state.get('subagents') or []
    parent = loop.get('parent')
    loops = state.get('loops') or []

    if loop.get('status') == 'complete':
        return {'loopId': loop_id, 'actionable': False, 'reason': 'loop-complete'}

    if state.get('loops_mode') == 'sequential' and not parent:
        first = first_incomplete_top_level(loops)
        if first and first != loop_id:
            return {'loopId': loop_id, 'actionable': False, 'reason': 'waiting-previous-top-level-loop'}

    children = active_child_loops(loops, loop_id)
    if children:
        return {
            'loopId': loop_id,
            'actionable': False,
            'reason': 'waiting-active-child-loop',
            'activeChildren': [c.get('id') for c in children],
            'mustNotAdvance': True,
        }

    if parent:
        parent_loop = next((x for x in loops if x.get('id') == parent), None)
        if parent_loop and parent_loop.get('status') == 'complete':
            return {'loopId': loop_id, 'actionable': False, 'reason': 'parent-complete', 'mustNotAdvance': True}

    if not branches:
        return {
            'loopId': loop_id,
            'actionable': loop.get('status') in {'pending', 'running'} and loop.get('current_func') is not None,
            'mode': kind,
            'currentFunc': loop.get('current_func'),
            'mergeReady': False,
            'mustNotAdvance': False,
            'recommendedEvent': None,
            'recommendedTo': None,
            'reason': None,
        }

    active_branch_ids, completed_branch_ids, blocked_branch_ids, worker_conflicts = [], [], [], []
    for b in branches:
        bid = b.get('branch_id')
        count = active_worker_count(subs, loop_id, bid)
        if count > 1:
            worker_conflicts.append(bid)
        if b.get('status') == 'complete':
            completed_branch_ids.append(bid)
        elif b.get('status') in {'pending', 'running'}:
            active_branch_ids.append(bid)
        elif b.get('status') == 'paused':
            blocked_branch_ids.append(bid)

    merge_policy = loop.get('merge_policy')
    merge_ready = False
    needs_user_criterion = False
    must_not_advance = False
    recommended_event = None
    recommended_to = None
    reason = None

    if merge_policy == 'all-success':
        merge_ready = len(completed_branch_ids) == len(branches) and len(branches) > 0
    elif merge_policy == 'quorum':
        merge_ready = len(completed_branch_ids) >= max(1, (len(branches) // 2) + (len(branches) % 2))
    elif merge_policy == 'custom-user-criterion':
        if active_branch_ids:
            needs_user_criterion = False
            merge_ready = False
            must_not_advance = False
            reason = 'waiting-for-remaining-branches-before-user-criterion'
        else:
            needs_user_criterion = True
            merge_ready = False
            must_not_advance = True
            recommended_event = 'pause-requested'
            recommended_to = 'paused'
            reason = 'custom-user-criterion-not-explicitly-satisfied'

    if worker_conflicts:
        must_not_advance = True
        recommended_event = 'pause-requested'
        recommended_to = 'paused'
        reason = f'branch-worker-conflict:{worker_conflicts[0]}'

    return {
        'loopId': loop_id,
        'actionable': (bool(active_branch_ids) or merge_ready) and not must_not_advance,
        'mode': kind,
        'activeBranches': active_branch_ids,
        'completedBranches': completed_branch_ids,
        'blockedBranches': blocked_branch_ids,
        'workerConflicts': worker_conflicts,
        'mergeReady': merge_ready,
        'mergePolicy': merge_policy,
        'currentFunc': loop.get('current_func'),
        'needsUserCriterion': needs_user_criterion,
        'mustNotAdvance': must_not_advance,
        'recommendedEvent': recommended_event,
        'recommendedTo': recommended_to,
        'reason': reason,
    }


def main():
    ap = argparse.ArgumentParser(description='Evaluate actionable loops, branch readiness, merge readiness, and branch conflicts from STATE.md.')
    ap.add_argument('state_path', help='Path to STATE.md (fenced YAML or raw YAML).')
    ap.add_argument('--json', action='store_true', help='Emit machine-readable JSON result.')
    args = ap.parse_args()
    state = load_state(Path(args.state_path).expanduser())
    loops = state.get('loops') or []
    evaluated = [loop_action(loop, state) for loop in loops]
    actionable = [x for x in evaluated if x.get('actionable')]
    result = {
        'loopsMode': state.get('loops_mode'),
        'status': state.get('status'),
        'firstIncompleteTopLevel': first_incomplete_top_level(loops),
        'actionableLoops': actionable,
        'allLoops': evaluated,
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for item in actionable:
            print(item['loopId'])


if __name__ == '__main__':
    main()
