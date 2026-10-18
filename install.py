#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""Install a private application copy, menu entry and user service."""
import argparse
import os
import shutil
import subprocess
from pathlib import Path
from distribution import inventory, source_file
from app_info import VERSION
from deployment import require_user_maintenance
from maintenance import Locations, installation_lock, require_stopped, no_links
from install_transaction import install_files, recover

BASE = Path(__file__).resolve().parent
try:RUNTIME_FILES = tuple(inventory(BASE)['runtime'])
except (OSError,ValueError) as exc:
    if __name__=='__main__':raise SystemExit('Pacote incompleto ou inválido. Extraia novamente o download: '+str(exc))
    raise


def quoted(value):
    escaped = str(value).replace('\\','\\\\\\\\').replace('"','\\\\\\"').replace('`','\\\\`').replace('$','\\\\$').replace('%','%%')
    return '"'+escaped+'"'


def systemd_quoted(value):
    # $$ prevents environment expansion in ExecStart; %% escapes specifiers.
    return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('$','$$').replace('%','%%')+'"'


def import_desktop_environment():
    keys=[key for key in ('DISPLAY','WAYLAND_DISPLAY','XDG_CURRENT_DESKTOP','XDG_SESSION_TYPE') if os.environ.get(key)]
    if keys:subprocess.run(['systemctl','--user','import-environment',*keys],check=True)


def install(launch=True, access=False, files_only=False):
    if os.geteuid()==0:raise SystemExit('Execute como seu usuário, sem sudo. O acesso USB é autorizado separadamente.')
    require_user_maintenance(BASE,installing=True)
    if files_only and access:raise SystemExit('--files-only não instala o acesso USB.')
    from dualsense import migrate_legacy
    from doctor import checks
    missing=[item['name'] for item in checks(session=False) if item['required'] and not item['ok']]
    if missing:raise SystemExit('Dependências ausentes: '+', '.join(missing)+'. Consulte README.md ou execute python3 doctor.py.')
    # Validate the complete input before replacing any installed file.
    sources={name:source_file(BASE,name) for name in RUNTIME_FILES}
    locations=Locations.current()
    target=locations.app
    with installation_lock(locations):
        require_stopped(locations)
        migrate_legacy()
        external={}
        service=locations.target('service')
        desktop=locations.target('desktop')
        external['service']=f'''[Unit]
Description=Uplugo controller manager
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=notify
NotifyAccess=main
ExecStart=/usr/bin/python3 {systemd_quoted(target/'window.py')}
Restart=on-failure
RestartSec=2
TimeoutStopSec=15
KillMode=mixed
'''.encode()
        external['desktop']=f'''[Desktop Entry]
Type=Application
Name=Uplugo
Comment=Luzes, vibração e modos de uso dos seus controles
Exec=/usr/bin/python3 {quoted(target/'launch.py')}
Icon=dualsense-usb
Terminal=false
Categories=Game;
Keywords=DualSense;PS5;controle;USB;
StartupWMClass=dualsense-usb
'''.encode()
        external['icon']=sources['assets/dualsense-usb.svg'].read_bytes()
        install_files(locations,sources,external,VERSION)
        if shutil.which('update-desktop-database'):
            subprocess.run(['update-desktop-database',str(desktop.parent)],check=False)
        if not files_only:
            from session import systemd_available
            if systemd_available():
                subprocess.run(['systemctl','--user','daemon-reload'],check=True)
                import_desktop_environment()
            if access:
                from access_request import run_access
                result,_=run_access('install',interactive=True)
                if result.returncode:
                    raise RuntimeError('O acesso USB não foi configurado. '+(result.stderr or '').strip())
    if not files_only:
        if launch:
            from launch import open_app
            open_app(target,detach=True)
    return desktop


def recover_installation(files_only=False):
    require_user_maintenance(BASE)
    if os.geteuid()==0:raise ValueError('Execute como seu usuário, sem sudo.')
    locations=Locations.current()
    with installation_lock(locations):
        require_stopped(locations)
        result=recover(locations)
        if result!='none' and not files_only:
            from session import systemd_available
            if systemd_available():
                result_reload=subprocess.run(['systemctl','--user','daemon-reload'],check=False)
                if result_reload.returncode:print('Arquivos recuperados. Não foi possível recarregar o serviço do usuário; entre novamente na sessão do desktop.')
            desktop=locations.target('desktop')
            if desktop.parent.exists() and shutil.which('update-desktop-database'):
                subprocess.run(['update-desktop-database',str(desktop.parent)],check=False)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-launch',action='store_true')
    parser.add_argument('--files-only',action='store_true',help='Instalar arquivos sem iniciar serviços nem solicitar privilégios.')
    parser.add_argument('--access',action='store_true',help='Também solicitar autorização para instalar o helper USB.')
    parser.add_argument('--recover',action='store_true',help='Recuperar uma atualização interrompida, sem iniciar o app nem alterar o acesso USB.')
    args=parser.parse_args()
    if args.recover:
        if args.access:parser.error('--recover não instala o acesso USB.')
        try:result=recover_installation(args.files_only)
        except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError) as exc:parser.exit(1,'Não foi possível recuperar a instalação: '+str(exc)+'\nOs arquivos de recuperação foram preservados.\n')
        print({'none':'Não há atualização pendente.', 'discarded':'Preparação interrompida descartada. A instalação anterior foi mantida.', 'restored':'Instalação anterior restaurada. Você pode abrir o app novamente.', 'removed':'A primeira instalação foi desfeita. Execute o instalador novamente.', 'completed':'Atualização concluída. Limpeza de recuperação finalizada.'}[result])
        raise SystemExit(0)
    try:desktop=install(not args.no_launch,args.access,args.files_only)
    except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError) as exc:
        parser.exit(1,'Não foi possível concluir a instalação: '+str(exc)+'\nConfira os arquivos do pacote e execute python3 doctor.py.\n')
    print('Arquivos instalados:' if args.files_only else 'Instalado no menu:',desktop)
