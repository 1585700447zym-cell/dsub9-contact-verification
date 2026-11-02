"""Route the unchanged finite cycle into its new qualified execution package."""
from contextlib import contextmanager
import sys
from tools.learning import resumed_force_cycle as qualification
from tools.validation import run_force_failure_cycle as runner


def child_command(candidate_pin,authorization_pin,*,restore=False):
    return [sys.executable,'-X','utf8','-X','faulthandler','-B','-m','tools.validation.run_resumed_force_cycle',
        '--candidate-sha256',candidate_pin,'--authorization-sha256',authorization_pin,
        '--restore' if restore else '--worker']


@contextmanager
def bound_runner():
    overrides=dict(DELIVERY=qualification.DELIVERY,ForceAdmission=qualification.ForceAdmission,
        verify_candidate=qualification.verify_candidate,child_command=child_command)
    original={key:getattr(runner,key) for key in overrides}
    try:
        for key,value in overrides.items():setattr(runner,key,value)
        yield runner
    finally:
        for key,value in original.items():setattr(runner,key,value)


def main(argv=None):
    with bound_runner() as bound:return bound.main(argv)


if __name__=='__main__':raise SystemExit(main())
