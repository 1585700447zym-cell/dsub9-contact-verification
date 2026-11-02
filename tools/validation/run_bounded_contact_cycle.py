"""Explicit single-run entry point; restoring evaluation cannot start training."""
import argparse
from tools.learning.bounded_contact import BoundedAdmission,DELIVERY
from tools.learning.bounded_cycle import execute


def main():
    p=argparse.ArgumentParser();p.add_argument('--admission-sha256',required=True)
    p.add_argument('--restore-evaluate',action='store_true');a=p.parse_args()
    execute(BoundedAdmission(DELIVERY/'admission.json',expected_digest=a.admission_sha256),restore_only=a.restore_evaluate)


if __name__=='__main__':main()
