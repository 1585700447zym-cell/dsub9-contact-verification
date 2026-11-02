"""Explicit entry point; verification is read-only and physics requires a flag."""
import argparse
from pathlib import Path
from tools.learning.contact_admission import ContactAdmission
from tools.learning.contact_execution import ContactCollection
from tools.learning.contact_training import run_training,validate_resume_source
from tools.learning.contact_evaluation import evaluate
from tools.learning.sac_checkpoint import load_checkpoint


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--admission',required=True); parser.add_argument('--sha256',required=True)
    parser.add_argument('--output'); parser.add_argument('--authorize-physical-run',action='store_true')
    parser.add_argument('--checkpoint'); parser.add_argument('--checkpoint-sha256')
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--evaluate',action='store_true');modes.add_argument('--resume',action='store_true')
    a=parser.parse_args(); admission=ContactAdmission(a.admission,expected_digest=a.sha256)
    if not a.authorize_physical_run:
        print('Execution qualification verified; no physical run started.'); return
    if not a.output: parser.error('--output required for physical run')
    output=Path(a.output).resolve()
    if output.exists(): raise FileExistsError(output)
    if a.evaluate or a.resume:
        if not a.checkpoint or not a.checkpoint_sha256: parser.error('Evaluation requires pinned checkpoint')
        if a.resume:validate_resume_source(a.checkpoint,a.checkpoint_sha256)
        chain=load_checkpoint(a.checkpoint,expected_digest=a.checkpoint_sha256,admission=admission,output=output/'restored')
        if a.evaluate:evaluate(chain,checkpoint_sha256=a.checkpoint_sha256,output=output/'evaluation')
        else:run_training(chain,output/'training',resume=True)
    else:
        if a.checkpoint or a.checkpoint_sha256: parser.error('First short training must start fresh')
        chain=ContactCollection(admission=admission,output=output/'episodes')
        run_training(chain,output/'training')


if __name__=='__main__': main()
