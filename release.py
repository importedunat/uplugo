#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build, verify and extract a reproducible source release. Never opens USB."""
import argparse
import ast
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
import tempfile
import zlib
from distribution import BASE, MANIFEST, inventory, parse_manifest, safe_name, source_file

NAME = 'dualsense-usb'
RECORD = 'RELEASE.json'
MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
MAX_ARCHIVE = 40 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def version_from(data):
    tree=ast.parse(data.decode('utf-8'))
    versions=[node.value.value for node in tree.body if isinstance(node,ast.Assign)
              and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in node.targets)
              and isinstance(node.value,ast.Constant)]
    if len(versions)!=1 or not isinstance(versions[0],str):raise ValueError('Missing literal VERSION')
    version=versions[0]
    if len(version)>48 or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?',version):
        raise ValueError('Invalid release version')
    return version


def build(output, source=BASE, epoch=None):
    source=Path(source)
    manifest=inventory(source)
    listed=set(manifest['runtime']+manifest['development'])
    unlisted={p.name for p in source.glob('*.py') if p.name not in {'install-access.py','remove-access.py'}}-listed
    if unlisted:raise ValueError('Review unlisted Python modules before packaging: '+', '.join(sorted(unlisted)))
    payloads={}
    total=0
    for name in sorted(manifest['runtime']+manifest['development']):
        path=source_file(source,name)
        if path.stat().st_size>MAX_FILE:raise ValueError('Source file too large: '+name)
        with path.open('rb') as stream:data=stream.read(MAX_FILE+1)
        total+=len(data)
        if len(data)>MAX_FILE or total>MAX_TOTAL:raise ValueError('Source release too large')
        payloads[name]=data
    version=version_from(payloads['app_info.py'])
    epoch=int(os.environ.get('SOURCE_DATE_EPOCH','0')) if epoch is None else epoch
    if type(epoch) is not int or not 0<=epoch<=0xffffffff:raise ValueError('Invalid SOURCE_DATE_EPOCH')
    record={'format':1,'name':NAME,'version':version,'epoch':epoch,
            'files':{name:{'size':len(data),'sha256':digest(data)} for name,data in payloads.items()}}
    payloads[RECORD]=(json.dumps(record,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    basename=NAME+'-'+version
    archive=output/(basename+'.tar.gz')
    checksum=output/(archive.name+'.sha256')
    # Verify the entire candidate before replacing an earlier local build.
    with tempfile.TemporaryDirectory(prefix='.release-',dir=output) as staging:
        candidate=Path(staging)/archive.name
        with candidate.open('wb') as stream:
            with gzip.GzipFile(filename='',mode='wb',fileobj=stream,mtime=epoch,compresslevel=9) as compressed:
                with tarfile.open(fileobj=compressed,mode='w',format=tarfile.PAX_FORMAT) as tar:
                    for name,data in sorted(payloads.items()):
                        info=tarfile.TarInfo(basename+'/'+name)
                        info.size=len(data);info.mode=0o644;info.mtime=epoch
                        info.uid=info.gid=0;info.uname=info.gname=''
                        tar.addfile(info,io.BytesIO(data))
        checked=verify(candidate)
        checksum_data=checked['sha256']+'  '+archive.name+'\n'
        candidate_sum=Path(staging)/checksum.name
        candidate_sum.write_text(checksum_data,encoding='utf-8')
        os.replace(candidate,archive)
        os.replace(candidate_sum,checksum)
    return archive,checksum


def read_verified(archive, expected_sha256=None):
    path=Path(archive)
    if path.stat().st_size>MAX_ARCHIVE:raise ValueError('Archive too large')
    with path.open('rb') as stream:raw=stream.read(MAX_ARCHIVE+1)
    if len(raw)>MAX_ARCHIVE:raise ValueError('Archive too large')
    checksum=digest(raw)
    if expected_sha256 is not None:
        if not re.fullmatch(r'[0-9a-fA-F]{64}',expected_sha256) or checksum!=expected_sha256.lower():
            raise ValueError('Archive SHA256 mismatch')
    # Bound decompression before tarfile sees any extended/PAX headers. A tiny
    # gzip with enormous declared headers must not allocate unbounded memory.
    tar_limit=MAX_TOTAL+2*1024*1024
    with gzip.GzipFile(fileobj=io.BytesIO(raw),mode='rb') as stream:
        unpacked=stream.read(tar_limit+1)
    if len(unpacked)>tar_limit:raise ValueError('Unpacked tar too large')
    payloads={};roots=set();total=0
    with tarfile.open(fileobj=io.BytesIO(unpacked),mode='r:') as tar:
        for member in tar:
            if len(payloads)>=1000:raise ValueError('Too many archive members')
            if member.type!=tarfile.REGTYPE or member.sparse or member.mode!=0o644:
                raise ValueError('Only regular, non-executable files are allowed')
            root,separator,name=member.name.partition('/')
            if not separator:raise ValueError('Missing release directory')
            safe_name(root);safe_name(name)
            roots.add(root)
            if len(roots)!=1 or name in payloads:raise ValueError('Duplicate or inconsistent archive paths')
            total+=member.size
            if not 0<=member.size<=MAX_FILE or total>MAX_TOTAL:raise ValueError('Unpacked release too large')
            data=tar.extractfile(member).read(MAX_FILE+1)
            if len(data)!=member.size:raise ValueError('Truncated archive member')
            payloads[name]=data
    if RECORD not in payloads or MANIFEST not in payloads:raise ValueError('Missing release inventory')
    record_bytes=payloads.pop(RECORD)
    record=json.loads(record_bytes)
    if not isinstance(record,dict) or set(record)!={'format','name','version','epoch','files'} or type(record['format']) is not int or record['format']!=1 or record['name']!=NAME:
        raise ValueError('Unsupported release record')
    if type(record['epoch']) is not int or not 0<=record['epoch']<=0xffffffff:raise ValueError('Invalid release epoch')
    manifest=parse_manifest(json.loads(payloads[MANIFEST]))
    expected=set(manifest['runtime']+manifest['development'])
    if set(payloads)!=expected or not isinstance(record['files'],dict) or set(record['files'])!=expected:
        raise ValueError('Unexpected or missing release files')
    for name,data in payloads.items():
        if record['files'][name]!={'size':len(data),'sha256':digest(data)}:
            raise ValueError('Release member checksum mismatch: '+name)
    version=version_from(payloads['app_info.py'])
    if record['version']!=version or roots!={NAME+'-'+version}:raise ValueError('Release version mismatch')
    payloads[RECORD]=record_bytes
    return dict(version=version,files=len(payloads),sha256=checksum),payloads


def verify(archive, expected_sha256=None):
    return read_verified(archive,expected_sha256)[0]


def extract(archive,destination,expected_sha256=None):
    # Validate everything before creating output. Never call extractall on an
    # unchecked archive, or merge it with an existing user's directory.
    result,payloads=read_verified(archive,expected_sha256)
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=False)
    try:
        for name,data in payloads.items():
            path=destination/name;path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as stream:stream.write(data)
            path.chmod(0o644)
    except BaseException:
        shutil.rmtree(destination)
        raise
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    create=commands.add_parser('build',help='Build from the explicit file inventory')
    create.add_argument('--output',type=Path,default=BASE/'dist')
    for command in ('verify','extract'):
        sub=commands.add_parser(command)
        sub.add_argument('archive',type=Path)
        sub.add_argument('--sha256')
        if command=='extract':sub.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.command=='build':
            archive,checksum=build(args.output)
            print(archive);print(checksum)
        elif args.command=='verify':print(json.dumps(verify(args.archive,args.sha256),indent=2))
        else:print(json.dumps(extract(args.archive,args.destination,args.sha256),indent=2))
    except (OSError,ValueError,tarfile.TarError,SyntaxError,EOFError,zlib.error,RecursionError) as exc:
        parser.exit(1,'Release error: '+str(exc)+'\n')


if __name__=='__main__':main()
