"""Restore byte-pinned migration archives and derive local paths; standard library only."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda:f.read(1048576),b''): h.update(data)
    return h.hexdigest()


def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_new(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')


def safe_path(name):
    p=PurePosixPath(name)
    if not name or '\\' in name or ':' in name or p.is_absolute() or '..' in p.parts:
        raise ValueError('Unsafe archive path: '+name)
    return p


def verify_payload(manifest,destination):
    destination=Path(destination).resolve()
    for archive in manifest['archives']:
        for name,entry in archive['files'].items():
            relative=safe_path(name);p=destination.joinpath(*relative.parts)
            if not p.resolve().is_relative_to(destination) or not p.is_file() or p.is_symlink():
                raise ValueError('Missing or unsafe restored path: '+name)
            if p.stat().st_size!=entry['bytes'] or digest(p)!=entry['sha256']:
                raise ValueError('Restored payload digest differs or file modified: '+name)


def restore(manifest_path,destination):
    manifest_path=Path(manifest_path).resolve();manifest=read(manifest_path)
    if manifest['version']!='f4000_migration_v1':raise ValueError('Wrong migration package')
    destination=Path(destination).resolve()
    names=set()
    # Validate every archive/member before extracting any file.
    for item in manifest['archives']:
        name=safe_path(item['path']);archive=manifest_path.parent.joinpath(*name.parts)
        if digest(archive)!=item['sha256']:raise ValueError('Archive SHA256 digest differs: '+str(archive))
        with zipfile.ZipFile(archive) as z:
            infos=z.infolist()
            if len(infos)!=len(item['files']) or {x.filename for x in infos}!=set(item['files']):
                raise ValueError('Archive inventory differs')
            for info in infos:
                safe_path(info.filename)
                if info.filename in names or stat.S_ISLNK(info.external_attr>>16):
                    raise ValueError('Unsafe duplicate or symlink archive path')
                names.add(info.filename)
    if not destination.exists():
        destination.parent.mkdir(parents=True,exist_ok=True)
        stage=destination.with_name(destination.name+'.restore-'+uuid.uuid4().hex)
        stage.mkdir()
        for item in manifest['archives']:
            with zipfile.ZipFile(manifest_path.parent/item['path']) as z:
                for name in item['files']:
                    target=stage.joinpath(*safe_path(name).parts)
                    target.parent.mkdir(parents=True,exist_ok=True)
                    with z.open(name) as source,target.open('xb') as output:
                        for data in iter(lambda:source.read(1048576),b''):output.write(data)
        verify_payload(manifest,stage)
        # The only directory move is the just-created sibling into the named target.
        if stage.resolve().parent!=destination.parent or destination.exists():
            raise ValueError('Restore destination changed')
        stage.rename(destination)
    verify_payload(manifest,destination)
    return {**{k:str((destination/v).resolve()) for k,v in manifest['layout'].items()},
            'root':str(destination),'package_sha256':digest(manifest_path),
            'package_manifest':str(manifest_path)}


def bind_runtime(paths):
    root=Path(paths['root']);original=read(root/'source/runtime.json')
    record={**original,'module_file':str(Path(paths['runtime'])/'mujoco/__init__.py'),
            'migration_original_record_sha256':digest(root/'source/runtime.json'),
            'migration_path_relocation_only':True}
    target=root/'runtime_record.json'
    encoded=json.dumps(record,ensure_ascii=False,indent=2)+'\n'
    if target.exists() and target.read_text(encoding='utf-8')!=encoded:
        backup=target.with_name('runtime_record.before-'+uuid.uuid4().hex+'.json')
        backup.write_bytes(target.read_bytes())
    target.write_text(encoded,encoding='utf-8')
    result={**paths,'runtime_record':str(target),'runtime_record_sha256':digest(target)}
    (root/'local_paths.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


def load_paths(destination=None,manifest_path=None):
    target=Path(destination or ROOT/'.migration').resolve()
    manifest_path=Path(manifest_path or ROOT/'migration/package.json').resolve()
    verify_payload(read(manifest_path),target)
    return bind_runtime({**{k:str((target/v).resolve()) for k,v in read(manifest_path)['layout'].items()},
        'root':str(target),'package_sha256':digest(manifest_path),'package_manifest':str(manifest_path)})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=ROOT/'migration/package.json')
    parser.add_argument('--destination',type=Path,default=ROOT/'.migration')
    args=parser.parse_args()
    result=bind_runtime(restore(args.manifest,args.destination))
    print(json.dumps(dict(restored=True,**result,physics_steps=0,optimizer_updates=0),ensure_ascii=False))


if __name__=='__main__':main()
