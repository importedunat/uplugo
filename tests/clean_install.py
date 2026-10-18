# SPDX-License-Identifier: GPL-3.0-only
"""Install from a pristine export into empty XDG dirs, then remove the export.

No systemd activation, privilege escalation, host USB or personal preferences.
Run inside the clean OS image too; this does not emulate a graphical login.
"""
import os
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from install import RUNTIME_FILES

source=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='dualsense-clean-') as temporary:
    root=Path(temporary)
    checkout=root/'source with spaces'
    checkout.mkdir()
    for name in RUNTIME_FILES:
        destination=checkout/name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source/name,destination)
    (checkout/'docs/private-photo.png').write_bytes(b'not part of the runtime inventory')
    env=dict(os.environ,XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data with spaces'),XDG_STATE_HOME=str(root/'state'))
    result=subprocess.run([sys.executable,str(checkout/'install.py'),'--files-only'],env=env,text=True,capture_output=True)
    assert result.returncode==0,result.stdout+result.stderr
    installed=root/'data with spaces/dualsense-usb/app'
    assert (installed/'window.py').exists()
    receipt=installed.parent/'installation.json'
    record=json.loads(receipt.read_text())
    assert 'app/uninstall.py' in record['files'] and 'app/remove-access.py' in record['files']
    assert (installed/'docs/linux-support.md').exists()
    assert (installed/'LICENSE').read_text().startswith('                    GNU GENERAL PUBLIC LICENSE')
    assert not (installed/'controllers.json').exists()
    assert not (installed/'docs/private-photo.png').exists()
    assert not (root/'config/dualsense-usb/controllers.json').exists()
    desktop=root/'data with spaces/applications/dualsense-usb.desktop'
    subprocess.run(['desktop-file-validate',str(desktop)],check=True)
    service=root/'config/systemd/user/dualsense-usb.service'
    subprocess.run(['systemd-analyze','--user','verify',str(service)],env=env,check=True,stdout=subprocess.DEVNULL)
    assert str(checkout) not in desktop.read_text()+service.read_text()
    # Installing again is safe and must not overwrite preferences.
    preference=root/'config/dualsense-usb/controllers.json'
    preference.parent.mkdir(parents=True)
    preference.write_text('{"names":{"hid:sample":"Meu controle"}}')
    before=preference.read_bytes()
    subprocess.run([sys.executable,str(checkout/'install.py'),'--files-only'],env=env,check=True,stdout=subprocess.DEVNULL)
    assert preference.read_bytes()==before
    # Kill the actual installer after its directory exchange, then recover from
    # the installed copy. Recovery must not depend on the original download.
    before_receipt=receipt.read_bytes()
    code=('import sys,os,signal; sys.path.insert(0,sys.argv[1]); import install,install_transaction as tx\n'
          'def stop(step):\n'
          ' if step=="app":os.kill(os.getpid(),signal.SIGKILL)\n'
          'tx.checkpoint=stop; install.install(launch=False,files_only=True)')
    interrupted=subprocess.run([sys.executable,'-c',code,str(checkout)],env=env,capture_output=True)
    assert interrupted.returncode==-9,interrupted.stderr.decode()
    pending=installed.parent/'.installation-pending.json'
    assert pending.exists()
    refused=subprocess.run([sys.executable,str(checkout/'install.py'),'--files-only'],env=env,capture_output=True,text=True)
    assert refused.returncode!=0 and 'interrompida' in refused.stderr
    recovered=subprocess.run([sys.executable,str(installed/'install.py'),'--recover','--files-only'],env=env,capture_output=True,text=True)
    assert recovered.returncode==0,recovered.stdout+recovered.stderr
    assert 'restaurada' in recovered.stdout and not pending.exists()
    assert receipt.read_bytes()==before_receipt and preference.read_bytes()==before
    # Updates must refuse an older live process as well as a held lock. This
    # fixture has no hardware code; it occupies the exact installed entrypoint.
    window=installed/'window.py';real_window=window.read_bytes()
    window.write_text('import time\ntime.sleep(30)\n')
    child=subprocess.Popen([sys.executable,str(window)],env=env)
    try:
        refused=subprocess.run([sys.executable,str(checkout/'install.py'),'--files-only'],env=env,text=True,capture_output=True)
        assert refused.returncode!=0 and 'bandeja' in refused.stderr,refused.stderr
        assert window.read_text()=='import time\ntime.sleep(30)\n'
        assert child.poll() is None
    finally:
        child.terminate();child.wait(timeout=5);window.write_bytes(real_window)
    # A normal install must also succeed without a user systemd manager. This
    # shim cannot reach the host service and records unexpected service changes.
    shim=root/'bin';shim.mkdir()
    calls=root/'systemctl-calls'
    systemctl=shim/'systemctl'
    systemctl.write_text('#!'+sys.executable+'\nimport sys\nfrom pathlib import Path\n'
                         'with Path('+repr(str(calls))+').open("a") as stream:stream.write(repr(sys.argv[1:])+"\\n")\n'
                         'raise SystemExit(1)\n')
    systemctl.chmod(0o755)
    no_manager=dict(env,PATH=str(shim)+os.pathsep+env.get('PATH',''))
    subprocess.run([sys.executable,str(checkout/'install.py'),'--no-launch'],env=no_manager,check=True,stdout=subprocess.DEVNULL)
    assert calls.read_text().splitlines()==[repr(['--user','show-environment'])]
    assert preference.read_bytes()==before
    # A truncated new download must not start replacing the current copy.
    source_window=checkout/'window.py';window_bytes=source_window.read_bytes()
    source_window.unlink()
    installed_before=(installed/'window.py').read_bytes()
    incomplete=subprocess.run([sys.executable,str(checkout/'install.py'),'--files-only'],env=env,text=True,capture_output=True)
    assert incomplete.returncode!=0 and 'Não foi possível concluir' in incomplete.stderr
    assert 'Traceback' not in incomplete.stderr
    assert (installed/'window.py').read_bytes()==installed_before
    assert preference.read_bytes()==before
    source_window.write_bytes(window_bytes)
    # Destination links must be refused before replacing any earlier file.
    installed_icon=installed/'assets/dualsense-usb.svg';icon_bytes=installed_icon.read_bytes()
    outside=root/'unrelated-file';outside.write_bytes(b'untouched')
    installed_icon.unlink();installed_icon.symlink_to(outside)
    linked=subprocess.run([sys.executable,str(checkout/'install.py'),'--files-only'],env=env,text=True,capture_output=True)
    assert linked.returncode!=0 and 'Link inesperado' in linked.stderr,linked.stderr
    assert outside.read_bytes()==b'untouched' and (installed/'window.py').read_bytes()==installed_before
    installed_icon.unlink();installed_icon.write_bytes(icon_bytes)
    shutil.rmtree(checkout)
    subprocess.run([sys.executable,'-c','import window,ui,dualsense,broker,development,diagnostics,input_view,input_state,session,launch; print("Imports da cópia instalada: OK")'],cwd=installed,env=env,check=True)
    subprocess.run([sys.executable,'-c','import i18n; i18n.set_language("en"); assert i18n._("Só carregar")=="Charge only"; i18n.set_language("es"); assert i18n._("Só carregar")=="Solo cargar"'],cwd=installed,env=env,check=True)
    subprocess.run([sys.executable,str(installed/'doctor.py'),'--no-session'],env=env,check=True)
    # Run the uninstaller from its installed copy after deleting the download.
    photo=installed.parent/'appearance-library/personal-photo.png'
    history=root/'state/dualsense-usb/charge-history.json'
    for path in (photo,history):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'personal fixture')
    saved={path:path.read_bytes() for path in (preference,photo,history)}
    snapshot={str(p.relative_to(installed)):p.read_bytes() for p in installed.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    preview=subprocess.run([sys.executable,str(installed/'uninstall.py')],env=no_manager,capture_output=True,text=True)
    assert preview.returncode==0 and 'Prévia' in preview.stdout,preview.stdout+preview.stderr
    assert snapshot=={str(p.relative_to(installed)):p.read_bytes() for p in installed.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    subprocess.run([sys.executable,str(installed/'uninstall.py'),'--yes'],env=no_manager,check=True)
    assert not installed.exists() and not receipt.exists()
    assert not desktop.exists() and not service.exists()
    assert not (root/'data with spaces/icons/hicolor/scalable/apps/dualsense-usb.svg').exists()
    for path,content in saved.items():assert path.read_bytes()==content
    # A fresh installation after removal finds the same personal data.
    checkout.mkdir()
    for name in RUNTIME_FILES:
        destination=checkout/name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source/name,destination)
    subprocess.run([sys.executable,str(checkout/'install.py'),'--files-only'],env=env,check=True,stdout=subprocess.DEVNULL)
    for path,content in saved.items():assert path.read_bytes()==content
    assert (installed/'window.py').exists()
    print('CLEAN INSTALL OK: files, desktop, service, active-app protection, interrupted-update recovery, reinstall, private data, no user systemd, source removal, uninstall preview/execute and reinstall.')
