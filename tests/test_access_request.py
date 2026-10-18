# SPDX-License-Identifier: GPL-3.0-only
import ast
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
import os
import threading
from types import SimpleNamespace
from unittest.mock import patch
import access_request as request
import build_helper


class AccessRequestTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='dualsense-readonly-request-')
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.source=self.root/'read only program';self.source.mkdir()
        names=['dualsense.py','input_state.py','motion_state.py','usb_charge.py','broker.py','access_admin.py',
               'packaging/install-access.py.in','packaging/remove-access.py.in']
        for name in names:
            target=self.source/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(build_helper.BASE/name,target);target.chmod(0o444)
        for path in (self.source/'packaging',self.source):path.chmod(0o555)
        self.before={p.relative_to(self.source):p.read_bytes() for p in self.source.rglob('*') if p.is_file()}
        self.addCleanup(self.restore_permissions)
        mock=patch.object(build_helper,'BASE',self.source);mock.start();self.addCleanup(mock.stop)

    def restore_permissions(self):
        for path in (self.source,self.source/'packaging'):path.chmod(0o755)

    def unchanged(self):
        self.assertEqual({p.relative_to(self.source):p.read_bytes() for p in self.source.rglob('*') if p.is_file()},self.before)

    def test_read_only_sources_generate_self_contained_private_requests(self):
        for action in ('install','remove'):
            with request.prepare_access(action) as prepared:
                script=Path(prepared.command[-1]);folder=script.parent
                self.assertEqual(prepared.command[:3],('pkexec','/usr/bin/python3','-I'))
                self.assertEqual(stat.S_IMODE(folder.stat().st_mode),0o700)
                self.assertEqual(stat.S_IMODE(script.stat().st_mode),0o600)
                source=script.read_text();ast.parse(source)
                self.assertNotIn('@ACCESS_SOURCE@',source)
                self.assertNotIn('@HELPER_SOURCE@',source)
                self.assertNotIn('@LEGACY_HELPER_HASH@',source)
                self.assertNotIn('import access_admin',source)
                self.assertEqual(prepared.expected_helper is not None,action=='install')
                self.assertNotIn(self.source,script.parents)
            self.assertFalse(folder.exists())
        self.unchanged()

    def test_simultaneous_requests_have_independent_lifetimes(self):
        with request.prepare_access('install') as first:
            first_path=Path(first.command[-1])
            with request.prepare_access('remove') as second:
                second_path=Path(second.command[-1]);self.assertNotEqual(first_path.parent,second_path.parent)
                self.assertTrue(first_path.exists() and second_path.exists())
            self.assertFalse(second_path.exists());self.assertTrue(first_path.exists())
        self.assertFalse(first_path.exists());self.unchanged()

    def test_authorization_outcomes_keep_script_until_exit_then_clean_it(self):
        for code,interactive in ((code,interactive) for code in (0,1,126,127) for interactive in (False,True)):
            observed=[]
            def runner(command,**kwargs):
                path=Path(command[-1]);self.assertTrue(path.exists());observed.append(path)
                self.assertNotIn('shell',kwargs)
                if interactive:
                    self.assertNotIn('stdin',kwargs);self.assertNotIn('capture_output',kwargs)
                else:self.assertEqual(kwargs['stdin'],subprocess.DEVNULL)
                return subprocess.CompletedProcess(command,code,'result','detail')
            with patch.object(request.subprocess,'run',side_effect=runner):
                result,helper=request.run_access('install',interactive=interactive)
            self.assertEqual((result.returncode,result.stdout,result.stderr),(code,'result','detail'))
            self.assertEqual(helper,build_helper.helper_source())
            self.assertFalse(observed[0].exists())
        self.unchanged()

    def test_command_failure_cleans_private_script_without_touching_source(self):
        observed=[]
        def fail(command,**kwargs):
            observed.append(Path(command[-1]));raise OSError('authorization command missing')
        with patch.object(request.subprocess,'run',side_effect=fail),self.assertRaises(OSError):
            request.run_access('remove')
        self.assertFalse(observed[0].parent.exists());self.unchanged()

    def test_preparation_failure_never_starts_authorization(self):
        with patch.object(request,'installation_source',side_effect=OSError('package missing')), \
             patch.object(request.subprocess,'run') as run:
            with self.assertRaises(OSError):request.run_access('install')
            run.assert_not_called()
        self.unchanged()

    def test_unknown_action_never_reads_sources_or_creates_files(self):
        with patch.object(request,'helper_source') as helper,patch.object(request.tempfile,'TemporaryDirectory') as temporary:
            with self.assertRaises(ValueError):
                with request.prepare_access('anything'):pass
            helper.assert_not_called();temporary.assert_not_called()

    def test_legacy_cleanup_requires_native_entry_and_keeps_request_until_authorization_returns(self):
        with patch.object(request,'inspect_deployment',return_value=SimpleNamespace(system=False)),patch.object(request.subprocess,'run') as run:
            with self.assertRaises(ValueError):request.remove_legacy_access(self.source)
            run.assert_not_called()
        for code in (0,1,126,127):
            observed=[]
            def runner(command,**kwargs):
                script=Path(command[-1]);observed.append(script)
                self.assertEqual(script.read_text(),request.removal_source())
                self.assertEqual(command[:3],['pkexec','/usr/bin/python3','-I'])
                self.assertEqual(kwargs['stdin'],subprocess.DEVNULL)
                self.assertNotIn('shell',kwargs)
                return subprocess.CompletedProcess(command,code,'','detail')
            with patch.object(request,'inspect_deployment',return_value=SimpleNamespace(system=True)),patch.object(request.subprocess,'run',side_effect=runner):
                result=request.remove_legacy_access(self.source)
            self.assertEqual(result.returncode,code);self.assertFalse(observed[0].parent.exists())
        self.unchanged()


class HelperRevisionTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'helper'

    def test_missing_current_different_and_replaced_without_rebuilding(self):
        calls=[]
        probe=request.HelperRevision(self.path,builder=lambda:(calls.append(True) or 'new helper'))
        probe._check();self.assertEqual(probe._state,'missing');self.assertFalse(calls)
        self.path.write_text('new helper');probe._check();self.assertEqual(probe._state,'current')
        info=self.path.stat()
        replacement=self.path.with_name('replacement');replacement.write_text('old helper')
        os.utime(replacement,ns=(info.st_atime_ns,info.st_mtime_ns));replacement.replace(self.path)
        probe._check();self.assertEqual(probe._state,'different');self.assertEqual(len(calls),1)
        self.path.write_text('new helper');probe._check();self.assertEqual(probe._state,'current')
        self.path.unlink();probe._check();self.assertEqual(probe._state,'missing')

    def test_unchanged_file_uses_cached_comparison(self):
        self.path.write_text('expected');probe=request.HelperRevision(self.path,builder=lambda:'expected')
        probe._check()
        with patch.object(request.os,'open',side_effect=AssertionError('read again')):
            probe._check()
        self.assertEqual(probe._state,'current')

    def test_unreadable_nonregular_and_oversized_are_not_reported_current(self):
        probe=request.HelperRevision(self.path,builder=lambda:'expected')
        self.path.symlink_to('absent');probe._check();self.assertEqual(probe._state,'unavailable')
        self.path.unlink();os.mkfifo(self.path);probe._check();self.assertEqual(probe._state,'unavailable')
        self.path.unlink()
        with self.path.open('wb') as stream:stream.truncate(2*1024*1024+1)
        probe._check();self.assertEqual(probe._state,'unavailable')
        self.path.write_text('expected')
        with patch.object(request.os,'open',side_effect=PermissionError):probe._check()
        self.assertEqual(probe._state,'unavailable')
        probe._check();self.assertEqual(probe._state,'current')

    def test_source_failure_recovers_and_native_uses_native_builder(self):
        self.path.write_text('native')
        with patch.object(request,'native_helper_source',side_effect=[RuntimeError('source missing'),'native']) as native, \
             patch.object(request,'helper_source',side_effect=AssertionError('wrong deployment')):
            probe=request.HelperRevision(self.path,native=True)
            probe._check();self.assertEqual(probe._state,'unavailable')
            probe._check();self.assertEqual(probe._state,'current');self.assertEqual(native.call_count,2)

    def test_probe_is_nonblocking_and_coalesces_pending_checks(self):
        self.path.write_text('expected');started=threading.Event();release=threading.Event();finished=threading.Event()
        def builder():
            started.set();self.assertTrue(release.wait(5));return 'expected'
        probe=request.HelperRevision(self.path,builder=builder)
        original=probe._check
        def checked():
            try:original()
            finally:finished.set()
        probe._check=checked
        try:
            self.assertEqual(probe.state(),'checking');self.assertTrue(started.wait(2))
            with patch.object(request.threading,'Thread',side_effect=AssertionError('duplicate worker')):
                for count in range(10):self.assertEqual(probe.state(),'checking')
        finally:release.set();self.assertTrue(finished.wait(2))
        self.assertEqual(probe.state(),'current')


if __name__=='__main__':unittest.main()
