# SPDX-License-Identifier: GPL-3.0-only
"""Copy a prepared rootfs and exercise actual package transactions privately."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import json
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rootfs',type=Path)
    parser.add_argument('manager',choices=['deb','rpm'])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if os.geteuid()==0:parser.error('Run as a regular user; root is mapped only inside the test namespace.')
    source=Path(__file__).resolve().parents[1];root=args.rootfs.resolve()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='dualsense-package-test-') as temporary:
        temporary=Path(temporary);private=temporary/'rootfs'
        def ignore(folder,names):
            relative=Path(folder).relative_to(root)
            return [name for name in names if str(relative/name) in ('dev','proc','sys','var/cache','var/lib/apt/lists/partial')]
        shutil.copytree(root,private,symlinks=True,ignore=ignore)
        # Unprivileged OCI extraction can leave inherited 0775 ancestor modes.
        # Normalize only the disposable copy, not the source image or host.
        sys.path.insert(0,str(source))
        from native_package import payloads
        ancestors={str(parent) for name in payloads(args.manager) for parent in Path(name).parents if str(parent)!='.'}
        ancestors.update(('var','var/lib','etc','etc/polkit-1','etc/polkit-1/rules.d'))
        normalized={}
        for name in sorted(ancestors):
            path=private/name
            if path.is_dir() and not path.is_symlink():
                mode=path.stat().st_mode&0o777
                if mode&0o022:
                    path.chmod(mode&~0o022);normalized[name]=[oct(mode),oct(mode&~0o022)]
        (output/'fixture-normalization.json').write_text(json.dumps(normalized,indent=2)+'\n')
        marker=temporary/'marker';marker.write_text('private package transaction test\n')
        command=['bwrap','--unshare-all','--die-with-parent','--new-session','--uid','0','--gid','0',
            '--bind',str(private),'/', '--dev','/dev','--proc','/proc','--tmpfs','/tmp','--tmpfs','/run','--tmpfs','/sys',
            '--dir','/sys/bus/usb/devices','--ro-bind',str(source),'/tmp/source','--bind',str(output),'/artifacts',
            '--ro-bind',str(marker),'/run/dualsense-native-package-test',
            '--clearenv','--setenv','PATH','/usr/bin:/bin:/usr/sbin:/sbin',
            '--setenv','HOME','/root','--setenv','LANG','C.UTF-8','--setenv','PYTHONDONTWRITEBYTECODE','1',
            '--setenv','XDG_RUNTIME_DIR','/tmp/runtime',
            '--chdir','/tmp/source','/usr/bin/python3','tests/native_package_smoke.py',args.manager]
        return subprocess.run(command).returncode


if __name__=='__main__':raise SystemExit(main())
