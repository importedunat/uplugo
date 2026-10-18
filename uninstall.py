#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""Preview or remove this user's installation, preserving their saved data."""
import argparse
import os
import shutil
import subprocess
from access_request import run_access
from deployment import require_user_maintenance
from dualsense import xdg_directory
from maintenance import Locations, installation_lock, require_stopped, removal_plan, remove_user_files
from session import systemd_available
from autostart import entry_path, remove_if_ours


def preview(locations,remove_access=False):
    require_user_maintenance()
    plan=removal_plan(locations)
    print(f"Arquivos do programa a remover: {len(plan['remove'])}.")
    for key,reason in plan['preserve'].items():
        print('Preservado ('+reason+'): '+str(locations.target(key)))
    if entry_path(locations.config).exists():print('Abertura automática a remover: '+str(entry_path(locations.config)))
    print('Nomes e preferências preservados: '+str(locations.config/'dualsense-usb'))
    print('Fotos preservadas: '+str(locations.base/'appearance-library'))
    print('Histórico e diagnósticos preservados: '+str(xdg_directory('XDG_STATE_HOME','.local/state')/'dualsense-usb'))
    print('A remoção do acesso USB pedirá autorização administrativa.' if remove_access
          else 'O acesso USB administrativo será mantido. Use --remove-access para removê-lo também.')
    return plan


def remove_access_files():
    # Build a self-contained script before deleting any installed module. There
    # is no privileged path argument, dependency on cwd, or removal without auth.
    result,_=run_access('remove',interactive=True)
    if result.returncode:
        detail=(result.stderr or '').strip()
        raise RuntimeError('O acesso USB não foi removido (autorização cancelada ou operação recusada). Os arquivos do app foram mantidos.'+('\n'+detail if detail else ''))


def uninstall(locations=None,remove_access=False):
    require_user_maintenance()
    if os.geteuid()==0:raise ValueError('Execute como seu usuário, sem sudo.')
    locations=locations or Locations.current()
    with installation_lock(locations):
        require_stopped(locations)
        removal_plan(locations)  # Validate everything before requesting admin.
        if remove_access:remove_access_files()
        plan=remove_user_files(locations)
        # A login entry would otherwise point at the removed launcher.
        remove_if_ours(locations.config)
        # Imported above: the script may itself have just been removed.
        if systemd_available():
            subprocess.run(['systemctl','--user','daemon-reload'],check=True)
        if shutil.which('update-desktop-database') and locations.target('desktop').parent.exists():
            subprocess.run(['update-desktop-database',str(locations.target('desktop').parent)],check=False)
        return plan


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--yes',action='store_true',help='Executar a remoção. Sem esta opção, apenas mostra o que será feito.')
    parser.add_argument('--remove-access',action='store_true',help='Também remover helper e permissões USB, com autorização administrativa.')
    args=parser.parse_args()
    try:
        if os.geteuid()==0:raise ValueError('Execute como seu usuário, sem sudo.')
        locations=Locations.current()
        preview(locations,args.remove_access)
        if not args.yes:
            print('Prévia: nenhum arquivo removido. Encerre o app pela bandeja e acrescente --yes para executar.')
            return 0
        plan=uninstall(locations,args.remove_access)
        print(f"Removidos {len(plan['remove'])} arquivos. Seus dados foram preservados.")
        if plan['preserve']:print('Arquivos alterados foram mantidos; confira os caminhos listados acima.')
        return 0
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
        parser.exit(1,'Não foi possível concluir a remoção: '+str(exc)+'\n')


if __name__=='__main__':raise SystemExit(main())
