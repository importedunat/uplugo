# SPDX-License-Identifier: GPL-3.0-only
"""Native grant boundaries in private files. Never authorizes or opens USB."""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock,patch
import xml.etree.ElementTree as ET
from build_helper import native_payloads,native_helper_source
import native_grant as grant
from native_access import NativeAccess
import native_status


class NativeAccessTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.files=grant.NativeGrantFiles(self.root,os.getuid())
        self.alice=(1000,'alice');self.bob=(1001,'bob')
        self.payloads=native_payloads();self.expected={}
        for name,(data,mode) in self.payloads.items():
            path=self.files.path(name,create=True);path.write_bytes(data);path.chmod(mode)
            if name!=grant.NATIVE_ADMIN_PATH:self.expected[name]=(hashlib.sha256(data).hexdigest(),mode)
        self.admin=NativeAccess(self.files,self.expected)
        self.package_before={name:self.files.read(name,1024*1024) for name in self.payloads}

    def rule(self,actor):return self.files.read(self.files.relative('rule',actor[0]))

    def package_unchanged(self):
        self.assertEqual(self.package_before,{name:self.files.read(name,1024*1024) for name in self.payloads})

    def test_two_accounts_grant_revoke_and_idempotence_without_touching_package(self):
        for actor in (self.alice,self.bob):
            self.assertTrue(self.admin.apply('install',actor))
            self.assertFalse(self.admin.apply('install',actor))
            self.assertEqual(self.rule(actor),(grant.native_rule(actor),0o644))
            self.assertEqual(self.files.read(self.files.relative('lock',actor[0])),(b'',0o600))
            with self.files.session(actor):pass
        bob_before=self.rule(self.bob)
        self.assertTrue(self.admin.apply('remove',self.alice));self.assertFalse(self.admin.apply('remove',self.alice))
        self.assertIsNone(self.rule(self.alice));self.assertEqual(self.rule(self.bob),bob_before)
        with self.files.session(self.bob):pass
        with self.assertRaises(ValueError):
            with self.files.session(self.alice):pass
        self.package_unchanged()

    def test_restrictive_umask_keeps_rules_readable_and_locks_private(self):
        before=os.umask(0o077)
        try:self.admin.apply('install',self.alice)
        finally:os.umask(before)
        self.assertEqual(self.files.path(self.files.relative('rule',1000)).parent.stat().st_mode&0o777,0o755)
        self.assertEqual(self.rule(self.alice)[1],0o644)
        self.assertEqual(self.files.read(self.files.relative('lock',1000)),(b'',0o600))
        # A canonical grant made unreadable to polkitd must be repairable after
        # explicit authorization, not incorrectly treated as already configured.
        self.files.path(self.files.relative('rule',1000)).chmod(0o600)
        self.assertTrue(self.admin.apply('install',self.alice))
        self.assertEqual(self.rule(self.alice)[1],0o644)

    def test_active_account_blocks_its_revoke_but_not_other_accounts(self):
        self.admin.apply('install',self.alice);self.admin.apply('install',self.bob)
        with self.files.session(self.alice):
            self.assertFalse(self.admin.apply('install',self.alice))
            with self.assertRaisesRegex(RuntimeError,'sessões USB'):self.admin.apply('remove',self.alice)
            self.assertTrue(self.admin.apply('remove',self.bob))
            self.assertTrue(self.admin.apply('install',self.bob))
            with self.files.session(self.alice):pass  # More than one controller.
        self.assertTrue(self.admin.apply('remove',self.alice))
        # A device disappearing inside a session is not misreported as a grant error.
        with self.assertRaisesRegex(FileNotFoundError,'device unplugged'):
            with self.files.session(self.bob):raise FileNotFoundError('device unplugged')
        self.package_unchanged()

    def test_uid_and_username_must_both_match_and_rename_requires_admin(self):
        self.admin.apply('install',self.alice)
        for actor in ((1001,'alice'),(1000,'renamed')):
            with self.assertRaises(ValueError):
                with self.files.session(actor):pass
        self.admin.apply('install',(1000,'renamed'))
        with self.files.session((1000,'renamed')):pass
        self.assertEqual(grant.native_rule_actor(self.rule(self.alice)[0],1000),(1000,'renamed'))

    def test_custom_or_wrong_account_rule_is_preserved_for_install_and_remove(self):
        self.admin.apply('install',self.alice)
        path=self.files.path(self.files.relative('rule',1000))
        for content in (b'local admin customization\n',grant.native_rule(self.bob),grant.native_rule(self.alice)+b'// changed\n'):
            path.write_bytes(content)
            for action in ('install','remove'):
                with self.assertRaises(ValueError):self.admin.apply(action,self.alice)
                self.assertEqual(path.read_bytes(),content)
        self.package_unchanged()

    def test_missing_changed_or_wrong_mode_package_cannot_create_a_grant(self):
        name=grant.NATIVE_HELPER_PATH;path=self.root/name;data,mode=self.payloads[name]
        for changed in ('missing','bytes','mode'):
            if changed=='missing':path.unlink()
            elif changed=='bytes':path.write_text('modified');path.chmod(mode)
            else:path.write_bytes(data);path.chmod(0o644)
            with self.assertRaisesRegex(ValueError,'pacote'):self.admin.apply('install',self.alice)
            self.assertIsNone(self.rule(self.alice))
        path.write_bytes(data);path.chmod(mode)
        self.admin.apply('install',self.alice);path.unlink()
        self.assertTrue(self.admin.apply('remove',self.alice),'Revocation must work even if package files are missing')

    def test_symlinks_hardlinks_fifo_writable_parent_and_foreign_owner_refused(self):
        self.admin.apply('install',self.alice)
        path=self.files.path(self.files.relative('rule',1000));original=path.read_bytes()
        outside=self.root/'outside';outside.write_bytes(original)
        path.unlink();path.symlink_to(outside)
        with self.assertRaises((OSError,ValueError)):self.admin.apply('remove',self.alice)
        self.assertEqual(outside.read_bytes(),original)
        path.unlink();os.link(outside,path)
        with self.assertRaises(ValueError):self.admin.apply('remove',self.alice)
        path.unlink();os.mkfifo(path)
        with self.assertRaises(ValueError):self.admin.apply('remove',self.alice)
        path.unlink();path.write_bytes(original);path.chmod(0o644)
        path.parent.chmod(0o777)
        with self.assertRaises(ValueError):self.admin.apply('remove',self.alice)
        path.parent.chmod(0o755)
        other=grant.NativeGrantFiles(self.root,os.getuid()+1)
        with self.assertRaises(ValueError):other.read(self.files.relative('rule',1000))
        lock=self.files.path(self.files.relative('lock',1000));lock.chmod(0o644)
        with self.assertRaises(ValueError):
            with self.files.session(self.alice):pass

    def test_replace_or_sync_failure_restores_previous_rule_only(self):
        self.admin.apply('install',self.alice);self.admin.apply('install',self.bob)
        before=self.rule(self.alice);bob=self.rule(self.bob)
        for action in ('install','remove'):
            actor=(1000,'renamed') if action=='install' else self.alice
            with patch.object(self.admin,'sync_parent',side_effect=[OSError('disk fixture'),None]):
                with self.assertRaisesRegex(RuntimeError,'anterior foi restaurada'):self.admin.apply(action,actor)
            self.assertEqual(self.rule(self.alice),before);self.assertEqual(self.rule(self.bob),bob)
        with patch.object(self.admin,'sync_parent',side_effect=OSError('disk still failed')):
            with self.assertRaisesRegex(RuntimeError,'restauração precisa'):self.admin.apply('remove',self.alice)
        self.assertEqual(self.rule(self.alice),before)
        self.assertFalse(list((self.root/'etc/polkit-1/rules.d').glob('.dualsense-native-*')))
        self.package_unchanged()

    def test_killed_writer_leaves_old_or_new_complete_grant_and_can_retry(self):
        self.admin.apply('install',self.alice)
        for phase,expected_actor in (('before',self.alice),('after',(1000,'renamed'))):
            self.admin.apply('install',self.alice)
            code='''import os,signal,sys,json
from pathlib import Path
from native_grant import NativeGrantFiles
from native_access import NativeAccess
files=NativeGrantFiles(Path(sys.argv[1]),os.getuid())
admin=NativeAccess(files,json.loads(sys.argv[2]))
original=os.replace
def boundary(*args):
    if sys.argv[3]=='after':original(*args)
    os.kill(os.getpid(),signal.SIGKILL)
os.replace=boundary
admin.apply('install',(1000,'renamed'))
'''
            result=subprocess.run([sys.executable,'-c',code,str(self.root),json.dumps(self.expected),phase],timeout=5)
            self.assertEqual(result.returncode,-9)
            self.assertEqual(self.rule(self.alice)[0],grant.native_rule(expected_actor))
            self.admin.apply('install',self.alice)
            with self.files.session(self.alice):pass
        self.package_unchanged()

    def test_actor_and_cli_contract_never_accept_supplied_user_or_target_paths(self):
        with patch.object(grant.os,'geteuid',return_value=1000):
            with self.assertRaises(ValueError):grant.native_actor()
        with patch.object(grant.os,'geteuid',return_value=0):
            for value in ('','0','-1','1000\n','4294967295','999999999999999999'):
                with patch.dict(os.environ,{'PKEXEC_UID':value}),patch.object(grant.pwd,'getpwuid',return_value=Mock(pw_name='alice')):
                    with self.assertRaises(ValueError):grant.native_actor()
            with patch.dict(os.environ,{'PKEXEC_UID':'1000'}),patch.object(grant.pwd,'getpwuid',return_value=Mock(pw_name='alice')):
                self.assertEqual(grant.native_actor(),self.alice)
        script=self.root/grant.NATIVE_ADMIN_PATH
        for args in ([],['install','--root','/tmp'],['remove','1001'],['other']):
            result=subprocess.run([sys.executable,'-I',str(script),*args],capture_output=True,timeout=5)
            self.assertNotEqual(result.returncode,0);self.assertIn(b'inv',result.stderr.lower())
        self.assertIsNone(self.rule(self.alice));self.package_unchanged()

    def test_policy_only_grants_runtime_after_admin_choice_and_embedded_code_is_self_contained(self):
        policy=ET.fromstring(self.payloads[grant.NATIVE_POLICY_PATH][0])
        actions={item.attrib['id']:item for item in policy.findall('action')}
        self.assertEqual(set(actions),{grant.NATIVE_CONTROL_ACTION,grant.NATIVE_MANAGE_ACTION})
        self.assertEqual(actions[grant.NATIVE_CONTROL_ACTION].findtext('defaults/allow_active'),'no')
        self.assertEqual(actions[grant.NATIVE_MANAGE_ACTION].findtext('defaults/allow_active'),'auth_admin')
        for item in actions.values():
            self.assertEqual(item.findtext('defaults/allow_inactive'),'no');self.assertEqual(item.findtext('defaults/allow_any'),'no')
        for action,path in ((grant.NATIVE_CONTROL_ACTION,grant.NATIVE_HELPER_PATH),(grant.NATIVE_MANAGE_ACTION,grant.NATIVE_ADMIN_PATH)):
            self.assertEqual(actions[action].find('annotate').text,'/'+path)
            self.assertEqual({e.attrib.get('{http://www.w3.org/XML/1998/namespace}lang') for e in actions[action].findall('message')},{None,'pt_BR','es'})
        for name in (grant.NATIVE_HELPER_PATH,grant.NATIVE_ADMIN_PATH):
            source=self.payloads[name][0].decode();tree=ast.parse(source)
            self.assertTrue(source.startswith('#!/usr/bin/python3 -I\n'))
            self.assertFalse(any(isinstance(n,ast.ImportFrom) and n.module in ('native_grant','native_access','dualsense') for n in ast.walk(tree)))
        escaped=(1000,'a"; polkit.Result.YES; //\n')
        self.assertEqual(grant.native_rule_actor(grant.native_rule(escaped),1000),escaped)
        self.assertEqual(len([line for line in grant.native_rule(escaped).splitlines() if b'polkit.addRule' in line]),1)
        self.assertNotIn(grant.NATIVE_MANAGE_ACTION.encode(),grant.native_rule(self.alice))


class NativeStatusTests(unittest.TestCase):
    def test_probe_never_requests_interaction_and_uses_pid_start_time_uid(self):
        stat='1 (name with ) paren) '+' '.join(['S']+['0']*18+['123456'])
        with patch.object(Path,'read_text',return_value=stat),patch.object(native_status.os,'getpid',return_value=42), \
             patch.object(native_status.os,'getuid',return_value=1000), \
             patch.object(native_status.subprocess,'run',return_value=subprocess.CompletedProcess([],0)) as run:
            self.assertTrue(native_status.native_authorized())
            self.assertEqual(run.call_args.args[0],['/usr/bin/pkcheck','--action-id',grant.NATIVE_CONTROL_ACTION,'--process','42,123456,1000'])
            self.assertEqual(run.call_args.kwargs['stdin'],subprocess.DEVNULL)
            self.assertEqual(run.call_args.kwargs['timeout'],3)
            for result in (subprocess.CompletedProcess([],1),FileNotFoundError(),subprocess.TimeoutExpired('pkcheck',3)):
                run.side_effect=result if isinstance(result,Exception) else None;run.return_value=result
                self.assertFalse(native_status.native_authorized())

    def test_slow_probe_is_async_cached_and_stale_result_cannot_overwrite_confirmation(self):
        entered=threading.Event();release=threading.Event();done=threading.Event()
        def slow():entered.set();release.wait(3);done.set();return False
        status=native_status.NativeAuthorization(slow)
        started=time.monotonic();self.assertFalse(status.ready());self.assertLess(time.monotonic()-started,.2)
        self.assertTrue(entered.wait(1))
        with patch.object(status,'probe',return_value=True) as probe:
            self.assertTrue(status.confirm());probe.assert_called_once()
            self.assertTrue(status.ready());probe.assert_called_once()
        release.set();self.assertTrue(done.wait(1))
        # Wait for the old worker to finish its store, which must be ignored.
        time.sleep(.03);self.assertTrue(status.ready())

    def test_confirmation_retries_rule_reload_and_clears_failed_state(self):
        probe=Mock(side_effect=[False,False,True]);status=native_status.NativeAuthorization(probe)
        with patch.object(native_status.time,'sleep'):
            self.assertTrue(status.confirm());self.assertEqual(probe.call_count,3)
        status.probe=Mock(return_value=False)
        with patch.object(native_status.time,'sleep'):
            self.assertFalse(status.confirm());self.assertFalse(status.ready())
        self.assertFalse(status._running)


if __name__=='__main__':unittest.main()
