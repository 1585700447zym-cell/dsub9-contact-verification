"""Capacity-only repair, bound each horizon array by all face edges (3 * 6N)."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent

def patch(source):
    size_start=source.index('size_t mjc_ccdSize(')
    run_start=source.index('mjtNum mjc_ccd(',size_start)
    head=source[:size_start]
    sizing=source[size_start:run_start]
    body=source[run_start:]
    assert sizing.count('sizeof(int) * 24')==2
    assert body.count('sizeof(int) * 24')==1
    sizing=sizing.replace('sizeof(int) * 24','sizeof(int) * 18 * iterations')
    body=body.replace('sizeof(int) * 24','sizeof(int) * 18 * N')
    comment='// Each of at most 6*N triangular faces contributes at most 3 horizon edges.\n'
    return head+comment+sizing+body

if __name__=='__main__':
    original=(HERE/'upstream/engine_collision_gjk.c').read_text()
    fixed=patch(original)
    (HERE/'engine_collision_gjk_fixed.c').write_text(fixed,encoding='utf-8')
    if len(sys.argv)>1:
        target=Path(sys.argv[1]);assert target.read_text()==original
        target.write_text(fixed,encoding='utf-8')
