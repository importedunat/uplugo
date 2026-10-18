# SPDX-License-Identifier: GPL-3.0-only
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import native_package
import startup_notice as notice


class StartupNoticeTests(unittest.TestCase):
    def test_language_preference_fallback_and_damaged_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); path=root/'dualsense-usb/controllers.json';path.parent.mkdir()
            env={'XDG_CONFIG_HOME':temporary,'LANG':'en_US.UTF-8','LANGUAGE':'es:en'}
            self.assertEqual(notice.notice_language(env),'es')
            path.write_text(json.dumps({'ui':{'language':'pt-BR'}}))
            self.assertEqual(notice.notice_language(env),'pt-BR')
            for data in ('not JSON','[]','{"ui":[]}','{"ui":{"language":[]}}',' '*300000):
                path.write_text(data);self.assertEqual(notice.notice_language(env),'es')
            path.unlink();os.mkfifo(path)
            self.assertEqual(notice.notice_language(env),'es')
            path.unlink();path.symlink_to(root/'missing')
            self.assertEqual(notice.notice_language(env),'es')
            self.assertEqual(notice.notice_language(dict(env,LANGUAGE='',LC_ALL='pt_PT.UTF-8')),'pt-BR')
            self.assertEqual(notice.notice_language(dict(env,LANGUAGE='',LANG='de_DE')),'en')

    def test_bounded_plain_details_include_service_output(self):
        error=subprocess.CalledProcessError(1,['systemctl','--user','start','test'],stderr='<service failed>\x00')
        text=notice.notice_details(error)
        self.assertIn('<service failed>',text);self.assertNotIn('\x00',text)
        self.assertEqual(len(notice.notice_details(RuntimeError('x'*20000))),12000)

    def test_headless_privileged_service_and_cli_do_not_import_gtk(self):
        original=__import__
        def guarded(name,*args,**kwargs):
            if name=='gi' or name.startswith('gi.'):raise AssertionError('Unexpected graphical import')
            return original(name,*args,**kwargs)
        for environment,uid,graphical in [({},1000,True),({'DISPLAY':':99'},0,True),({'DISPLAY':':99','INVOCATION_ID':'service'},1000,True),({'DISPLAY':':99','NOTIFY_SOCKET':'service'},1000,True),({'DISPLAY':':99'},1000,False)]:
            with patch.dict(os.environ,environment,clear=True),patch.object(os,'geteuid',return_value=uid),patch('builtins.__import__',side_effect=guarded),contextlib.redirect_stderr(io.StringIO()) as output:
                self.assertEqual(notice.report_startup_failure(RuntimeError('blocked'),graphical=graphical),78)
                self.assertIn('blocked',output.getvalue())

    def test_embedded_guard_works_without_application_files_or_catalogs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); script=root/'start.py'; marker=root/'opened'
            body=('from pathlib import Path\nPath('+repr(str(marker))+').touch()\n').encode()
            script.write_bytes(native_package.bootstrap(body,graphical=False))
            env={'PATH':os.environ.get('PATH',''),'LANG':'es_ES.UTF-8','HOME':str(root),'XDG_CONFIG_HOME':str(root/'config'),'PYTHONDONTWRITEBYTECODE':'1'}
            for gate in (None,'syntax broken !!','def hold_native_package(version): raise RuntimeError("maintenance fixture")'):
                if gate is not None:(root/'native_lifecycle.py').write_text(gate)
                result=subprocess.run([sys.executable,str(script)],env=env,capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,78,result.stderr)
                self.assertIn('La instalación debe finalizar',result.stderr)
                self.assertFalse(marker.exists())
            (root/'native_lifecycle.py').write_text('def hold_native_package(version): pass')
            result=subprocess.run([sys.executable,str(script)],env=env,capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(marker.exists())

    def test_standalone_launcher_missing_program_and_doctor_arguments(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); app=root/'app';app.mkdir();launcher=root/'dualsense-usb'
            launcher.write_bytes(native_package.launcher_source().replace(b'/usr/share/dualsense-usb',str(app).encode()))
            env={'PATH':os.environ.get('PATH',''),'LANG':'en_US.UTF-8','HOME':str(root),'PYTHONDONTWRITEBYTECODE':'1'}
            def run(*args):return subprocess.run([sys.executable,str(launcher),*args],env=env,capture_output=True,text=True,timeout=5)
            self.assertEqual(run('--version').stdout.strip(),native_package.VERSION)
            self.assertEqual(run('--setup','ignored').returncode,2)
            result=run();self.assertEqual(result.returncode,78);self.assertIn('Installation needs to finish',result.stderr)
            (app/'native_lifecycle.py').write_text('def hold_native_package(version): pass')
            result=run();self.assertEqual(result.returncode,1);self.assertIn('launch.py',result.stderr)
            (app/'doctor.py').write_text('import sys\nprint(repr(sys.argv[1:]))')
            result=run('--doctor','--no-session');self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.strip(),"['--no-session']")


if __name__=='__main__':unittest.main()
