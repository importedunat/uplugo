# SPDX-License-Identifier: GPL-3.0-only
"""Real disposable Git indexes; never stage or commit in the working repository."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from tests.git_inventory import audit


@unittest.skipUnless(shutil.which('git'), 'Git is a developer dependency')
class GitInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)/'app';self.root.mkdir()
        self.git('init', '-q')
        runtime = ['install.py','app_info.py','distribution.py','packaging/files.json','build_helper.py',
                   'packaging/install-access.py.in','LICENSE','THIRD_PARTY.md','README.md',
                   'assets/dualsense-blueprint.LICENSE.txt','locales/en.json','locales/es.json']
        self.names = runtime + ['release.py']
        for name in self.names:
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture\n')
        (self.root/'packaging/files.json').write_text(json.dumps({'format':1,'runtime':runtime,'development':['release.py']}))
        self.git('add','--',*self.names)

    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.root),*args],stderr=subprocess.PIPE)

    def test_ready_initial_index_and_read_only_audit(self):
        before=(self.root/'.git/index').read_bytes()
        (self.root/'controllers.json').write_text('personal and untracked')
        self.assertTrue(audit(self.root)['ok'])
        self.assertEqual((self.root/'.git/index').read_bytes(),before)

    def test_missing_and_outdated_staged_source_is_reported(self):
        self.git('rm','--cached','app_info.py')
        (self.root/'README.md').write_text('new unpublished instructions')
        report=audit(self.root)
        self.assertFalse(report['ok'])
        self.assertEqual(report['missing_from_index'],['app_info.py'])
        self.assertEqual(report['outdated_in_index'],['README.md'])

    def test_private_extra_and_symlink_entries_are_refused(self):
        (self.root/'controllers.json').write_text('private contents must not be returned')
        self.git('add','controllers.json')
        (self.root/'README.md').unlink();(self.root/'README.md').symlink_to('LICENSE')
        self.git('add','README.md')
        report=audit(self.root)
        self.assertEqual(report['unsafe_indexed_paths'],['controllers.json'])
        self.assertEqual(report['unexpected_indexed'],['controllers.json'])
        self.assertEqual(report['unsupported_index_entries'],['README.md'])
        self.assertNotIn('private contents',json.dumps(report))

    def test_conflicts_and_wrong_repository_root_are_refused(self):
        oid=self.git('rev-parse',':README.md').decode().strip()
        self.git('update-index','--force-remove','README.md')
        subprocess.run(['git','-C',str(self.root),'update-index','--index-info'],
                       input=f'100644 {oid} 1\tREADME.md\n100644 {oid} 2\tREADME.md\n'.encode(),check=True)
        self.assertEqual(audit(self.root)['unsupported_index_entries'],['README.md'])
        with self.assertRaises(ValueError):audit(self.root/'packaging')
