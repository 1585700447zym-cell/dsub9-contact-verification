"""Exceptional rollouts must preserve measured counts independently of gzip."""
import gzip
import json
import pytest


def test_nonfinite_rollout_is_tagged_without_losing_receipt(tmp_path):
    from tools.learning.diagnostic_archive import publish_diagnostic
    receipt = dict(status='error', error='INVALID_SIMULATION', physical_substeps=17, peak=float('nan'))
    publish_diagnostic(tmp_path, dict(trace=[dict(force=float('nan'))]), receipt)
    saved = json.loads((tmp_path/'receipt.json').read_text(encoding='utf-8'))
    raw = json.loads(gzip.decompress((tmp_path/'episode.json.gz').read_bytes()))
    assert saved['physical_substeps'] == 17
    assert saved['error'] == 'INVALID_SIMULATION'
    assert raw['trace'][0]['force'] == {'nonfinite': 'nan'}
    assert saved['peak'] == {'nonfinite': 'nan'}


def test_existing_archive_failure_still_writes_latest_receipt(tmp_path):
    from tools.learning.diagnostic_archive import publish_diagnostic
    (tmp_path/'episode.json.gz').write_bytes(b'preserve')
    with pytest.raises(FileExistsError):
        publish_diagnostic(tmp_path, {}, dict(status='error', physical_substeps=23))
    saved = json.loads((tmp_path/'receipt.json').read_text(encoding='utf-8'))
    assert saved['physical_substeps'] == 23
    assert saved['archive_error'].startswith('FileExistsError')
    assert (tmp_path/'episode.json.gz').read_bytes() == b'preserve'
