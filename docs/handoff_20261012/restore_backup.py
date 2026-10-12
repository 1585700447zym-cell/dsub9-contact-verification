"""Restore the byte-exact D-sub9 migration archive without scientific imports."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import shutil
import urllib.request
import zipfile

REPO = '1585700447zym-cell/dsub9-contact-verification'
TAG = 'handoff-20261012'

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()

def safe_join(root, name):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:
        raise ValueError('Unsafe archive path: ' + name)
    target = root.joinpath(*p.parts).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError('Path escapes destination: ' + name)
    return target

def destination(root, name):
    if name.startswith('current/'):
        return safe_join(root, name[len('current/'):])
    return safe_join(root / 'migration_extras', name)

def download(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.download')
    req = urllib.request.Request(url, headers={'User-Agent': 'Dsub9-Restore'})
    with urllib.request.urlopen(req, timeout=600) as src, temp.open('wb') as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
    os.replace(temp, path)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--download', action='store_true')
    ap.add_argument('--restore', action='store_true')
    ap.add_argument('--overwrite', action='store_true')
    ap.add_argument('--verify-restored', action='store_true')
    ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument('--assets-dir', type=Path)
    args = ap.parse_args()
    root = args.root.resolve()
    assets = (args.assets_dir or root / 'tmp/handoff_download_20261012').resolve()
    assets.mkdir(parents=True, exist_ok=True)
    manifest_path = assets / 'backup_manifest.json'
    if args.download:
        req = urllib.request.Request('https://api.github.com/repos/' + REPO + '/releases/tags/' + TAG,
                                     headers={'User-Agent': 'Dsub9-Restore'})
        with urllib.request.urlopen(req, timeout=60) as f:
            release = json.load(f)
        links = {a['name']: a['browser_download_url'] for a in release['assets']}
        download(links['backup_manifest.json'], manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest['repository'] != REPO or manifest['tag'] != TAG:
        raise ValueError('Unexpected backup identity')
    if args.download:
        for part in manifest['archives']:
            p = safe_join(assets, part['name'])
            if not p.is_file() or p.stat().st_size != part['bytes'] or digest(p) != part['sha256']:
                print('Downloading ' + part['name'], flush=True)
                download(links[part['name']], p)
            if p.stat().st_size != part['bytes'] or digest(p) != part['sha256']:
                raise ValueError('Download checksum mismatch: ' + part['name'])
    if args.restore:
        by_archive = {}
        for entry in manifest['files']:
            by_archive.setdefault(entry['archive'], {})[entry['path']] = entry
        for part in manifest['archives']:
            p = safe_join(assets, part['name'])
            if p.stat().st_size != part['bytes'] or digest(p) != part['sha256']:
                raise ValueError('Archive checksum mismatch: ' + p.name)
            expected = by_archive[p.name]
            with zipfile.ZipFile(p) as archive:
                if len(archive.namelist()) != len(expected) or set(archive.namelist()) != set(expected):
                    raise ValueError('Archive membership mismatch: ' + p.name)
                for name, entry in expected.items():
                    target = destination(root, name)
                    if target.is_file() and target.stat().st_size == entry['bytes'] and digest(target) == entry['sha256']:
                        continue
                    if target.exists() and not args.overwrite:
                        raise FileExistsError('Different existing file; review before using --overwrite: ' + str(target))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temporary = target.with_name(target.name + '.handoff-restoring')
                    with archive.open(name) as src, temporary.open('wb') as dst:
                        shutil.copyfileobj(src, dst, 1024 * 1024)
                    if temporary.stat().st_size != entry['bytes'] or digest(temporary) != entry['sha256']:
                        raise ValueError('Restored file checksum mismatch: ' + name)
                    os.replace(temporary, target)
            print('Restored ' + p.name, flush=True)
    if args.restore or args.verify_restored:
        failures = []
        for entry in manifest['files']:
            target = destination(root, entry['path'])
            if not target.is_file() or target.stat().st_size != entry['bytes'] or digest(target) != entry['sha256']:
                failures.append(entry['path'])
        result = {'files': len(manifest['files']), 'passed': not failures, 'failures': failures,
                  'scientific_execution': 0}
        (assets / 'restore_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if failures:
            raise SystemExit(1)
    elif not args.download:
        ap.error('Choose --download, --restore, or --verify-restored')

if __name__ == '__main__':
    main()
