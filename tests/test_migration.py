# SPDX-License-Identifier: GPL-3.0-only
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import deployment
import migration as m
from app_info import VERSION
from maintenance import Locations,installation_lock


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'system';self.source.mkdir()
        (self.source/'system-package.json').write_text(json.dumps({'format':1,'manager':'deb','version':VERSION}))
        p=patch.object(deployment,'SYSTEM_APP',self.source);p.start();self.addCleanup(p.stop)
        p=patch.object(m,'systemd_available',return_value=False);p.start();self.addCleanup(p.stop)
        p=patch.dict(os.environ,{'XDG_STATE_HOME':str(self.root/'state')});p.start();self.addCleanup(p.stop)
        self.loc=Locations(self.root/'data',self.root/'config')

    def install_old(self,loc=None):
        loc=loc or self.loc
        loc.app.mkdir(parents=True);(loc.app/'modified.py').write_text('user modified program')
        (loc.app/'unknown').mkdir();(loc.app/'unknown/personal.txt').write_text('unknown data')
        (loc.app/'link').symlink_to('../personal-outside')
        (loc.base/'personal-outside').write_text('outside target')
        for key in ('desktop','icon','service'):
            path=loc.target(key);path.parent.mkdir(parents=True,exist_ok=True);path.write_text('old '+key)
        overrides=loc.target('service').with_name(m.UNIT+'.d');overrides.mkdir();(overrides/'local.conf').write_text('custom override')
        enabled=loc.target('service').parent/'default.target.wants';enabled.mkdir();(enabled/m.UNIT).symlink_to('../'+m.UNIT)
        preferences=loc.config/'dualsense-usb/controllers.json';preferences.parent.mkdir(parents=True,exist_ok=True);preferences.write_text('saved names and modes')
        photos=loc.base/'appearance-library';photos.mkdir();(photos/'photo.png').write_bytes(b'photo fixture')
        return preferences,photos

    def migrate(self,loc=None):
        loc=loc or self.loc
        return m.migrate(self.source,loc,m.preview(loc)['token'])

    def test_receiptless_legacy_migrates_whole_program_and_overrides_without_changing_data(self):
        prefs,photos=self.install_old();plan=m.preview(self.loc)
        self.assertEqual(plan['action'],'migrate');self.assertFalse(self.loc.receipt.exists())
        before={key:m.identity(path,allow_link=key.startswith('enable/')) for key,path in m.program_paths(self.loc).items() if path.exists() or path.is_symlink()}
        result=self.migrate();self.assertFalse(result['recovered'])
        self.assertEqual(deployment.legacy_conflicts(self.loc),[])
        self.assertEqual(m.preview(self.loc)['action'],'')
        record=json.loads(next((self.loc.base/'migrations').glob('*.json')).read_text())
        for key,identity in before.items():self.assertEqual(m.identity(m.backup_for(self.loc,key,record['id']),allow_link=key.startswith('enable/')),identity)
        app=m.backup_for(self.loc,'app',record['id'])
        self.assertEqual((app/'modified.py').read_text(),'user modified program')
        self.assertEqual((app/'unknown/personal.txt').read_text(),'unknown data')
        self.assertEqual(os.readlink(app/'link'),'../personal-outside')
        self.assertEqual((self.loc.base/'personal-outside').read_text(),'outside target')
        self.assertEqual(prefs.read_text(),'saved names and modes');self.assertEqual((photos/'photo.png').read_bytes(),b'photo fixture')

    def test_preview_change_and_live_locks_refuse_before_moving_anything(self):
        self.install_old();token=m.preview(self.loc)['token']
        self.loc.receipt.write_text('even an old/invalid receipt is preserved as a file')
        with self.assertRaises(RuntimeError):m.migrate(self.source,self.loc,token)
        self.assertFalse((self.loc.base/m.JOURNAL).exists())
        with installation_lock(self.loc,shared=True),self.assertRaises(RuntimeError):self.migrate()
        with patch.object(m,'require_stopped',side_effect=RuntimeError('busy')),self.assertRaises(RuntimeError):self.migrate()
        self.assertTrue(self.loc.app.exists());self.assertTrue(self.loc.target('service').exists())

    def test_symlink_and_foreign_enable_link_are_preserved(self):
        self.loc.base.mkdir(parents=True);self.loc.app.symlink_to(self.root/'outside')
        with self.assertRaises(ValueError):m.preview(self.loc)
        self.assertTrue(self.loc.app.is_symlink());self.loc.app.unlink();self.install_old()
        link=self.loc.target('service').parent/'default.target.wants'/m.UNIT
        link.unlink();link.symlink_to('/tmp/foreign.service')
        with self.assertRaises(ValueError):m.preview(self.loc)
        self.assertEqual(os.readlink(link),'/tmp/foreign.service')

    def test_interrupted_moves_resume_and_refuse_recreated_source(self):
        self.install_old()
        def stop(name):
            if name=='moved-app':raise OSError('simulated interruption')
        with patch.object(m,'checkpoint',side_effect=stop),self.assertRaises(OSError):self.migrate()
        plan=m.preview(self.loc);self.assertEqual(plan['action'],'resume_migration')
        self.assertFalse(self.loc.app.exists())
        with self.assertRaises(RuntimeError),installation_lock(self.loc,shared=True):pass
        self.loc.app.mkdir();(self.loc.app/'new.txt').write_text('new installation')
        with self.assertRaises(ValueError):m.preview(self.loc)
        self.assertEqual((self.loc.app/'new.txt').read_text(),'new installation')
        (self.loc.app/'new.txt').unlink();self.loc.app.rmdir()
        self.migrate();self.assertEqual(deployment.legacy_conflicts(self.loc),[])

    def test_process_kill_at_each_commit_boundary_is_resumable(self):
        source_root=Path(__file__).resolve().parents[1]
        for index,stage in enumerate(('journal','moved-app','moved-service','reloaded','archived','history','finished')):
            with self.subTest(stage=stage):
                loc=Locations(self.root/f'data-{index}',self.root/f'config-{index}');prefs,_=self.install_old(loc)
                code='''import os,signal,sys
from pathlib import Path
import deployment,migration as m
from maintenance import Locations
deployment.SYSTEM_APP=Path(sys.argv[1]);m.systemd_available=lambda:False
loc=Locations(Path(sys.argv[2]),Path(sys.argv[3]))
def stop(name):
 if name==sys.argv[4]:os.kill(os.getpid(),signal.SIGKILL)
m.checkpoint=stop
m.migrate(deployment.SYSTEM_APP,loc,m.preview(loc)['token'])
'''
                result=subprocess.run([sys.executable,'-c',code,str(self.source),str(loc.data),str(loc.config),stage],cwd=source_root,capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,-signal.SIGKILL,result.stderr)
                if m.preview(loc)['action']:self.migrate(loc)
                self.assertEqual(deployment.legacy_conflicts(loc),[])
                self.assertEqual(prefs.read_text(),'saved names and modes')
                records=list((loc.base/'migrations').glob('*.json'));self.assertEqual(len(records),1)
                record=json.loads(records[0].read_text());self.assertTrue((m.backup_for(loc,'app',record['id'])/'modified.py').exists())

    def test_journal_and_history_unexpected_objects_never_overwritten(self):
        self.install_old();journal=self.loc.base/m.JOURNAL
        os.mkfifo(journal)
        with self.assertRaises(ValueError):m.preview(self.loc)
        journal.unlink()
        def stop(name):
            if name=='archived':raise OSError('pause before history')
        with patch.object(m,'checkpoint',side_effect=stop),self.assertRaises(OSError):self.migrate()
        record=m.read_journal(self.loc);folder=self.loc.base/'migrations';folder.mkdir();path=folder/(record['id']+'.json');os.mkfifo(path)
        with self.assertRaises(ValueError):self.migrate()
        self.assertTrue(journal.exists());path.unlink();self.migrate()

    def test_installer_pending_is_recovered_before_archival(self):
        self.install_old()
        from install_transaction import write_journal
        import uuid
        record={'format':1,'id':uuid.uuid4().hex,'phase':'building','roots':{'data':str(self.loc.data),'config':str(self.loc.config)}}
        write_journal(self.loc,record)
        self.assertEqual(m.preview(self.loc)['action'],'recover_legacy')
        result=self.migrate();self.assertTrue(result['recovered'])
        self.assertTrue(self.loc.app.exists());self.assertFalse(self.loc.pending.exists())
        self.assertEqual(m.preview(self.loc)['action'],'migrate')
        self.migrate();self.assertFalse(self.loc.app.exists())

    def test_changed_pending_installer_record_invalidates_preview(self):
        self.install_old()
        from install_transaction import write_journal
        import uuid
        record={'format':1,'id':uuid.uuid4().hex,'phase':'building','roots':{'data':str(self.loc.data),'config':str(self.loc.config)}}
        write_journal(self.loc,record);token=m.preview(self.loc)['token']
        record['id']=uuid.uuid4().hex;write_journal(self.loc,record)
        with self.assertRaises(RuntimeError):m.migrate(self.source,self.loc,token)
        self.assertTrue(self.loc.pending.exists());self.assertTrue(self.loc.app.exists())

    def test_journal_rejects_wrong_object_kind_and_negative_identity(self):
        self.install_old()
        def stop(name):
            if name=='journal':raise OSError('pause before moves')
        with patch.object(m,'checkpoint',side_effect=stop),self.assertRaises(OSError):self.migrate()
        path=self.loc.base/m.JOURNAL;original=json.loads(path.read_text())
        for field,value in (('kind',32768),('inode',-1),('device',False)):
            record=json.loads(json.dumps(original));record['files']['app'][field]=value
            path.write_text(json.dumps(record))
            with self.assertRaises(ValueError):m.preview(self.loc)
            self.assertTrue(self.loc.app.exists())
        path.write_text(json.dumps(original));self.migrate()

    def test_service_is_checked_and_reloaded_without_stop_or_start(self):
        self.install_old()
        def run(command,**kwargs):
            if 'show' in command:return subprocess.CompletedProcess(command,0,'ActiveState=inactive\nFragmentPath='+str(self.loc.target('service'))+'\n','')
            return subprocess.CompletedProcess(command,0,'','')
        with patch.object(m,'systemd_available',return_value=True),patch.object(m.subprocess,'run',side_effect=run) as execute:
            self.migrate()
            commands=[call.args[0] for call in execute.call_args_list]
            self.assertIn(['systemctl','--user','daemon-reload'],commands)
            self.assertFalse(any('stop' in cmd or 'start' in cmd or 'kill' in cmd for cmd in commands))

    def test_data_left_in_old_program_is_imported_once_without_replacing_current_preferences(self):
        prefs,_=self.install_old()
        (self.loc.app/'controllers.json').write_text('{"names":{"old":"legacy"}}')
        (self.loc.app/'charge-history.json').write_text('{"history":"legacy"}')
        plan=m.preview(self.loc)
        self.assertNotIn('controllers.json',plan['imports']);self.assertIn('charge-history.json',plan['imports'])
        def stop(name):
            if name=='imported-charge-history.json':raise OSError('interrupted after data import')
        with patch.object(m,'checkpoint',side_effect=stop),self.assertRaises(OSError):self.migrate()
        destination=m.data_target(self.loc,'charge-history.json')
        self.assertEqual(destination.read_text(),'{"history":"legacy"}')
        self.migrate();self.assertEqual(prefs.read_text(),'saved names and modes')
        record=json.loads(next((self.loc.base/'migrations').glob('*.json')).read_text())
        self.assertEqual((m.backup_for(self.loc,'app',record['id'])/'controllers.json').read_text(),'{"names":{"old":"legacy"}}')

    def test_changed_data_destination_is_never_overwritten_on_resume(self):
        prefs,_=self.install_old();prefs.unlink()
        (self.loc.app/'controllers.json').write_text('{"names":{"old":"legacy"}}')
        def stop(name):
            if name=='staged-data-controllers.json':raise OSError('interrupted before data commit')
        with patch.object(m,'checkpoint',side_effect=stop),self.assertRaises(OSError):self.migrate()
        prefs.write_text('{"names":{"new":"do not overwrite"}}')
        with self.assertRaises(ValueError):m.preview(self.loc)
        self.assertIn('do not overwrite',prefs.read_text());self.assertTrue(self.loc.app.exists())
        prefs.unlink();self.migrate();self.assertIn('legacy',prefs.read_text())

    def test_separate_data_and_config_filesystems_use_adjacent_archives(self):
        if not Path('/dev/shm').is_dir():self.skipTest('No separate tmpfs available')
        with tempfile.TemporaryDirectory(prefix='dualsense-migrate-config-',dir='/dev/shm') as temporary:
            loc=Locations(self.root/'disk-data',Path(temporary)/'config')
            self.install_old(loc)
            self.migrate(loc)
            record=json.loads(next((loc.base/'migrations').glob('*.json')).read_text())
            self.assertEqual(m.backup_for(loc,'service',record['id']).stat().st_dev,loc.config.stat().st_dev)
            self.assertEqual(m.backup_for(loc,'app',record['id']).stat().st_dev,loc.data.stat().st_dev)


if __name__=='__main__':unittest.main()
