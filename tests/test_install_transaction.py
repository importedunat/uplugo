# SPDX-License-Identifier: GPL-3.0-only
"""Real filesystem exchanges and SIGKILL at commit/rollback boundaries, no USB."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from maintenance import Locations, installation_lock, PendingInstallation, removal_plan
import install_transaction as tx

CHILD = r'''
import os,signal,sys
from pathlib import Path
from maintenance import Locations,installation_lock
import install_transaction as tx
root=Path(sys.argv[1]);locations=Locations(root/'data',Path(sys.argv[4]))
def stop(step):
    if step==sys.argv[3]:os.kill(os.getpid(),signal.SIGKILL)
tx.checkpoint=stop
with installation_lock(locations):
    if sys.argv[2]=='recover':tx.recover(locations)
    else:
        sources={p.name:p for p in (root/'new-source').iterdir()}
        tx.install_files(locations,sources,{key:('new '+key).encode() for key in ('desktop','icon','service')},'new')
'''


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.locations=Locations(self.root/'data',self.root/'config')
        self.new=self.source('new')

    def source(self,version,obsolete=False):
        folder=self.root/(version+'-source');folder.mkdir()
        (folder/'window.py').write_text('VERSION = '+repr(version)+'\n')
        (folder/'build_helper.py').write_text('from pathlib import Path\nroot=Path(__file__).parent\n'
             'for name in ("install-access.py","remove-access.py"):(root/name).write_text("generated fixture")\n')
        if obsolete:(folder/'obsolete.py').write_text('old owned file')
        return {p.name:p for p in folder.iterdir()}

    def install(self,sources=None,version='new'):
        with installation_lock(self.locations):
            tx.install_files(self.locations,sources or self.new,{key:(version+' '+key).encode() for key in ('desktop','icon','service')},version)

    def recover(self):
        with installation_lock(self.locations):return tx.recover(self.locations)

    def snapshot(self):
        return {'app':tx.tree_state(self.locations.app),
                **{name:tx.file_state(tx.target(self.locations,name)) for name in tx.ALIASES}}

    def killed(self,phase,operation='install'):
        result=subprocess.run([sys.executable,'-c',CHILD,str(self.root),operation,phase,str(self.locations.config)],capture_output=True,timeout=15)
        self.assertEqual(result.returncode,-signal.SIGKILL,result.stdout.decode()+result.stderr.decode())

    def test_success_preserves_unknown_and_personal_files_removes_obsolete_owned_code(self):
        old=self.source('old',obsolete=True);self.install(old,'old')
        personal=[self.locations.app/'personal.txt',self.locations.config/'dualsense-usb/controllers.json',
                  self.locations.base/'appearance-library/photo.png',self.root/'state/history.json']
        for path in personal:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'keep')
        linked=self.root/'outside';linked.write_bytes(b'outside')
        (self.locations.app/'custom-link').symlink_to(linked)
        self.install()
        for path in personal:self.assertEqual(path.read_bytes(),b'keep')
        self.assertTrue((self.locations.app/'custom-link').is_symlink())
        self.assertFalse((self.locations.app/'obsolete.py').exists())
        self.assertEqual(linked.read_bytes(),b'outside')
        self.assertEqual(json.loads(self.locations.receipt.read_text())['version'],'new')
        self.assertIn('app/'+tx.GENERATION,removal_plan(self.locations)['remove'])
        self.assertFalse(self.locations.pending.exists())
        self.assertEqual(list(self.locations.base.glob('.installation-*')),[])

    def test_sigkill_before_commit_restores_exact_previous_installation(self):
        self.install(self.source('old'),'old');expected=self.snapshot()
        for point in ('bundle-created','building','prepared','app','desktop','icon','service','receipt'):
            with self.subTest(point=point):
                self.killed(point)
                self.assertTrue(self.locations.pending.exists())
                with self.assertRaises(PendingInstallation),installation_lock(self.locations,shared=True):pass
                with self.assertRaises(PendingInstallation):removal_plan(self.locations)
                self.recover()
                self.assertEqual(self.snapshot(),expected)
                self.assertEqual(self.recover(),'none')

    def test_first_install_is_removed_after_interruption(self):
        for point in ('prepared','app','desktop','icon','service','receipt'):
            with self.subTest(point=point):
                self.killed(point);self.assertEqual(self.recover(),'removed')
                self.assertIsNone(tx.tree_state(self.locations.app))
                self.assertTrue(all(tx.file_state(tx.target(self.locations,k)) is None for k in tx.ALIASES))

    def test_committed_update_survives_interrupted_cleanup(self):
        for point in ('committed','cleanup-app','cleanup-new','cleanup-old','cleanup-bundle'):
            with self.subTest(point=point):
                self.killed(point)
                current=self.snapshot()
                self.assertIn("'new'",(self.locations.app/'window.py').read_text())
                self.assertEqual(self.recover(),'completed')
                self.assertEqual(self.snapshot(),current)
                self.assertEqual(self.recover(),'none')

    def test_rollback_can_itself_be_interrupted_and_repeated(self):
        self.install(self.source('old'),'old');expected=self.snapshot()
        for point in ('rollback-app','rollback-desktop','rollback-icon','rollback-service','rollback-receipt','rolled-back','cleanup-app','cleanup-bundle'):
            with self.subTest(point=point):
                self.killed('receipt');self.killed(point,'recover')
                self.recover();self.assertEqual(self.snapshot(),expected)

    def test_write_error_and_missing_exchange_support_preserve_old_install(self):
        self.install(self.source('old'),'old');expected=self.snapshot()
        original=tx.atomic_write
        def fail_once(path,*args):
            if path==self.locations.target('service') and args[0]==b'new service':raise OSError('disk full')
            return original(path,*args)
        with patch.object(tx,'atomic_write',side_effect=fail_once):
            with self.assertRaisesRegex(OSError,'disk full'):self.install()
        self.assertEqual(self.snapshot(),expected)
        with patch.object(tx,'exchange',side_effect=OSError('unsupported')):
            with self.assertRaisesRegex(OSError,'unsupported'):self.install()
        self.assertEqual(self.snapshot(),expected)
        self.assertFalse(self.locations.pending.exists())

    def test_failed_helper_preparation_never_touches_installation(self):
        self.install(self.source('old'),'old');expected=self.snapshot()
        self.new['build_helper.py'].write_text('raise RuntimeError("failed build")')
        with self.assertRaises(subprocess.CalledProcessError):self.install()
        self.assertEqual(self.snapshot(),expected)
        self.assertFalse(self.locations.pending.exists())

    def test_modified_new_installation_or_backup_is_not_destroyed_on_recovery(self):
        self.install(self.source('old'),'old');self.killed('app')
        original=(self.locations.app/'window.py').read_bytes()
        (self.locations.app/'window.py').write_bytes(b'new user edit')
        with self.assertRaisesRegex(ValueError,'mudaram'):self.recover()
        self.assertEqual((self.locations.app/'window.py').read_bytes(),b'new user edit')
        (self.locations.app/'window.py').write_bytes(original)
        self.locations.target('service').write_bytes(b'user service')
        with self.assertRaisesRegex(ValueError,'alterado'):self.recover()
        self.assertTrue(self.locations.pending.exists())
        self.assertEqual(self.locations.target('service').read_bytes(),b'user service')

    def test_invalid_journal_and_external_links_cannot_redirect_recovery(self):
        self.install(self.source('old'),'old');expected=self.snapshot()
        outside=self.root/'outside';outside.write_bytes(b'outside')
        self.locations.pending.symlink_to(outside)
        with self.assertRaises(ValueError):self.recover()
        self.locations.pending.unlink()
        self.killed('prepared');record=json.loads(self.locations.pending.read_text())
        changed=dict(record,id='../outside');self.locations.pending.write_text(json.dumps(changed))
        with self.assertRaises(ValueError):self.recover()
        self.locations.pending.write_text(json.dumps(record))
        self.locations.target('icon').unlink();self.locations.target('icon').symlink_to(outside)
        with self.assertRaises(ValueError):self.recover()
        self.assertEqual(outside.read_bytes(),b'outside')
        self.assertEqual(tx.tree_state(self.locations.app),expected['app'])

    def test_data_and_config_on_different_filesystems(self):
        shared=Path('/dev/shm')
        if not shared.is_dir() or not os.access(shared,os.W_OK):
            self.skipTest('No separate writable tmpfs in this environment')
        if shared.stat().st_dev==self.root.stat().st_dev:
            self.skipTest('Temporary paths share a filesystem')
        with tempfile.TemporaryDirectory(prefix='dualsense-config-test-',dir=shared) as directory:
            self.locations=Locations(self.root/'data',Path(directory)/'config')
            self.install(self.source('old'),'old');before=self.snapshot()
            self.killed('service');self.assertEqual(self.recover(),'restored')
            self.assertEqual(self.snapshot(),before)
            self.install();self.assertEqual(json.loads(self.locations.receipt.read_text())['version'],'new')

    def test_linked_destination_is_rejected_before_staging(self):
        self.install(self.source('old'),'old')
        outside=self.root/'outside';outside.write_bytes(b'outside')
        path=self.locations.app/'window.py';path.unlink();path.symlink_to(outside)
        with self.assertRaises(ValueError):self.install()
        self.assertEqual(outside.read_bytes(),b'outside')
        self.assertFalse(self.locations.pending.exists())
