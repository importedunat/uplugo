# SPDX-License-Identifier: GPL-3.0-only
"""Verify a reproducible release and install/test only its extracted contents."""
import argparse
import gzip
import os
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import release


def compare_rebuild(original, rebuilt, require_identical_archive=True):
    # Validate both bounded archives before decompressing for comparison.
    release.verify(original);release.verify(rebuilt)
    first, second = original.read_bytes(), rebuilt.read_bytes()
    identical = first == second
    if require_identical_archive:
        assert identical, 'Rebuild differs with the same compression tools'
    else:
        # zlib-ng and zlib can encode the same tar differently. Still require
        # every tar byte: contents, order, headers, timestamps and permissions.
        assert gzip.decompress(first) == gzip.decompress(second), 'Rebuilt tar differs'
    return identical


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,help='Test this exact built artifact instead of building a candidate')
    parser.add_argument('--sha256',help='Expected external SHA256 for --archive')
    parser.add_argument('--gui',action='store_true',help='Also exercise GTK from the extracted source (display required)')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='dualsense-release-') as temporary:
        root=Path(temporary)
        if args.archive:
            archive=args.archive.resolve();expected=args.sha256
        else:
            archive,checksum=release.build(root/'first',epoch=0)
            second,_=release.build(root/'second',epoch=0)
            assert archive.read_bytes()==second.read_bytes(),'Non-reproducible source package'
            expected=checksum.read_text().split()[0]
        info=release.verify(archive,expected)
        extracted=root/'extracted source with spaces'
        release.extract(archive,extracted,expected)
        assert (extracted/'RELEASE.json').is_file()
        assert (extracted/'assets/dualsense-blueprint.LICENSE.txt').is_file()
        assert not (extracted/'install-access.py').exists()
        env=dict(os.environ,PYTHONPATH=str(extracted),PYTHONDONTWRITEBYTECODE='1',
                 XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),XDG_STATE_HOME=str(root/'state'))
        subprocess.run([sys.executable,'-m','unittest','discover','-q'],cwd=extracted,env=env,check=True)
        subprocess.run([sys.executable,'tests/clean_install.py'],cwd=extracted,env=env,check=True)
        if args.gui:
            for test in ('startup', 'autostart', 'stream_recovery','native_startup','recovery','setup','deployment','migration','touchpad','steam_access','native_access','readonly','first_use','gui','accessibility','display','appearance','effects','input','analog','motion','battery','language','photos'):
                subprocess.run([sys.executable,'tests/'+test+'_smoke.py'],cwd=extracted,env=env,check=True)
        # Rebuild without the original checkout or Git metadata and compare again.
        import json
        epoch=json.loads((extracted/'RELEASE.json').read_text())['epoch']
        subprocess.run([sys.executable,'release.py','build','--output',str(root/'rebuilt')],
                       cwd=extracted,env=dict(env,SOURCE_DATE_EPOCH=str(epoch)),check=True,stdout=subprocess.DEVNULL)
        rebuilt=root/'rebuilt'/('dualsense-usb-'+info['version']+'.tar.gz')
        identical=compare_rebuild(archive,rebuilt,require_identical_archive=args.archive is None)
        print('RELEASE OK:',info['version'],info['files'],'files; checksums, identical tar, extracted tests and clean installation; gzip byte-identical:',identical,'GUI:',args.gui)


if __name__=='__main__':main()
