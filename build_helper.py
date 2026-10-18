# SPDX-License-Identifier: GPL-3.0-only
"""Rebuild the self-contained, privileged helper embedded in the installer."""
import ast
import hashlib
from pathlib import Path
import textwrap

BASE = Path(__file__).resolve().parent
DISPATCH = r'''
try:
    if len(sys.argv) in {3,4} and sys.argv[1] in {'--charge-usb','--exclusive'}:
        name=sys.argv[2]
        if os.geteuid()!=0 or not re.fullmatch(r'\d+-\d+(?:\.\d+)*',name) or not supported(USB/name):
            raise ValueError('Controle inválido.')
        if sys.argv[1]=='--exclusive':
            if len(sys.argv)!=4 or sys.argv[3] not in {'charge','proxy'}:
                raise ValueError('Modo inválido.')
            charge_usb(USB/name,decode_battery,hardware_identity(USB/name),sys.argv[3])
        elif len(sys.argv)==3:
            charge_usb(USB/name,decode_battery,hardware_identity(USB/name))
        else:raise ValueError('Argumentos inválidos.')
    elif len(sys.argv)==3 and sys.argv[1]=='--stream':stream_control(sys.argv[2])
    elif len(sys.argv)==4 and sys.argv[1]=='--switch' and sys.argv[3] in {'play','charge','read','identify'}:
        if sys.argv[3] in {'read','identify'}:print(json.dumps(inspect_control(sys.argv[2],sys.argv[3]=='identify')))
        else:switch(sys.argv[2],sys.argv[3])
    else:raise ValueError('Operação inválida.')
except Exception as exc:
    print(str(exc),file=sys.stderr);sys.exit(1)
'''


def helper_source():
    core = (BASE/'dualsense.py').read_text().split("if __name__ == '__main__':")[0]
    core = '#!/usr/bin/python3 -I\n' + core.partition('\n')[2]
    inputs = (BASE/'input_state.py').read_text().replace('from motion_state import MotionCalibration\n','')
    helper = core + '\n' + (BASE/'motion_state.py').read_text() + '\n' + inputs + '\n' + (BASE/'usb_charge.py').read_text() + '\n' + (BASE/'broker.py').read_text() + DISPATCH
    ast.parse(helper)
    return helper


def native_helper_source():
    from app_info import VERSION
    shared=native_shared_source()
    core=helper_source().removesuffix(DISPATCH).partition('\n')[2]
    source='#!/usr/bin/python3 -I\n'+shared+'\ntry:hold_native_package('+repr(VERSION)+')\nexcept Exception as exc:raise SystemExit(str(exc))\n'+core+'\ntry:\n'
    source+='    with NativeGrantFiles().session(native_actor()):\n'
    source+="        if len(sys.argv)==4 and sys.argv[1]=='--exclusive' and sys.argv[3]=='proxy' and not Path('/dev/uhid').exists():\n"
    source+="            subprocess.run(['/usr/sbin/modprobe','uhid'],check=True,timeout=5)\n"
    source+=textwrap.indent(DISPATCH,'        ')
    source+='except Exception as exc:\n    print(str(exc),file=sys.stderr);sys.exit(1)\n'
    ast.parse(source)
    return source


def native_shared_source():
    lifecycle=(BASE/'native_lifecycle.py').read_text().replace('from native_grant import NativeGrantFiles, native_rule_actor\n','')
    return (BASE/'native_grant.py').read_text()+'\n'+lifecycle


def native_payloads():
    """Package-owned artifacts; no per-account authorization is shipped."""
    from native_grant import NATIVE_HELPER_PATH,NATIVE_ADMIN_PATH,NATIVE_POLICY_PATH,NATIVE_UDEV_PATH
    from access_admin import ACCESS_UDEV
    files={NATIVE_HELPER_PATH:(native_helper_source().encode(),0o755),
           NATIVE_POLICY_PATH:((BASE/'packaging/native.policy').read_bytes(),0o644),
           NATIVE_UDEV_PATH:(ACCESS_UDEV.encode(),0o644)}
    expected={name:(hashlib.sha256(data).hexdigest(),mode) for name,(data,mode) in files.items()}
    from app_info import VERSION
    shared=native_shared_source()
    admin=(BASE/'native_access.py').read_text().replace('from native_grant import native_identity, native_rule, native_rule_actor\n','')
    source='#!/usr/bin/python3 -I\n'+shared+'\n'+admin+'\nimport sys\n'
    source+="if __name__=='__main__':\n    try:\n"
    source+="        if len(sys.argv)!=2 or sys.argv[1] not in ('install','remove'):raise ValueError('Operação inválida.')\n"
    source+='        hold_native_package('+repr(VERSION)+')\n'
    source+='        actor=native_actor()\n        changed=NativeAccess(NativeGrantFiles(),'+repr(expected)+').apply(sys.argv[1],actor)\n'
    source+="        print('Acesso autorizado para esta conta.' if sys.argv[1]=='install' else 'Acesso revogado para esta conta.')\n"
    source+='    except Exception as exc:raise SystemExit(str(exc))\n'
    ast.parse(source)
    files[NATIVE_ADMIN_PATH]=(source.encode(),0o755)
    from touchpad_policy import TOUCHPAD_ADMIN,TOUCHPAD_POLICY
    files[TOUCHPAD_ADMIN]=(touchpad_source(native=True).encode(),0o755)
    files[TOUCHPAD_POLICY]=((BASE/'packaging/touchpad.policy').read_bytes(),0o644)
    from steam_access import STEAM_ADMIN,STEAM_POLICY
    files[STEAM_ADMIN]=(steam_access_source(native=True).encode(),0o755)
    files[STEAM_POLICY]=((BASE/'packaging/steam-access.policy').read_bytes(),0o644)
    return files


def touchpad_source(native=False):
    policy=(BASE/'touchpad_policy.py').read_text()
    admin=(BASE/'touchpad_admin.py').read_text()
    admin=admin.replace('from touchpad_policy import (touchpad_identity,touchpad_rule_path,touchpad_rule,\n    touchpad_nodes,touchpad_matches,TOUCHPAD_LOCK)\n','')
    source='#!/usr/bin/python3 -I\n'+policy+'\n'+admin+'\nimport sys\n'
    if native:source+=native_shared_source()+'\n'
    source+="if __name__=='__main__':\n    try:\n"
    if native:
        from app_info import VERSION
        source+='        hold_native_package('+repr(VERSION)+')\n'
    source+='        touchpad_main(sys.argv[1:])\n'
    source+="    except Exception as exc:\n        print(json.dumps({'error':str(exc)[:1000]}),file=sys.stderr)\n        raise SystemExit(1)\n"
    ast.parse(source)
    return source



def steam_access_source(native=False):
    # Reuse protected file transactions without importing user-controlled modules.
    source=touchpad_source().split("if __name__=='__main__':")[0]
    policy=(BASE/'steam_access.py').read_text().replace('from touchpad_policy import touchpad_identity,touchpad_read\n','')
    admin=(BASE/'steam_access_admin.py').read_text().replace('from touchpad_policy import touchpad_identity\n','').replace('from touchpad_admin import TouchpadAdmin\n','')
    admin=admin.replace('from steam_access import (STEAM_HELPERS,steam_rule_path,steam_rule,steam_environment,steam_nodes,steam_matches)\n','')
    source+='\n'+policy+'\n'+admin+'\n'
    if native:source+=native_shared_source()+'\n'
    source+="if __name__=='__main__':\n    try:\n"
    if native:
        from app_info import VERSION
        source+='        hold_native_package('+repr(VERSION)+')\n'
    source+='        steam_access_main(sys.argv[1:])\n'
    source+="    except Exception as exc:\n        print(json.dumps({'error':str(exc)[:1000]}),file=sys.stderr)\n        raise SystemExit(1)\n"
    ast.parse(source)
    return source


def removal_source(helper=None):
    helper=helper if helper is not None else helper_source()
    access=(BASE/'access_admin.py').read_text()
    removal=(BASE/'packaging/remove-access.py.in').read_text().replace('@ACCESS_SOURCE@',access)
    removal=removal.replace('@LEGACY_HELPER_HASH@',repr(hashlib.sha256(helper.encode()).hexdigest()))
    ast.parse(removal)
    return removal


def installation_source(helper=None):
    helper=helper if helper is not None else helper_source()
    access=(BASE/'access_admin.py').read_text()
    template=(BASE/'packaging/install-access.py.in').read_text()
    source=template.replace('@ACCESS_SOURCE@',access).replace('@HELPER_SOURCE@',repr(helper))
    ast.parse(source)
    return source


def build():
    """Generate distribution files in a writable staging tree, never at runtime."""
    helper=helper_source()
    source=installation_source(helper)
    (BASE/'install-access.py').write_text(source)
    (BASE/'remove-access.py').write_text(removal_source(helper))
    return helper


if __name__ == '__main__':
    print('Helper compilado no instalador:', len(build()), 'bytes')
