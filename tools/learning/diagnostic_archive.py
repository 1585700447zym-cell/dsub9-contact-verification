"""Diagnostic publication with an independent receipt and tagged invalid data."""
import gzip
import hashlib
import json
import os
from pathlib import Path

from tools.validation.native313_matrix_audit import archive_nonfinite


def _receipt(path, receipt):
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(archive_nonfinite(receipt), ensure_ascii=False,
                                    indent=2, allow_nan=False), encoding='utf-8')
    os.replace(temporary, path)


def publish_diagnostic(folder, raw, receipt):
    """Persist counts first; a failed archive never suppresses the receipt.

    Existing archives are immutable. Nonfinite values are explicit evidence
    tags, never silently replaced with zero or accepted as training samples.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder/'receipt.json'
    _receipt(path, receipt)
    try:
        encoded = json.dumps(archive_nonfinite(raw), ensure_ascii=False,
                             allow_nan=False, separators=(',', ':')).encode('utf-8')
        data = gzip.compress(encoded, mtime=0)
        with (folder/'episode.json.gz').open('xb') as stream:
            stream.write(data)
        receipt['archive_sha256'] = hashlib.sha256(data).hexdigest()
    except BaseException as exc:
        receipt['archive_error'] = repr(exc)
        raise
    finally:
        _receipt(path, receipt)
    return receipt['archive_sha256']
