"""Learning physics tests run in a fresh process with the qualified runtime."""
from pathlib import Path
import pytest


@pytest.fixture(scope='session')
def runtime():
    from tools.learning.runtime import verify_runtime
    return verify_runtime(Path(__file__).resolve().parents[2] / 'tmp/mujoco_3_13_probe')


@pytest.fixture
def session(runtime):
    from tools.learning.session import EpisodeSession
    from tools.validation.run_b1_baseline import cases
    session = EpisodeSession()
    session.reset(cases()[0], seed=2026092201)
    return session
