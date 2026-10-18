# SPDX-License-Identifier: GPL-3.0-only
"""Program ownership, launch routing and maintenance without system writes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import access_request
import deployment as deploy
import install
import launch
import session
import setup_state
import uninstall
from distribution import inventory, safe_name
from maintenance import Locations


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.system=self.root/'usr/share/dualsense-usb';self.system.mkdir(parents=True)
        self.loc=Locations(self.root/'data',self.root/'config')
        self.marker=self.system/deploy.MARKER
        self.record={'format':1,'manager':'deb','version':deploy.VERSION}
        self.marker.write_text(json.dumps(self.record))
        for target,name,value in ((deploy,'SYSTEM_APP',self.system),(deploy,'BASE',self.system)):
            mocked=patch.object(target,name,value);mocked.start();self.addCleanup(mocked.stop)

    def test_fixed_paths_and_strict_marker_cannot_fall_back_to_manual_installation(self):
        for manager in ('deb','rpm'):
            self.marker.write_text(json.dumps(dict(self.record,manager=manager)))
            view=deploy.inspect_deployment()
            self.assertEqual(view.manager,manager);self.assertEqual(view.helper,Path('/usr/libexec/dualsense-usb-helper'))
        for content in ('[]','{}','not json',json.dumps(dict(self.record,format=True)),
                        json.dumps(dict(self.record,manager='shell')),json.dumps(dict(self.record,version='old')),
                        json.dumps(dict(self.record,helper='/tmp/injected')), ' '*4097):
            self.marker.write_text(content)
            with self.assertRaises(ValueError):deploy.inspect_deployment()
        self.marker.unlink()
        with self.assertRaises(ValueError):deploy.inspect_deployment()
        self.marker.symlink_to(self.root/'missing')
        with self.assertRaises(ValueError):deploy.inspect_deployment()
        copy=self.root/'copied';copy.mkdir();(copy/deploy.MARKER).write_text(json.dumps(self.record))
        with self.assertRaises(ValueError):deploy.inspect_deployment(copy)
        with self.assertRaises(ValueError):safe_name(deploy.MARKER)
        manual=deploy.inspect_deployment(self.root/'download')
        self.assertFalse(manual.system)
        self.assertEqual(manual.helper,Path('/usr/local/libexec/dualsense-usb-helper'))

    def test_personal_data_is_not_migration_conflict_but_entrypoints_and_pending_updates_are(self):
        self.loc.base.mkdir(parents=True)
        for name in ('appearance-library','battery-history','controllers.json'):
            (self.loc.base/name).write_text('personal')
        self.assertEqual(deploy.legacy_conflicts(self.loc),[])
        for target in (self.loc.app,self.loc.receipt,self.loc.pending,self.loc.target('desktop'),self.loc.target('service')):
            target.parent.mkdir(parents=True,exist_ok=True);target.symlink_to(self.root/'missing')
            self.assertIn(str(target),deploy.legacy_conflicts(self.loc))
            with self.assertRaises(RuntimeError):deploy.require_no_legacy(self.loc)
            target.unlink()
        self.assertTrue((self.loc.base/'controllers.json').exists())

    def test_native_cli_cannot_create_or_remove_user_copy_or_request_admin(self):
        with patch.object(install,'BASE',self.system),patch.object(install,'installation_lock') as lock, \
             patch.object(uninstall,'installation_lock') as removal_lock, \
             patch.object(access_request.subprocess,'run') as run:
            for operation in (lambda:install.install(),lambda:install.recover_installation(),
                              lambda:uninstall.uninstall(self.loc,True),lambda:uninstall.preview(self.loc,True)):
                with self.assertRaises(RuntimeError):operation()
            lock.assert_not_called();removal_lock.assert_not_called();run.assert_not_called()
        self.assertFalse(self.loc.data.exists());self.assertFalse(self.loc.config.exists())
        # A downloaded installer must not shadow an existing system package.
        with self.assertRaises(RuntimeError):deploy.require_user_maintenance(self.root/'download',installing=True)
        deploy.require_user_maintenance(self.root/'download')  # Allows explicit legacy removal/recovery.

    def test_native_access_uses_only_package_administrator_and_no_generated_script(self):
        admin=self.root/'admin';admin.write_text('fixture')
        with patch.object(access_request,'SYSTEM_ACCESS',admin), \
             patch.object(access_request,'installation_source') as generate, \
             patch.object(access_request,'removal_source') as remove, \
             patch.object(access_request.tempfile,'TemporaryDirectory') as temporary, \
             patch.object(access_request.subprocess,'run',return_value=subprocess.CompletedProcess([],126,'','cancelled')) as run:
            for action in ('install','remove'):
                result,helper=access_request.run_access(action)
                self.assertEqual(run.call_args.args[0],['pkexec',str(admin),action])
                self.assertEqual(result.returncode,126)
                self.assertEqual(helper is not None,action=='install')
            admin.unlink()
            with self.assertRaises(RuntimeError):access_request.run_access('install')
            self.assertEqual(run.call_count,2)
            generate.assert_not_called();remove.assert_not_called();temporary.assert_not_called()

    def test_native_setup_is_read_only_and_opens_package_files(self):
        for name in inventory()['runtime']:
            target=self.system/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(setup_state.BASE/name,target)
        before={p.relative_to(self.system):p.read_bytes() for p in self.system.rglob('*') if p.is_file()}
        backend=setup_state.SetupBackend(self.system,self.loc)
        with patch.object(setup_state,'checks',return_value=[]),patch.object(setup_state,'spawn_logged') as spawn:
            view=backend.inspect()
            self.assertEqual(view.system_package,'deb');self.assertTrue(view.launchable)
            for action in ('install','remove','recover'):
                self.assertFalse(view.allowed(action,True))
                with self.assertRaises(RuntimeError):backend.execute(action,True)
            backend.open_app()
            self.assertEqual(spawn.call_args.args[0],['/usr/bin/python3',str(self.system/'launch.py')])
            self.loc.base.mkdir(parents=True);self.loc.pending.write_text('{}')
            self.assertFalse(backend.inspect().launchable)
            with self.assertRaises(RuntimeError):backend.open_app()
            self.assertEqual(spawn.call_count,1)
            self.assertEqual(self.loc.pending.read_text(),'{}')
            self.marker.unlink()
            invalid=backend.inspect()
            self.assertTrue(invalid.system_package and invalid.source_error)
            self.assertFalse(invalid.launchable or invalid.allowed('install'))
            self.marker.write_text(json.dumps(self.record))
        self.assertEqual(before,{p.relative_to(self.system):p.read_bytes() for p in self.system.rglob('*') if p.is_file()})

    def test_native_launcher_never_installs_or_starts_legacy_service(self):
        with patch.object(launch.Locations,'current',return_value=self.loc), \
             patch.object(launch,'activate_existing',return_value=False) as activate, \
             patch.object(launch,'systemd_available',return_value=True), \
             patch.object(install,'install') as copy,patch.object(install,'import_desktop_environment'), \
             patch.object(launch.subprocess,'run') as run:
            run.return_value=subprocess.CompletedProcess([],0,f'FragmentPath={deploy.SYSTEM_UNIT_PATH}\nDropInPaths=\n','')
            launch.open_app(self.system)
            copy.assert_not_called()
            self.assertEqual(run.call_args.args[0],['systemctl','--user','start',deploy.SYSTEM_UNIT])
            activate.assert_called_once_with(expected_directory=self.system)
            for value in ('FragmentPath=/home/tester/old.service\nDropInPaths=\n',
                          f'FragmentPath={deploy.SYSTEM_UNIT_PATH}\nDropInPaths=/tmp/override.conf\n',''):
                run.reset_mock();run.return_value=subprocess.CompletedProcess([],0,value,'')
                with self.assertRaises(RuntimeError):launch.open_app(self.system)
                self.assertFalse(any('start' in call.args[0] for call in run.call_args_list))
            self.assertFalse(self.loc.data.exists());self.assertFalse(self.loc.config.exists())

    def test_native_legacy_conflicts_show_assistant_before_activation_and_never_recover_implicitly(self):
        self.loc.base.mkdir(parents=True);self.loc.pending.write_text('old transaction')
        with patch.object(launch.Locations,'current',return_value=self.loc), \
             patch.object(launch,'activate_existing') as activate, \
             patch.object(launch,'systemd_available') as systemd,patch.object(launch.os,'execv') as execute:
            launch.open_app(self.system)
            execute.assert_called_once_with('/usr/bin/python3',['/usr/bin/python3',str(self.system/'setup.py')])
            activate.assert_not_called();systemd.assert_not_called()
        self.assertEqual(self.loc.pending.read_text(),'old transaction')

    def test_native_without_systemd_and_service_failure_do_not_use_manual_paths(self):
        with patch.object(launch.Locations,'current',return_value=self.loc), \
             patch.object(launch,'activate_existing',return_value=False), \
             patch.object(launch,'systemd_available',return_value=False),patch.object(launch.os,'execv') as execute:
            launch.open_app(self.system)
            execute.assert_called_once_with('/usr/bin/python3',['/usr/bin/python3',str(self.system/'window.py')])
        def runner(command,**kwargs):
            if 'start' in command:raise subprocess.CalledProcessError(1,command)
            return subprocess.CompletedProcess(command,0,f'FragmentPath={deploy.SYSTEM_UNIT_PATH}\nDropInPaths=\n','')
        with patch.object(launch.Locations,'current',return_value=self.loc), \
             patch.object(launch,'activate_existing',return_value=False) as activate, \
             patch.object(launch,'systemd_available',return_value=True),patch.object(install,'import_desktop_environment'), \
             patch.object(launch.subprocess,'run',side_effect=runner),patch.object(launch.os,'execv') as execute:
            with self.assertRaises(subprocess.CalledProcessError):launch.open_app(self.system)
            execute.assert_not_called();self.assertEqual(activate.call_count,2)

    def test_owner_identification_rejects_other_programs_and_handles_relative_python_script(self):
        proc=self.root/'proc';entry=proc/'42';entry.mkdir(parents=True)
        (entry/'cwd').symlink_to(self.system)
        for args in (b'/usr/bin/python3\0-I\0window.py\0',os.fsencode('/usr/bin/python3\0'+str(self.system/'window.py')+'\0')):
            (entry/'cmdline').write_bytes(args)
            self.assertEqual(session.process_directory(42,proc),self.system)
        for args in (b'other\0window.py\0',b'python3\0-c\0print(1)\0',b'python3\0other.py\0',b'python3\0'):
            (entry/'cmdline').write_bytes(args)
            self.assertIsNone(session.process_directory(42,proc))


if __name__=='__main__':unittest.main()
