# SPDX-License-Identifier: GPL-3.0-only
"""Administrative transactions in an owned temporary tree. No root or hardware."""
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch
import access_admin as a


class AccessAdminTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.proc=self.root/'proc';self.proc.mkdir()
        self.reload=Mock()
        self.files=a.AccessFiles(self.root,os.getuid(),self.reload,self.proc)
        self.actor=(1000,'fixture')
        self.helper='#!/usr/bin/python3\nprint("fixture")\n'
        self.digest=a.access_digest(self.helper.encode())

    def snapshot(self):return {name:self.files.read(name) for name in a.ACCESS_PATHS}

    def test_install_receipt_modes_and_idempotent_removal(self):
        self.files.install(self.helper,self.actor)
        record=self.files.receipt()
        self.assertEqual(record['owner_uid'],1000)
        for name,(data,mode) in a.access_payloads(self.helper,'fixture').items():
            self.assertEqual(self.files.read(name),(data,mode))
            self.assertEqual(record['files'][name],a.access_digest(data))
        self.assertEqual(stat.S_IMODE(self.files.path('receipt').stat().st_mode),0o600)
        self.assertEqual(set(self.files.remove(self.digest,self.actor)),set(a.ACCESS_PATHS)-{'receipt'})
        self.assertTrue(all(v is None for v in self.snapshot().values()))
        self.assertEqual(self.files.remove(self.digest,self.actor),[])

    def test_different_account_cannot_replace_or_remove_existing_grant(self):
        self.files.install(self.helper,self.actor);before=self.snapshot()
        for operation in (lambda:self.files.install('changed',(1001,'other')),
                          lambda:self.files.remove(self.digest,(1001,'other'))):
            with self.assertRaisesRegex(ValueError,'outra conta'):operation()
            self.assertEqual(self.snapshot(),before)

    def test_modified_administrative_file_refuses_entire_removal(self):
        self.files.install(self.helper,self.actor)
        self.files.path('udev').write_text('local customization\n')
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'nada foi removido'):self.files.remove(self.digest,self.actor)
        self.assertEqual(self.snapshot(),before)

    def test_existing_helper_session_prevents_removal(self):
        self.files.install(self.helper,self.actor);before=self.snapshot()
        entry=self.proc/'42';entry.mkdir()
        (entry/'cmdline').write_bytes(b'/usr/bin/python3\0-I\0'+os.fsencode(self.files.path('helper'))+b'\0--exclusive\0')
        with self.assertRaisesRegex(ValueError,'sessões'):self.files.remove(self.digest,self.actor)
        self.assertEqual(self.snapshot(),before)

    def test_install_reload_failure_restores_previous_files_and_receipt(self):
        self.files.install(self.helper,self.actor);before=self.snapshot()
        self.reload.side_effect=[OSError('fixture reload failure'),None]
        with self.assertRaisesRegex(RuntimeError,'anteriores restaurados'):self.files.install('new helper',self.actor)
        self.assertEqual(self.snapshot(),before)

    def test_first_install_failure_leaves_no_access_files(self):
        self.reload.side_effect=[OSError('fixture reload failure'),None]
        with self.assertRaisesRegex(RuntimeError,'anteriores restaurados'):self.files.install(self.helper,self.actor)
        self.assertTrue(all(v is None for v in self.snapshot().values()))

    def test_midway_write_failure_restores_completed_writes(self):
        self.files.install(self.helper,self.actor);before=self.snapshot()
        original_write=self.files.write
        calls=[]
        def fail_once(name,data,mode):
            calls.append(name)
            if len(calls)==3:raise OSError('fixture disk failure')
            return original_write(name,data,mode)
        with patch.object(self.files,'write',side_effect=fail_once):
            with self.assertRaisesRegex(RuntimeError,'anteriores restaurados'):self.files.install('new helper',self.actor)
        self.assertEqual(self.snapshot(),before)

    def test_failed_removal_restores_files_and_reports_failed_reload_separately(self):
        self.files.install(self.helper,self.actor);before=self.snapshot()
        self.reload.side_effect=[OSError('fixture failure'),None]
        with self.assertRaisesRegex(RuntimeError,'anteriores restaurados'):self.files.remove(self.digest,self.actor)
        self.assertEqual(self.snapshot(),before)
        self.reload.side_effect=OSError('reload still unavailable')
        with self.assertRaisesRegex(RuntimeError,'restauração também'):self.files.remove(self.digest,self.actor)
        self.assertEqual(self.snapshot(),before)

    def test_legacy_access_requires_matching_account_and_every_file_hash(self):
        for name,(data,mode) in a.access_payloads(self.helper,'fixture').items():self.files.write(name,data,mode)
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'outra conta'):self.files.remove(self.digest,(1001,'other'))
        with self.assertRaisesRegex(ValueError,'modificado'):self.files.remove('0'*64,self.actor)
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(len(self.files.remove(self.digest,self.actor)),4)

    def test_symlinks_or_writable_admin_parents_are_never_followed(self):
        outside=self.root/'outside';outside.mkdir()
        (self.root/'usr').symlink_to(outside,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'Diretório'):self.files.install(self.helper,self.actor)
        self.assertEqual(list(outside.iterdir()),[])
        (self.root/'usr').unlink();(self.root/'usr').mkdir(mode=0o777)
        (self.root/'usr').chmod(0o777)
        with self.assertRaisesRegex(ValueError,'Diretório'):self.files.install(self.helper,self.actor)
        (self.root/'usr').chmod(0o755)
        self.files.install(self.helper,self.actor)
        path=self.files.path('helper');path.unlink();path.symlink_to(outside/'target')
        with self.assertRaisesRegex(ValueError,'Arquivo administrativo'):self.files.remove(self.digest,self.actor)
        self.assertFalse((outside/'target').exists())

    def test_malformed_receipt_is_not_trusted_as_a_list_of_paths(self):
        self.files.install(self.helper,self.actor);before=self.snapshot()
        for record in ({'format':True,'owner_uid':1000,'files':{}},
                       {'format':1,'owner_uid':1000,'files':{'/tmp/anything':'0'*64}}):
            self.files.write('receipt',json.dumps(record).encode(),0o600)
            with self.assertRaisesRegex(ValueError,'Registro'):self.files.remove(self.digest,self.actor)
            for name in set(a.ACCESS_PATHS)-{'receipt'}:self.assertEqual(self.files.read(name),before[name])

    def test_only_one_administrative_transaction_at_a_time(self):
        with self.files.lock():
            with self.assertRaisesRegex(ValueError,'Outra configuração'):self.files.install(self.helper,self.actor)

    def test_entrypoint_requires_root_and_real_pkexec_user(self):
        with patch.object(a.os,'geteuid',return_value=1000):
            with self.assertRaises(ValueError):a.access_actor()
        with patch.object(a.os,'geteuid',return_value=0):
            for value in ('','0','-1','1x','1000\n'):
                with patch.dict(os.environ,{'PKEXEC_UID':value}):
                    with self.assertRaises(ValueError):a.access_actor()
            with patch.dict(os.environ,{'PKEXEC_UID':'1000'}),patch.object(a.pwd,'getpwuid',return_value=Mock(pw_name='fixture')):
                self.assertEqual(a.access_actor(),self.actor)
