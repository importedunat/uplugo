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
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import steam_access as p
from steam_access_admin import SteamAccessAdmin,steam_access_main
from steam_access_request import prepare_steam_access,SteamAccessBackend
from build_helper import steam_access_source,native_payloads

WHITE='00:11:22:33:44:55';BLACK='aa:bb:cc:dd:ee:ff'
CONNECTED='Interface Plug Slot Notes\nsteam-support steam:steam-support :steam-support -\n'


def fixture_hid(root,name='hidraw0',identity=WHITE,product='00000CE6',bus='0003'):
    device=root/'sys/devices/fixture'/name;node=device/'hidraw'/name;node.mkdir(parents=True)
    (node/'device').symlink_to('../..')
    (device/'uevent').write_text(f'HID_ID={bus}:0000054C:{product}\nHID_UNIQ={identity}\n')
    (node/'dev').write_text('240:'+name[6:]+'\n')
    folder=root/'sys/class/hidraw';folder.mkdir(parents=True,exist_ok=True);(folder/name).symlink_to(node)
    return node


def fixture_snap(root,helper=p.STEAM_HELPERS[0]):
    for name in ('usr/bin/snap',helper):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture');path.chmod(0o755)
        for directory in path.parents:
            if directory==root:break
            directory.chmod(0o755)


class SteamAccessTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup);self.root=Path(self.temporary.name)
        self.node=fixture_hid(self.root);fixture_snap(self.root);self.calls=[]
        def runner(command,**kwargs):
            self.calls.append(command);self.assertLessEqual(kwargs['timeout'],15);self.assertNotIn('shell',kwargs)
            return subprocess.CompletedProcess(command,0,CONNECTED if command[-2:]==['connections','steam'] else '','')
        self.admin=SteamAccessAdmin(self.root,self.root/'sys',os.getuid(),runner)

    def test_rule_fixed_scope_and_identity_validation(self):
        for helper in p.STEAM_HELPERS:
            rule=p.steam_rule('hid:'+WHITE,helper).decode()
            self.assertIn('HID_UNIQ}=="'+WHITE+'"',rule);self.assertIn('0003:054C:0DF2.*',rule)
            self.assertNotIn('MODE=',rule);self.assertNotIn('chmod',rule)
        for identity in ('../device',WHITE+'\n','" RUN+="x',None):
            with self.assertRaises(ValueError):p.steam_rule(identity,p.STEAM_HELPERS[0])
        with self.assertRaises(ValueError):p.steam_rule(WHITE,'tmp/helper')
        for native in (False,True):
            source=steam_access_source(native);ast.parse(source)
            self.assertNotIn('from steam_access',source);self.assertNotIn('from touchpad_',source)

    def test_selected_usb_only_preserves_other_hid_and_bluetooth(self):
        fixture_hid(self.root,'hidraw1',BLACK);fixture_hid(self.root,'hidraw2',WHITE,bus='0005')
        fixture_hid(self.root,'hidraw3',WHITE,product='000005C4')
        answer=self.admin.apply(WHITE,'allow');self.assertEqual(answer,{'choice':'allow','refreshed':1,'pending':False})
        triggers=[c for c in self.calls if 'trigger' in c]
        self.assertEqual(len(triggers),2);self.assertIn('--action=remove',triggers[0]);self.assertIn('--action=add',triggers[1])
        for command in triggers:self.assertEqual(command[-1],str(self.node));self.assertIn('--subsystem-match=hidraw',command)
        self.assertFalse((self.root/p.steam_rule_path(BLACK)).exists())
        self.calls.clear();self.admin.apply(BLACK,'allow')
        self.assertTrue(all('hidraw1' in c[-1] for c in self.calls if 'trigger' in c))

    def test_snapshot_distinguishes_current_tag_history_and_external_rule(self):
        database=self.root/'run/udev/data/c240:0';database.parent.mkdir(parents=True)
        (self.root/'run').chmod(0o755)
        database.write_text('G:snap_steam_steam\n')
        view=p.steam_snapshot(WHITE,self.root,self.root/'sys',self.admin.runner)
        self.assertEqual(view['saved'],'system');self.assertFalse(view['nodes'][0]['tagged'])
        database.write_text('Q:snap_steam_steam\n')
        view=p.steam_snapshot(WHITE,self.root,self.root/'sys',self.admin.runner)
        self.assertEqual(view['saved'],'system');self.assertTrue(view['nodes'][0]['tagged'])
        self.admin.apply(WHITE,'allow');self.assertEqual(p.steam_snapshot(WHITE,self.root,self.root/'sys',self.admin.runner)['saved'],'allow')
        path=self.root/p.steam_rule_path(WHITE);path.write_bytes(b'custom')
        self.assertEqual(p.steam_snapshot(WHITE,self.root,self.root/'sys',self.admin.runner)['saved'],'custom')

    def test_restore_owned_rule_even_without_snap_preserves_other_rules(self):
        self.admin.apply(WHITE,'allow');self.admin.apply(BLACK,'allow')
        other=self.root/'etc/udev/rules.d/70-other.rules';other.write_text('other')
        (self.root/'usr/bin/snap').unlink();self.calls.clear();self.admin.apply(WHITE,'system')
        self.assertFalse((self.root/p.steam_rule_path(WHITE)).exists());self.assertTrue((self.root/p.steam_rule_path(BLACK)).exists())
        self.assertEqual(other.read_text(),'other');self.assertTrue(all('connections' not in c for c in self.calls))

    def test_disconnected_or_exclusively_charging_saves_without_changing_usb_mode(self):
        self.calls.clear();answer=self.admin.apply('11:22:33:44:55:66','allow')
        self.assertTrue(answer['pending']);self.assertFalse(any('trigger' in c for c in self.calls))
        self.assertEqual(self.calls[-1],['/usr/bin/udevadm','control','--reload-rules'])

    def test_unavailable_snap_disconnected_interface_and_bad_helper_prevent_grant(self):
        for text in ('',CONNECTED.replace(':steam-support -','- -'),'steam-support other:steam-support :steam-support -'):
            with patch.object(self.admin,'runner',return_value=subprocess.CompletedProcess([],0,text,'')),self.assertRaisesRegex(ValueError,'snap-connection'):self.admin.apply(WHITE,'allow')
            self.assertFalse((self.root/p.steam_rule_path(WHITE)).exists())
        helper=self.root/p.STEAM_HELPERS[0];helper.chmod(0o777)
        with self.assertRaisesRegex(ValueError,'snap-helper'):self.admin.apply(WHITE,'allow')
        helper.unlink();self.assertFalse(p.steam_environment(self.root,self.admin.runner)['available'])
        (self.root/'usr/bin/snap').unlink()
        self.assertEqual(p.steam_environment(self.root,self.admin.runner)['reason'],'no-snap')

    def test_custom_symlink_hardlink_fifo_or_writable_rule_is_preserved(self):
        path=self.admin.path(p.steam_rule_path(WHITE),True)
        for kind in ('custom','symlink','hardlink','fifo','writable'):
            outside=self.root/'outside';outside.write_text('keep')
            if kind=='symlink':path.symlink_to(outside)
            elif kind=='hardlink':os.link(outside,path)
            elif kind=='fifo':os.mkfifo(path)
            else:path.write_bytes(b'custom' if kind=='custom' else p.steam_rule(WHITE,p.STEAM_HELPERS[0]))
            if kind=='writable':path.chmod(0o666)
            self.calls.clear()
            with self.assertRaises((ValueError,OSError)):self.admin.apply(WHITE,'system')
            self.assertEqual(outside.read_text(),'keep');self.assertFalse(self.calls);path.unlink()

    def test_shared_lock_prevents_concurrent_permission_changes(self):
        with self.admin.lock(),self.assertRaisesRegex(RuntimeError,'busy'):self.admin.apply(WHITE,'allow')
        self.assertFalse(self.calls)

    def test_failed_remove_readds_and_restores_previous_rule(self):
        original=self.admin.runner;failed=False
        def runner(command,**kwargs):
            nonlocal failed
            result=original(command,**kwargs)
            if '--action=remove' in command and not failed:
                failed=True;raise subprocess.TimeoutExpired(command,15)
            return result
        self.admin.runner=runner
        with self.assertRaisesRegex(RuntimeError,'apply-failed-restored'):self.admin.apply(WHITE,'allow')
        self.assertFalse((self.root/p.steam_rule_path(WHITE)).exists())
        triggers=[c for c in self.calls if 'trigger' in c];self.assertIn('--action=add',triggers[1]);self.assertEqual(len(triggers),4)

    def test_node_alias_reuse_does_not_redirect_refresh(self):
        other=fixture_hid(self.root,'hidraw1',BLACK);alias=self.root/'sys/class/hidraw/hidraw0';original=self.admin.runner
        def runner(command,**kwargs):
            result=original(command,**kwargs)
            if '--action=remove' in command:alias.unlink();alias.symlink_to(other)
            return result
        self.admin.runner=runner;self.admin.apply(WHITE,'allow')
        self.assertEqual(self.calls[-1][-1],str(self.node))

    def test_privileged_entry_and_native_auth_policy(self):
        for uid in ('','0','-1','1000\n','4294967295'):
            with patch('steam_access_admin.os.geteuid',return_value=0),patch.dict(os.environ,PKEXEC_UID=uid),self.assertRaises(ValueError):steam_access_main(['allow',WHITE])
        with patch('steam_access_admin.os.geteuid',return_value=1000),self.assertRaises(ValueError):steam_access_main(['allow',WHITE])
        import xml.etree.ElementTree as ET
        action=ET.fromstring(native_payloads()[p.STEAM_POLICY][0]).find('action')
        self.assertEqual(action.findtext('defaults/allow_active'),'auth_admin');self.assertEqual(action.findtext('defaults/allow_inactive'),'no')
        self.assertEqual(action.findtext('annotate'),'/'+p.STEAM_ADMIN)

    def test_request_is_private_and_native_path_fixed(self):
        with patch('steam_access_request.inspect_deployment',return_value=SimpleNamespace(system=False)):
            with prepare_steam_access(WHITE,'allow') as command:
                script=Path(command[3]);self.assertEqual(command[:3],['pkexec','/usr/bin/python3','-I'])
                self.assertEqual(script.stat().st_mode&0o777,0o600);self.assertEqual(script.parent.stat().st_mode&0o777,0o700)
                self.assertEqual(command[-2:],['allow',WHITE])
            self.assertFalse(script.parent.exists())
        with patch('steam_access_request.inspect_deployment',return_value=SimpleNamespace(system=True)):
            with prepare_steam_access(WHITE,'system') as command:self.assertEqual(command,['pkexec','/'+p.STEAM_ADMIN,'system',WHITE])

    def test_backend_does_not_report_success_without_saved_and_parsed_result(self):
        backend=SteamAccessBackend(WHITE);view={'saved':'system'}
        with patch.object(backend,'inspect',return_value=view),patch('steam_access_request.subprocess.run') as run:
            run.return_value=subprocess.CompletedProcess([],126,'','');self.assertEqual(backend.apply('allow')[0].returncode,126)
            run.return_value=subprocess.CompletedProcess([],0,'[]','')
            with self.assertRaisesRegex(RuntimeError,'invalid-result'):backend.apply('allow')
            run.return_value=subprocess.CompletedProcess([],0,'{"choice":"allow","refreshed":0,"pending":true}','')
            with self.assertRaisesRegex(RuntimeError,'not-saved'):backend.apply('allow')
            view['saved']='allow';self.assertTrue(backend.apply('allow')[1]['pending'])
