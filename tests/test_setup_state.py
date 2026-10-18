# SPDX-License-Identifier: GPL-3.0-only
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch,Mock
import setup_state as setup
import deployment
from distribution import inventory
from maintenance import record_installation,GENERATED


class SetupStateTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        # Each test owns the system-installation state too, even when the
        # developer runs this suite on a machine with a native package.
        self.system=self.root/'system-program'
        native=patch.object(deployment,'SYSTEM_APP',self.system)
        native.start();self.addCleanup(native.stop)
        self.source=self.root/'download with spaces';self.source.mkdir()
        for name in inventory()['runtime']:
            target=self.source/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(setup.BASE/name,target)
        self.loc=setup.Locations(self.root/'data',self.root/'config')
        self.backend=setup.SetupBackend(self.source,self.loc)
        self.dependencies=[dict(name='libusb',ok=True,required=True),dict(name='tray',ok=False,required=False)]
        for target,kwargs in [('checks',{'side_effect':lambda **k:self.dependencies}),('running_app',{'return_value':[]})]:
            item=patch.object(setup,target,**kwargs);item.start();self.addCleanup(item.stop)

    def installed(self):
        for key in ['app/window.py','app/launch.py',*('app/'+n for n in GENERATED),'desktop','icon','service']:
            path=self.loc.target(key);path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture '+key)
        record_installation(self.loc,['window.py','launch.py'],'1.test')

    def test_fresh_preview_creates_no_personal_directories_and_optional_items_do_not_block(self):
        view=self.backend.inspect()
        self.assertTrue(view.allowed('install'));self.assertFalse(view.allowed('remove'))
        self.assertFalse(self.loc.data.exists());self.assertFalse(self.loc.config.exists())
        self.assertFalse(view.installed);self.assertFalse(view.launchable)
        self.system.mkdir()
        view=self.backend.inspect()
        self.assertTrue(view.install_error);self.assertFalse(view.allowed('install'))
        with patch.object(setup.subprocess,'run') as run,self.assertRaises(RuntimeError):self.backend.execute('install')
        run.assert_not_called();self.assertFalse(self.loc.data.exists())

    def test_missing_package_and_dependencies_block_installation_before_subprocess(self):
        self.dependencies[0]['ok']=False
        self.assertFalse(self.backend.inspect().allowed('install'))
        with patch.object(setup.subprocess,'run') as run,self.assertRaises(RuntimeError):self.backend.execute('install')
        run.assert_not_called()
        self.dependencies[0]['ok']=True;(self.source/'ui.py').unlink()
        self.assertTrue(self.backend.inspect().source_error)
        with patch.object(setup.subprocess,'run') as run,self.assertRaises(RuntimeError):self.backend.execute('install')
        run.assert_not_called()

    def test_removed_or_modified_files_are_distinguished_and_preferences_untouched(self):
        self.installed();original=self.loc.receipt.read_bytes()
        (self.loc.app/'window.py').write_text('modified')
        view=self.backend.inspect()
        self.assertEqual(view.version,'1.test');self.assertTrue(view.launchable)
        self.assertIn(str(self.loc.app/'window.py'),view.preserve)
        self.assertNotIn(str(self.loc.app/'window.py'),view.remove)
        self.assertTrue(view.allowed('remove'));self.assertEqual(self.loc.receipt.read_bytes(),original)
        self.dependencies[0]['ok']=False
        self.assertTrue(self.backend.inspect().allowed('remove'),'Missing USB library must not prevent removal')

    def test_busy_root_and_pending_states_cannot_be_bypassed(self):
        self.installed()
        with patch.object(setup,'running_app',return_value=[42]):
            with patch.object(setup.subprocess,'run') as run,self.assertRaises(RuntimeError):self.backend.execute('remove',True)
            run.assert_not_called()
        with patch.object(setup.os,'geteuid',return_value=0):
            self.assertFalse(self.backend.inspect().allowed('install'))
        self.loc.pending.write_text('{}')
        view=self.backend.inspect()
        self.assertFalse(view.allowed('remove',True));self.assertFalse(view.allowed('install'))
        self.assertTrue(view.allowed('recover'));self.assertFalse(view.launchable)

    def test_legacy_and_invalid_receipts_are_explained_without_removing_files(self):
        self.loc.app.mkdir(parents=True)
        self.assertTrue(self.backend.inspect().removal_error)
        self.loc.receipt.write_text('[]')
        view=self.backend.inspect();self.assertTrue(view.removal_error)
        self.assertFalse(view.allowed('remove',True))
        self.assertTrue(self.loc.app.exists())

    def test_commands_are_fixed_and_admin_removal_requires_explicit_choice(self):
        self.installed()
        with patch.object(setup.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'','')) as run:
            self.backend.execute('install')
            self.assertEqual(run.call_args.args[0],['/usr/bin/python3',str(self.source/'install.py'),'--no-launch'])
            self.backend.execute('remove')
            self.assertEqual(run.call_args.args[0],['/usr/bin/python3',str(self.source/'uninstall.py'),'--yes'])
            self.backend.execute('remove',True)
            self.assertEqual(run.call_args.args[0][-1],'--remove-access')
            self.assertEqual(run.call_args.kwargs['env']['XDG_DATA_HOME'],str(self.loc.data))
            self.assertNotIn('shell',run.call_args.kwargs)
            self.loc.pending.write_text('{}');self.backend.execute('recover')
            self.assertEqual(run.call_args.args[0][-1],'--recover')

    def test_open_is_detached_and_never_waits_for_the_window_to_close(self):
        self.installed()
        with patch.dict(os.environ,{'XDG_STATE_HOME':str(self.root/'state')}),patch.object(setup.subprocess,'Popen') as spawn:
            result=self.backend.open_app()
        self.assertEqual(result.returncode,0)
        self.assertEqual(spawn.call_args.args[0],['/usr/bin/python3',str(self.loc.app/'launch.py')])
        self.assertTrue(spawn.call_args.kwargs['start_new_session'])
        self.assertEqual((self.root/'state/dualsense-usb/setup-launch.log').stat().st_mode&0o777,0o600)

    def test_assistant_has_separate_scope_with_systemd_and_direct_fallback_without_it(self):
        for available in (True,False):
            with patch.dict(os.environ,{'XDG_STATE_HOME':str(self.root/'state')}), \
                 patch.object(setup,'systemd_available',return_value=available), \
                 patch.object(setup.subprocess,'Popen') as spawn:
                self.assertIs(setup.launch_assistant(self.source),spawn.return_value)
                command=spawn.call_args.args[0]
                self.assertEqual(command[-2:],['/usr/bin/python3','setup.py'])
                self.assertEqual('--scope' in command,available)
                self.assertEqual(spawn.call_args.kwargs['cwd'],self.source)
                self.assertTrue(spawn.call_args.kwargs['start_new_session'])
                self.assertNotIn('shell',spawn.call_args.kwargs)
            self.assertEqual((self.root/'state/dualsense-usb/setup-assistant.log').stat().st_mode&0o777,0o600)

    def test_assistant_missing_source_or_root_cannot_start_a_process(self):
        with patch.object(setup.subprocess,'Popen') as spawn:
            with self.assertRaises(FileNotFoundError):setup.launch_assistant(self.root/'missing')
            with patch.object(setup.os,'geteuid',return_value=0),self.assertRaises(ValueError):setup.launch_assistant(self.source)
            spawn.assert_not_called()


if __name__=='__main__':unittest.main()
