# SPDX-License-Identifier: GPL-3.0-only
import ast
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from native_grant import NativeGrantFiles,native_rule
from native_lifecycle import NativePackageGate,PACKAGE_LOCK,PACKAGE_STATE
import native_package as package


class PackageLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.files=NativeGrantFiles(Path(self.temporary.name),os.getuid());self.gate=NativePackageGate(self.files)
        self.name='usr/share/dualsense-usb/fixture'
        self.expected={self.name:(hashlib.sha256(b'program').hexdigest(),0o644)}

    def install(self):
        self.gate.begin('deb','one',self.expected)
        path=self.files.path(self.name,create=True);path.write_bytes(b'program');path.chmod(0o644)
        self.gate.finish('deb','one',self.expected)

    def test_transaction_refuses_live_sessions_and_blocks_new_starts_between_scripts(self):
        self.install()
        with self.gate.session('one'):
            with self.assertRaisesRegex(RuntimeError,'is open'):self.gate.begin('deb','two',self.expected)
            self.gate.finish('deb','one',self.expected)
            with self.gate.session('one'):pass
        self.gate.begin('deb','two',self.expected)
        with self.assertRaisesRegex(RuntimeError,'maintenance'):
            with self.gate.session('one'):pass
        self.gate.finish('deb','two',self.expected)
        with self.assertRaises(RuntimeError):
            with self.gate.session('one'):pass
        with self.gate.session('two'):pass

    def test_partial_update_remains_blocked_until_verified_repair(self):
        self.install();self.gate.begin('deb','two',self.expected)
        self.files.path(self.name).write_bytes(b'incomplete')
        with self.assertRaisesRegex(ValueError,'missing or changed'):self.gate.finish('deb','two',self.expected)
        self.assertEqual(self.gate.state()['phase'],'maintenance')
        self.files.path(self.name).write_bytes(b'program');self.gate.finish('deb','two',self.expected)
        with self.assertRaisesRegex(FileNotFoundError,'body'):
            with self.gate.session('two'):raise FileNotFoundError('body')

    def test_no_unmanaged_overwrite_or_mixed_manager(self):
        path=self.files.path(self.name,create=True);path.write_bytes(b'foreign')
        with self.assertRaisesRegex(ValueError,'Unmanaged'):self.gate.begin('deb','one',self.expected)
        self.assertEqual(path.read_bytes(),b'foreign');self.assertIsNone(self.gate.state())
        path.unlink();self.install()
        for action in (lambda:self.gate.begin('rpm','two'),lambda:self.gate.finish('rpm','one',self.expected),lambda:self.gate.removed('rpm','one')):
            with self.assertRaisesRegex(ValueError,'another package manager'):action()

    def test_removal_only_revokes_canonical_native_grants(self):
        self.install()
        for uid,data in [(1000,native_rule((1000,'alice'))),(1001,b'local custom rule\n')]:
            path=self.files.path(self.files.relative('rule',uid),create=True);path.write_bytes(data);path.chmod(0o644)
        with patch.object(self.files,'lock',side_effect=RuntimeError('session busy')):
            with self.assertRaisesRegex(RuntimeError,'session busy'):self.gate.prepare_remove('deb','one')
        self.assertIsNotNone(self.files.read(self.files.relative('rule',1000)))
        self.assertEqual(self.gate.state()['phase'],'maintenance')
        self.gate.finish('deb','one',self.expected)
        self.gate.prepare_remove('deb','one');self.gate.removed('deb','one')
        self.assertIsNone(self.files.read(self.files.relative('rule',1000)))
        self.assertEqual(self.files.read(self.files.relative('rule',1001))[0],b'local custom rule\n')
        self.assertEqual(self.files.path(self.name).read_bytes(),b'program') # manager owns removal
        with self.assertRaises(RuntimeError):
            with self.gate.session('one'):pass
        self.gate.removed('deb','one')

    def test_umask_and_untrusted_lock_or_state(self):
        previous=os.umask(0o077)
        try:self.install()
        finally:os.umask(previous)
        self.assertEqual(self.files.read(PACKAGE_LOCK),(b'',0o644))
        self.assertEqual(self.files.read(PACKAGE_STATE)[1],0o644)
        lock=self.files.path(PACKAGE_LOCK);lock.chmod(0o666)
        with self.assertRaises(ValueError):self.gate.begin('deb','two')
        lock.chmod(0o644)
        state=self.files.path(PACKAGE_STATE);state.write_text('{"format":1}')
        with self.assertRaises(ValueError):self.gate.begin('deb','two')

    def test_failed_state_sync_never_exposes_an_unverified_program(self):
        self.install()
        with patch('native_lifecycle.os.replace',side_effect=OSError('write failed')):
            with self.assertRaises(OSError):self.gate.begin('deb','two')
        with self.gate.session('one'):pass
        self.gate.begin('deb','two');self.files.path(self.name).unlink()
        with self.assertRaises(ValueError):self.gate.finish('deb','two',self.expected)
        self.assertFalse(list(self.files.path(PACKAGE_STATE).parent.glob('.package-*')))

    def test_native_layout_entrypoints_metadata_and_self_contained_scriptlets(self):
        for manager,phases in [('deb',['preinst','postinst','prerm','postrm']),('rpm',['pre','posttrans','preun','postun'])]:
            files=package.payloads(manager);expected=package.expected_files(files)
            for name in package.ENTRYPOINTS:
                data=files[package.PREFIX+name][0].decode()
                self.assertIn('hold_native_package('+repr(package.VERSION)+')',data)
                ast.parse(data)
            self.assertIn('usr/lib/systemd/user/dualsense-usb-system.service',files)
            self.assertIn(b'RestartPreventExitStatus=78',files['usr/lib/systemd/user/dualsense-usb-system.service'][0])
            self.assertNotIn('etc/polkit-1/rules.d/49-dualsense-usb-native-1000.rules',files)
            for phase in phases:
                script=package.maintainer_script(manager,phase,expected)
                ast.parse(script);self.assertNotIn('from native_grant import',script)
                self.assertNotIn('from native_lifecycle import',script)
            self.assertTrue(all(not name.startswith(('home/','usr/local/')) for name in files))
        for value in ('Someone\nDepends: anything','Name <a@b>\n','%macro <a@b>'):
            with self.assertRaises(ValueError):package.check_metadata(value,1)
        package.check_metadata('Local test <test@example.invalid>',1)


if __name__=='__main__':unittest.main()
