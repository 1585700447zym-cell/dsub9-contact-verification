"""Describe or verify Stage A; deliberately contains no physical training command."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--describe', action='store_true', help='Print versioned 140/5 interface and scope')
    group.add_argument('--check', action='store_true', help='Run offline/synthetic checks, no task physics')
    args = parser.parse_args(argv)
    if args.describe:
        from tools.learning.five_axis_contract import learning_config
        print(json.dumps(dict(config=learning_config(), physical_execution_enabled=False,
            formal_training_enabled=False, history='four control samples spanning 6 ms',
            baseline='N2, 450 um/s spiral, passive yaw admittance; no new pause/gate'),
            ensure_ascii=False, indent=2))
        return 0
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    import pytest
    return int(pytest.main([str(ROOT / 'tests/learning' / name) for name in
        ('test_five_axis_interface.py', 'test_five_axis_learning.py', 'test_five_axis_session.py')]
        + ['-q', '--tb=short']))


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
