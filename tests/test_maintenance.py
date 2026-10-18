# SPDX-License-Identifier: GPL-3.0-only
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import maintenance as m
import uninstall


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.locations=m.Locations(self.root/'data',self.root/'config')

    def installed(self):
        names=('window.py','assets/icon.svg')
        for key in [*('app/'+n for n in (*names,*m.GENERATED)),'desktop','icon','service']:
            path=self.locations.target(key);path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('fixture: '+key)
        m.record_installation(self.locations,names,'1.test')
        return names

    def test_roundtrip_preserves_preferences_photos_history_and_unknown_files(self):
        self.installed()
        personal=[self.locations.config/'dualsense-usb/controllers.json',
                  self.locations.base/'appearance-library/picture.png',
                  self.root/'state/dualsense-usb/charge-history.json',
                  self.locations.app/'custom.txt']
        for path in personal:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'keep me')
        cache=self.locations.app/'__pycache__';cache.mkdir()
        (cache/'window.cpython-314.pyc').write_bytes(b'owned bytecode')
        (cache/'unknown.cpython-314.pyc').write_bytes(b'keep me')
        with m.installation_lock(self.locations):result=m.remove_user_files(self.locations)
        self.assertEqual(len(result['remove']),7)
        self.assertFalse(self.locations.receipt.exists())
        self.assertFalse((cache/'window.cpython-314.pyc').exists())
        self.assertEqual((cache/'unknown.cpython-314.pyc').read_bytes(),b'keep me')
        for path in personal:self.assertEqual(path.read_bytes(),b'keep me')

    def test_modified_files_are_retained_and_can_be_removed_after_restoration(self):
        self.installed()
        window=self.locations.app/'window.py';original=window.read_bytes()
        window.write_bytes(b'user changes')
        result=m.remove_user_files(self.locations)
        self.assertEqual(result['preserve'],{'app/window.py':'modificado'})
        self.assertTrue(self.locations.receipt.exists())
        window.write_bytes(original)
        result=m.remove_user_files(self.locations)
        self.assertEqual(list(result['remove']),['app/window.py'])
        self.assertFalse(self.locations.app.exists())
        self.assertFalse(self.locations.receipt.exists())

    def test_untracked_legacy_installation_requires_receipt(self):
        self.locations.app.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError,'instalação antiga'):m.removal_plan(self.locations)

    def test_invalid_receipt_paths_never_delete_anything(self):
        self.installed()
        original=self.locations.receipt.read_text()
        for key in ('app/../../outside','app//window.py','app/./window.py','app/','desktop/extra','app/a\\b','/tmp/file'):
            record=json.loads(original);record['files'][key]='0'*64
            self.locations.receipt.write_text(json.dumps(record))
            with self.subTest(key=key),self.assertRaises(ValueError):m.remove_user_files(self.locations)
            self.assertTrue((self.locations.app/'window.py').exists())
        record=json.loads(original);record['format']=True
        self.locations.receipt.write_text(json.dumps(record))
        with self.assertRaises(ValueError):m.removal_plan(self.locations)

    def test_symlink_to_external_file_is_preserved_without_following_it(self):
        self.installed()
        outside=self.root/'outside';outside.write_bytes(b'leave alone')
        target=self.locations.app/'window.py';target.unlink();target.symlink_to(outside)
        result=m.remove_user_files(self.locations)
        self.assertEqual(result['preserve'],{'app/window.py':'link'})
        self.assertEqual(outside.read_bytes(),b'leave alone')
        self.assertTrue(target.is_symlink())

    def test_shared_runtime_and_exclusive_maintenance_locks_across_processes(self):
        code=('import sys; from pathlib import Path; from maintenance import Locations,installation_lock\n'
              'with installation_lock(Locations(Path(sys.argv[1]),Path(sys.argv[2])),shared=sys.argv[3]=="shared"): pass')
        def other(kind):
            return subprocess.run([sys.executable,'-c',code,str(self.locations.data),str(self.locations.config),kind],capture_output=True)
        with m.installation_lock(self.locations,shared=True):
            self.assertEqual(other('shared').returncode,0)
            self.assertNotEqual(other('exclusive').returncode,0)
        with m.installation_lock(self.locations):
            self.assertNotEqual(other('shared').returncode,0)
        self.assertEqual(other('exclusive').returncode,0)

    def test_lock_symlink_is_rejected(self):
        self.locations.base.mkdir(parents=True)
        outside=self.root/'outside';outside.write_bytes(b'leave alone')
        (self.locations.base/'.installation.lock').symlink_to(outside)
        with self.assertRaises(OSError),m.installation_lock(self.locations):pass
        self.assertEqual(outside.read_bytes(),b'leave alone')

    def test_legacy_process_detection_accepts_relative_path_not_command_mentions(self):
        proc=self.root/'proc';proc.mkdir()
        for pid,args in ((10,['/usr/bin/python3','-I',str(self.locations.app/'window.py')]),
                         (11,['python3','window.py']),
                         (12,['python3','-c',str(self.locations.app/'window.py')]),
                         (13,['cat',str(self.locations.app/'window.py')])):
            entry=proc/str(pid);entry.mkdir()
            (entry/'cmdline').write_bytes(b'\0'.join(os.fsencode(a) for a in args)+b'\0')
            (entry/'cwd').symlink_to(self.locations.app)
        self.assertEqual(sorted(m.running_app(self.locations,proc)),[10,11])

    def test_active_legacy_app_or_runtime_lock_blocks_removal_before_admin(self):
        self.installed();before=self.locations.receipt.read_bytes()
        with patch.object(uninstall,'remove_access_files') as admin,patch.object(m,'running_app',return_value=[123]):
            with self.assertRaisesRegex(RuntimeError,'bandeja'):uninstall.uninstall(self.locations,True)
            admin.assert_not_called()
        with m.installation_lock(self.locations,shared=True),patch.object(uninstall,'remove_access_files') as admin:
            with self.assertRaises(RuntimeError):uninstall.uninstall(self.locations,True)
            admin.assert_not_called()
        self.assertEqual(self.locations.receipt.read_bytes(),before)

    def test_uninstall_removes_its_login_entry_but_not_a_foreign_one(self):
        import autostart
        for foreign in (False,True):
            self.installed()
            entry=autostart.entry_path(self.locations.config);entry.parent.mkdir(parents=True,exist_ok=True)
            if foreign:entry.write_text('[Desktop Entry]\nExec=other\n')
            else:autostart.set_enabled(True,self.locations.app/'window.py',self.locations.config)
            with patch.object(uninstall,'systemd_available',return_value=False),patch.object(uninstall.shutil,'which',return_value=None):
                uninstall.uninstall(self.locations)
            self.assertFalse(self.locations.receipt.exists())
            self.assertEqual(entry.exists(),foreign)
            if foreign:self.assertEqual(entry.read_text(),'[Desktop Entry]\nExec=other\n');entry.unlink()

    def test_admin_cancellation_keeps_every_user_file(self):
        self.installed();before=self.locations.receipt.read_bytes()
        with patch.object(uninstall.subprocess,'run',return_value=subprocess.CompletedProcess([],126)) as command:
            with self.assertRaisesRegex(RuntimeError,'cancelada'):uninstall.uninstall(self.locations,True)
            args=command.call_args.args[0]
            self.assertEqual(args[:3],['pkexec','/usr/bin/python3','-I'])
            self.assertFalse(Path(args[3]).exists())
        self.assertEqual(self.locations.receipt.read_bytes(),before)
        self.assertEqual(len(m.removal_plan(self.locations)['remove']),7)
