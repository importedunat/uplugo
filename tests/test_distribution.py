# SPDX-License-Identifier: GPL-3.0-only
import io
import gzip
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from app_info import VERSION
from distribution import BASE, MANIFEST, inventory, safe_name, parse_manifest
import release


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='dualsense-dist-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.source=self.root/'source';self.source.mkdir()
        self.inventory=inventory()
        for name in self.inventory['runtime']+self.inventory['development']:
            target=self.source/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(BASE/name,target)

    def build(self,folder='out'):
        return release.build(self.root/folder,self.source,epoch=0)[0]

    def mutate(self,archive,kind):
        destination=self.root/(kind+'.tar.gz')
        with tarfile.open(archive,'r:gz') as src,tarfile.open(destination,'w:gz') as dst:
            entries=[(m,src.extractfile(m).read()) for m in src]
            changed=False
            for item,data in entries:
                if not changed and item.name.endswith('/README.md'):
                    if kind=='content':data+=b'\nchanged\n';item.size=len(data)
                    elif kind=='traversal':item.name=item.name.partition('/')[0]+'/../outside.txt'
                    elif kind=='symlink':item.type=tarfile.SYMTYPE;item.linkname='/tmp/outside';item.size=0;data=b''
                    changed=True
                dst.addfile(item,io.BytesIO(data))
            if kind=='duplicate':dst.addfile(entries[0][0],io.BytesIO(entries[0][1]))
            if kind=='extra':
                item=tarfile.TarInfo(entries[0][0].name.partition('/')[0]+'/secret.txt');item.mode=0o644
                dst.addfile(item,io.BytesIO())
        return destination

    def test_reproducible_after_path_mode_and_mtime_changes(self):
        first=self.build('a')
        path=self.source/'README.md';path.chmod(0o777);os.utime(path,(123456,123456))
        second=self.build('b')
        self.assertEqual(first.read_bytes(),second.read_bytes())
        info=release.verify(first,release.digest(first.read_bytes()))
        self.assertEqual(info['version'],VERSION)
        with self.assertRaises(ValueError):release.verify(first,'0'*64)

    def test_unlisted_personal_and_generated_files_never_enter_package(self):
        for name in ('controllers.json','install-access.py','remove-access.py','installation.json','docs/private-photo.png','work/input.log','.env','assets/official/photo.jpg'):
            path=self.source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'PERSONAL DATA')
        archive=self.build()
        result,payloads=release.read_verified(archive)
        self.assertEqual(set(payloads),set(self.inventory['runtime']+self.inventory['development'])|{release.RECORD})
        self.assertTrue(all(data!=b'PERSONAL DATA' for data in payloads.values()))
        self.assertIn('LICENSE',payloads)
        self.assertIn('assets/dualsense-blueprint.LICENSE.txt',payloads)

    def test_cross_compressor_rebuild_requires_the_entire_identical_tar(self):
        from tests.release_smoke import compare_rebuild
        original=self.build()
        self.assertTrue(compare_rebuild(original,original))
        encoded=self.root/'another-compressor.tar.gz'
        encoded.write_bytes(gzip.compress(gzip.decompress(original.read_bytes()),compresslevel=0,mtime=0))
        with self.assertRaises(AssertionError):compare_rebuild(original,encoded)
        self.assertFalse(compare_rebuild(original,encoded,False))
        # A valid package with different content must still fail comparison.
        with (self.source/'README.md').open('a') as stream:stream.write('\nChanged content\n')
        changed=self.build('changed')
        with self.assertRaises(AssertionError):compare_rebuild(original,changed,False)
        with self.assertRaises(ValueError):compare_rebuild(original,self.mutate(original,'content'),False)

    def test_missing_licenses_or_files_fail_before_creating_artifact(self):
        data=json.loads((self.source/MANIFEST).read_text())
        data['runtime'].remove('assets/dualsense-blueprint.LICENSE.txt')
        (self.source/MANIFEST).write_text(json.dumps(data))
        with self.assertRaises(ValueError):self.build()
        self.assertFalse((self.root/'out').exists())
        (self.source/MANIFEST).write_bytes((BASE/MANIFEST).read_bytes())
        (self.source/'window.py').unlink()
        with self.assertRaises(FileNotFoundError):self.build()
        self.assertFalse((self.root/'out').exists())

    def test_legacy_format_remains_readable_and_new_maintenance_must_be_complete(self):
        data=inventory(self.source)
        data['runtime'].remove('uninstall.py')
        with self.assertRaisesRegex(ValueError,'Incomplete'):parse_manifest(data)
        data['runtime']=[name for name in data['runtime'] if name not in
                         {'maintenance.py','access_admin.py','packaging/remove-access.py.in','install_transaction.py','recovery_ui.py'}]
        self.assertIs(parse_manifest(data),data)
        data['runtime'].append('install_transaction.py')
        with self.assertRaisesRegex(ValueError,'Incomplete'):parse_manifest(data)

    def test_symlinked_source_file_and_directory_are_rejected(self):
        path=self.source/'README.md';path.unlink();path.symlink_to(BASE/'README.md')
        with self.assertRaises(ValueError):self.build()
        path.unlink();shutil.copyfile(BASE/'README.md',path)
        shutil.rmtree(self.source/'assets');(self.source/'assets').symlink_to(BASE/'assets',target_is_directory=True)
        with self.assertRaises(ValueError):self.build()

    def test_new_python_modules_require_explicit_inventory_review(self):
        (self.source/'new_feature.py').write_text('FEATURE = True\n')
        with self.assertRaisesRegex(ValueError,'unlisted Python modules'):self.build()
        self.assertFalse((self.root/'out').exists())

    def test_tampered_links_duplicates_and_escape_paths_are_not_extracted(self):
        archive=self.build()
        for kind in ('content','traversal','symlink','duplicate','extra'):
            with self.subTest(kind=kind):
                invalid=self.mutate(archive,kind)
                destination=self.root/('extract-'+kind)
                with self.assertRaises(ValueError):release.extract(invalid,destination)
                self.assertFalse(destination.exists())
        self.assertFalse((self.root/'outside.txt').exists())

    def test_extract_preserves_existing_destination_and_rebuilds_from_source(self):
        archive=self.build()
        destination=self.root/'existing';destination.mkdir();marker=destination/'my-data';marker.write_text('keep')
        with self.assertRaises(FileExistsError):release.extract(archive,destination)
        self.assertEqual(marker.read_text(),'keep')
        clean=self.root/'clean';release.extract(archive,clean)
        self.assertTrue((clean/release.RECORD).is_file())
        rebuilt,_=release.build(self.root/'rebuilt',clean,epoch=0)
        self.assertEqual(archive.read_bytes(),rebuilt.read_bytes())

    def test_unsafe_private_and_duplicate_inventory_entries_are_rejected(self):
        for name in ('.','assets/.','assets/./file','../secret','/absolute','assets/../secret','a//b','a\\b','assets/.env','work/a.txt','controllers.json','cache.pyc'):
            with self.subTest(name=name),self.assertRaises(ValueError):safe_name(name)
        data=json.loads((self.source/MANIFEST).read_text())
        data['development'].append(data['runtime'][0])
        (self.source/MANIFEST).write_text(json.dumps(data))
        with self.assertRaises(ValueError):self.build()

    def test_version_reading_never_executes_source(self):
        data=b'VERSION = "0.6.0-alpha.1"\nraise RuntimeError("must not run")\n'
        self.assertEqual(release.version_from(data),'0.6.0-alpha.1')
        with self.assertRaises(ValueError):release.version_from(b'VERSION = "../bad"')
        with self.assertRaises(ValueError):release.build(self.root/'bad-epoch',self.source,epoch=-1)

    def test_excessive_gzip_expansion_is_rejected_before_tar_headers(self):
        archive=self.root/'too-large.tar.gz'
        archive.write_bytes(gzip.compress(bytes(3*1024*1024)))
        with patch.object(release,'MAX_TOTAL',1024),self.assertRaisesRegex(ValueError,'Unpacked tar too large'):
            release.verify(archive)
