"""Stdlib-only owned worker used to reproduce interruption while holding the counter lock."""
from pathlib import Path
import sys,time
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from supervised import enter_gate
from gate_contract import Counter
from joint_contract import write
if __name__=='__main__':
    folder=Path(sys.argv[1]);enter_gate(*sys.argv[2:5]);counter=Counter(folder/'counter.json')
    counter.claim('parent')
    with counter.locked():
        write(folder/'lock_held.json',dict(held=True))
        while True:time.sleep(.05)
