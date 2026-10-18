# SPDX-License-Identifier: GPL-3.0-only
import ast
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import touchpad_policy as p
from touchpad_admin import TouchpadAdmin,touchpad_main
from touchpad_request import TouchpadBackend,prepare_touchpad
from build_helper import touchpad_source,native_payloads

# Synthetic addresses: fixtures never need a personal controller identity.
WHITE='02:00:00:00:00:01';BLACK='02:00:00:00:00:02'


def fixture_device(root,event='event4',identity=WHITE,name='Sony DualSense Wireless Controller Touchpad',product='0ce6'):
    system=root/'sys';device=system/'devices/fixture/input'/('input-'+event);node=device/event
    node.mkdir(parents=True);(device/'id').mkdir()
    for path,value in [('name',name),('uniq',identity),('id/bustype','0003'),('id/vendor','054c'),('id/product',product)]:
        (device/path).write_text(value+'\n')
    (node/'dev').write_text('13:'+str(64+int(event[5:]))+'\n');(node/'device').symlink_to('..')
    aliases=system/'class/input';aliases.mkdir(parents=True,exist_ok=True);(aliases/event).symlink_to(node)
    return node


class TouchpadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.node=fixture_device(self.root)
        self.commands=[]
        def runner(command,**kwargs):
            self.commands.append(command)
            self.assertTrue(kwargs['check']);self.assertLessEqual(kwargs['timeout'],15)
            self.assertNotIn('shell',kwargs)
            return subprocess.CompletedProcess(command,0,'','')
        self.admin=TouchpadAdmin(self.root,self.root/'sys',os.getuid(),runner)

    def test_identity_is_stable_and_rejects_paths_or_rule_injection(self):
        for value in (WHITE,'hid:'+WHITE,WHITE.upper(),'serial:'+WHITE.replace(':','')):
            self.assertEqual(p.touchpad_identity(value),WHITE)
        for value in ('../event4',WHITE+'\n','hid:connection:3-1','"1", RUN+="anything"',None,1):
            with self.assertRaises(ValueError):p.touchpad_identity(value)
        ast.parse(touchpad_source());ast.parse(touchpad_source(native=True))

    def test_snapshot_distinguishes_saved_policy_and_udev_state(self):
        view=p.touchpad_snapshot(WHITE,self.root,self.root/'sys')
        self.assertEqual(view['saved'],'system');self.assertIsNone(view['nodes'][0]['ignored'])
        database=self.root/'run/udev/data/c13:68';database.parent.mkdir(parents=True);database.write_text('E:ID_INPUT_TOUCHPAD=1\n')
        (self.root/'run').chmod(0o755)
        self.assertFalse(p.touchpad_snapshot(WHITE,self.root,self.root/'sys')['nodes'][0]['ignored'])
        self.admin.apply(WHITE,'game')
        view=p.touchpad_snapshot(WHITE,self.root,self.root/'sys')
        self.assertEqual(view['saved'],'game');self.assertFalse(view['nodes'][0]['ignored'])
        database.write_text('E:LIBINPUT_IGNORE_DEVICE=1\n')
        self.assertTrue(p.touchpad_snapshot(WHITE,self.root,self.root/'sys')['nodes'][0]['ignored'])
        self.admin.apply(WHITE,'system');self.assertEqual(p.touchpad_snapshot(WHITE,self.root,self.root/'sys')['saved'],'system')
        self.assertTrue(p.touchpad_snapshot(WHITE,self.root,self.root/'sys')['nodes'][0]['ignored'])

    def test_scope_preserves_gamepad_motion_mouse_other_controller_and_current_mode(self):
        fixture_device(self.root,'event2',name='Sony DualSense Wireless Controller')
        fixture_device(self.root,'event3',name='Sony DualSense Wireless Controller Motion Sensors')
        fixture_device(self.root,'event8',name='Mouse Touchpad')
        fixture_device(self.root,'event14',BLACK,product='0df2')
        result=self.admin.apply(WHITE,'game');self.assertEqual(result,{'choice':'game','refreshed':1,'pending':False})
        self.assertEqual(len(self.commands),3)
        for command in self.commands[1:]:
            self.assertEqual(command[-1],str(self.node));self.assertIn('--sysname-match=event4',command)
        self.assertEqual((self.root/p.touchpad_rule_path(WHITE)).read_bytes(),p.touchpad_rule(WHITE))
        self.assertFalse((self.root/p.touchpad_rule_path(BLACK)).exists())
        self.commands.clear();self.admin.apply(BLACK,'game')
        self.assertTrue(all('event14' in command[-1] for command in self.commands[1:]))
        # A charging/disconnected controller has no input node. Saving its rule
        # never binds drivers, authorizes USB interfaces or creates a gamepad.
        self.commands.clear();result=self.admin.apply('00:11:22:33:44:55','game')
        self.assertTrue(result['pending']);self.assertEqual(len(self.commands),1)

    def test_restore_removes_only_owned_rule_and_preserves_other_settings(self):
        self.admin.apply(WHITE,'game');self.admin.apply(BLACK,'game')
        other=self.root/p.TOUCHPAD_RULES/'01-user-custom.rules';other.write_text('other settings')
        self.admin.apply(WHITE,'system')
        self.assertFalse((self.root/p.touchpad_rule_path(WHITE)).exists())
        self.assertEqual((self.root/p.touchpad_rule_path(BLACK)).read_bytes(),p.touchpad_rule(BLACK))
        self.assertEqual(other.read_text(),'other settings')

    def test_modified_symlink_fifo_hardlink_and_unsafe_parents_are_preserved(self):
        path=self.admin.path(p.touchpad_rule_path(WHITE),True)
        for kind in ('modified','link','fifo','hardlink','writable'):
            with self.subTest(kind=kind):
                outside=self.root/'outside';outside.write_text('keep')
                if kind=='modified':path.write_text('custom')
                elif kind=='link':path.symlink_to(outside)
                elif kind=='fifo':os.mkfifo(path)
                elif kind=='hardlink':os.link(outside,path)
                else:path.write_bytes(p.touchpad_rule(WHITE));path.chmod(0o666)
                self.commands.clear()
                with self.assertRaises((OSError,ValueError)):self.admin.apply(WHITE,'game')
                self.assertEqual(outside.read_text(),'keep');self.assertEqual(self.commands,[]);path.unlink()
        path.parent.chmod(0o777)
        with self.assertRaises(ValueError):self.admin.apply(WHITE,'game')
        path.parent.chmod(0o755)

    def test_concurrent_configuration_refused_before_rule_change(self):
        with self.admin.lock(),self.assertRaises(RuntimeError):self.admin.apply(WHITE,'game')
        self.assertEqual(self.commands,[]);self.assertFalse((self.root/p.touchpad_rule_path(WHITE)).exists())

    def test_failed_remove_still_adds_and_restores_old_policy(self):
        calls=[];failed=False
        def runner(command,**kwargs):
            nonlocal failed
            calls.append(command)
            if '--action=remove' in command and not failed:
                failed=True;raise subprocess.TimeoutExpired(command,15)
            return subprocess.CompletedProcess(command,0,'','')
        self.admin.runner=runner
        with self.assertRaisesRegex(RuntimeError,'apply-failed-restored'):self.admin.apply(WHITE,'game')
        self.assertIn('--action=add',calls[2]);self.assertFalse((self.root/p.touchpad_rule_path(WHITE)).exists())
        self.assertTrue(all(command[-1]==str(self.node) for command in calls if 'trigger' in command))

    def test_failed_recovery_is_reported_and_retry_recovers_saved_policy(self):
        def fail(command,**kwargs):raise OSError('missing udev')
        with patch.object(self.admin,'runner',side_effect=fail),self.assertRaisesRegex(RuntimeError,'recovery-needed'):
            self.admin.apply(WHITE,'game')
        self.admin.apply(WHITE,'system');self.assertFalse((self.root/p.touchpad_rule_path(WHITE)).exists())

    def test_reused_event_alias_cannot_redirect_add_to_a_different_device(self):
        other=fixture_device(self.root,'event14',BLACK)
        original=self.admin.runner;alias=self.root/'sys/class/input/event4'
        def runner(command,**kwargs):
            result=original(command,**kwargs)
            if '--action=remove' in command:alias.unlink();alias.symlink_to(other)
            return result
        self.admin.runner=runner;self.admin.apply(WHITE,'game')
        self.assertEqual(self.commands[-1][-1],str(self.node));self.assertNotEqual(self.commands[-1][-1],str(other))

    def test_kill_after_policy_write_is_recoverable_by_reapplying_without_cable(self):
        code='''import os,signal,sys
from pathlib import Path
from touchpad_admin import TouchpadAdmin
root=Path(sys.argv[1])
def run(command,**kwargs):
 if '--action=remove' in command:os.kill(os.getpid(),signal.SIGKILL)
admin=TouchpadAdmin(root,root/'sys',os.getuid(),run)
admin.apply(sys.argv[2],'game')
'''
        result=subprocess.run([sys.executable,'-c',code,str(self.root),WHITE],capture_output=True,timeout=10)
        self.assertEqual(result.returncode,-signal.SIGKILL)
        self.assertEqual((self.root/p.touchpad_rule_path(WHITE)).read_bytes(),p.touchpad_rule(WHITE))
        self.assertFalse(self.admin.apply(WHITE,'game')['pending'])

    def test_privileged_entry_rejects_missing_or_invalid_actor(self):
        for uid in ('','0','-1','1000\n','4294967295'):
            with patch('touchpad_admin.os.geteuid',return_value=0),patch.dict(os.environ,{'PKEXEC_UID':uid}),self.assertRaises(ValueError):touchpad_main(['game',WHITE])
        with patch('touchpad_admin.os.geteuid',return_value=1000),self.assertRaises(ValueError):touchpad_main(['game',WHITE])

    def test_requests_are_private_and_native_policy_requires_admin_authorization(self):
        with patch('touchpad_request.inspect_deployment',return_value=SimpleNamespace(system=False)):
            with prepare_touchpad('hid:'+WHITE,'game') as command:
                self.assertEqual(command[:3],['pkexec','/usr/bin/python3','-I']);script=Path(command[3])
                self.assertEqual(stat.S_IMODE(script.stat().st_mode),0o600)
                self.assertEqual(stat.S_IMODE(script.parent.stat().st_mode),0o700)
                self.assertNotIn('from touchpad_policy import',script.read_text());self.assertNotIn('from touchpad_admin import',script.read_text())
                self.assertEqual(command[-2:],['game',WHITE])
            self.assertFalse(script.parent.exists())
        with patch('touchpad_request.inspect_deployment',return_value=SimpleNamespace(system=True)):
            with prepare_touchpad(WHITE,'system') as command:self.assertEqual(command,['pkexec','/'+p.TOUCHPAD_ADMIN,'system',WHITE])
        import xml.etree.ElementTree as ET
        payloads=native_payloads();policy=ET.fromstring(payloads[p.TOUCHPAD_POLICY][0]);action=policy.find('action')
        self.assertEqual(action.findtext('defaults/allow_active'),'auth_admin')
        self.assertEqual(action.findtext('defaults/allow_inactive'),'no')
        self.assertEqual(action.findtext('annotate'),'/'+p.TOUCHPAD_ADMIN)

    def test_backend_requires_saved_policy_and_parsed_result_before_success(self):
        backend=TouchpadBackend(WHITE)
        view={'saved':'system','identity':WHITE,'nodes':[]}
        with patch.object(backend,'inspect',return_value=view),patch('touchpad_request.subprocess.run') as run:
            run.return_value=subprocess.CompletedProcess([],126,'','cancelled')
            self.assertEqual(backend.apply('game')[0].returncode,126)
            run.return_value=subprocess.CompletedProcess([],0,'{"choice":"game","refreshed":0,"pending":true}','')
            with self.assertRaisesRegex(RuntimeError,'not-saved'):backend.apply('game')
            run.return_value=subprocess.CompletedProcess([],0,'[]','')
            with self.assertRaisesRegex(RuntimeError,'invalid-result'):backend.apply('game')
            view['saved']='game';run.return_value=subprocess.CompletedProcess([],0,'{"choice":"game","refreshed":0,"pending":true}','')
            self.assertTrue(backend.apply('game')[1]['pending'])


if __name__=='__main__':unittest.main()
