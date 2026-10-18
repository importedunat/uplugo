# SPDX-License-Identifier: GPL-3.0-only
import io
import hashlib
import os
import tempfile
import threading
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request
import artwork
import photo_download as photos
from gi.repository import GdkPixbuf


class Response(io.BytesIO):
    def __init__(self, data, content_type='image/png', length=None):
        super().__init__(data)
        self.headers=Message();self.headers['Content-Type']=content_type
        if length is not None:self.headers['Content-Length']=str(length)
    def geturl(self):return photos.CATALOG[0]['url']


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.env=patch.dict(os.environ,XDG_DATA_HOME=self.directory.name)
        self.env.start();self.addCleanup(self.env.stop)
        self.source=Path(self.directory.name)/'source.png'
        image=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,False,8,32,24)
        image.fill(0xf0f0f0ff);image.savev(str(self.source),'png',[],[])
        self.data=self.source.read_bytes()
        self.entry=photos.CATALOG[0]
        self.cancel=threading.Event()

    def fetch(self,response):
        with patch.object(photos,'build_opener') as factory:
            factory.return_value.open.return_value=response
            return photos.fetch_photo(self.entry,self.cancel)

    def test_clean_download_then_offline_cache(self):
        self.assertTrue(self.fetch(Response(self.data,length=len(self.data))))
        target=artwork.photo_path(self.entry['id'])
        self.assertEqual(target.read_bytes(),self.data)
        with patch.object(photos,'build_opener',side_effect=AssertionError('Network used for cached photo')):
            self.assertFalse(photos.fetch_photo(self.entry,self.cancel))
        self.assertFalse(list(artwork.library().glob('.download-*')))

    def test_user_import_wins_even_if_download_is_finishing(self):
        original=artwork.import_photo(self.entry['id'],self.source)
        downloaded=Path(self.directory.name)/'new.png'
        image=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,False,8,16,16)
        image.fill(0xff0000ff);image.savev(str(downloaded),'png',[],[])
        artwork.import_photo(self.entry['id'],downloaded,replace=False)
        self.assertEqual(original.read_bytes(),self.data)
        with patch.object(photos,'build_opener',side_effect=AssertionError('User image overwritten')):
            self.assertFalse(photos.fetch_photo(self.entry,self.cancel))

    def old_catalog_photo(self):
        artwork.import_photo(self.entry['id'],self.source)
        self.entry=dict(self.entry,replaces_sha256=[hashlib.sha256(self.data).hexdigest()])
        new=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,True,8,40,40)
        new.fill(0xff0000aa);new.savev(str(self.source),'png',[],[])
        return self.source.read_bytes()

    def test_catalog_upgrade_preserves_custom_photos(self):
        replacement=self.old_catalog_photo()
        self.assertTrue(self.fetch(Response(replacement)))
        self.assertEqual(artwork.photo_path(self.entry['id']).read_bytes(),replacement)
        with patch.object(photos,'build_opener',side_effect=AssertionError('Custom/cached photo fetched')):
            self.assertFalse(photos.fetch_photo(self.entry,self.cancel))

    def test_upgrade_rechecks_identity_after_download(self):
        replacement=self.old_catalog_photo()
        class ConcurrentImport(Response):
            def read(response,*args):
                artwork.import_photo(self.entry['id'],self.source)
                return super().read(*args)
        self.fetch(ConcurrentImport(self.data))
        self.assertEqual(artwork.photo_path(self.entry['id']).read_bytes(),replacement)

    def test_failed_upgrade_retains_old_photo(self):
        self.old_catalog_photo()
        with self.assertRaises(ValueError):self.fetch(Response(b'broken'))
        self.assertEqual(artwork.photo_path(self.entry['id']).read_bytes(),self.data)
        self.assertFalse(list(artwork.library().glob('.download-*')))

    def test_redirects_reject_http_credentials_and_unknown_hosts(self):
        for url in ['http://gmedia.playstation.com/x','https://other.test/x',
                    'https://gmedia.playstation.com.evil.test/x','https://a:b@gmedia.playstation.com/x',
                    'https://gmedia.playstation.com:444/x']:
            with self.subTest(url=url),self.assertRaises(ValueError):
                photos.OfficialRedirect().redirect_request(Request(self.entry['url']),None,302,'Found',{},url)

    def test_html_corrupt_truncated_and_oversize_leave_no_photo(self):
        cases=[Response(b'<html/>','text/html'),Response(b'bad image'),
               Response(self.data,length=len(self.data)+1),
               Response(self.data,length=photos.MAX_BYTES+1)]
        for response in cases:
            with self.subTest(response=response),self.assertRaises(ValueError):self.fetch(response)
            self.assertIsNone(artwork.photo_path(self.entry['id']))
            self.assertFalse(list(artwork.library().glob('.download-*')))
        with patch.object(photos,'MAX_BYTES',8),self.assertRaises(ValueError):self.fetch(Response(self.data))

    def test_cancel_leaves_no_partial_file(self):
        self.cancel.set()
        with self.assertRaises(photos.Cancelled):self.fetch(Response(self.data))
        self.assertIsNone(artwork.photo_path(self.entry['id']))
        self.assertFalse(list(artwork.library().glob('.download-*')))

    def test_offline_stops_after_three_failures_and_retry_resumes(self):
        reports=[];job=photos.PhotoDownloads(lambda key,state:reports.append(state))
        with patch.object(photos,'fetch_photo',side_effect=OSError('offline')) as fetch:
            job.start();job.worker.join(2)
            self.assertFalse(job.worker.is_alive())
            self.assertEqual(fetch.call_count,3)
            self.assertFalse(job.state['active']);self.assertEqual(len(job.state['failed']),3)
        with patch.object(photos,'fetch_photo',return_value=False) as fetch:
            job.start();job.worker.join(2)
            self.assertEqual(fetch.call_count,len(photos.CATALOG))
            self.assertEqual(job.state['available'],len(photos.CATALOG))
            self.assertFalse(job.state['failed'])
        # Callback snapshots do not mutate as the job advances.
        self.assertEqual(reports[0]['done'],1)

    def test_background_job_does_not_block_and_cancel_stops_queue(self):
        entered=threading.Event();release=threading.Event()
        def waiting(entry,cancel):
            entered.set();release.wait(2)
            if cancel.is_set():raise photos.Cancelled()
        job=photos.PhotoDownloads(lambda *args:None)
        with patch.object(photos,'fetch_photo',side_effect=waiting):
            try:
                self.assertTrue(job.start())
                self.assertTrue(entered.wait(1))
                self.assertFalse(job.start())
                job.stop()
            finally:release.set();job.worker.join(2)
        self.assertFalse(job.state['active']);self.assertTrue(job.state['stopped'])
        self.assertEqual(job.state['done'],0)

    def test_manifest_only_known_models_and_official_https(self):
        ids=[entry['id'] for entry in photos.CATALOG]
        self.assertEqual(len(ids),len(set(ids)))
        for entry in photos.CATALOG:
            self.assertIn(entry['id'],artwork.BY_ID)
            self.assertEqual(photos.checked_url(entry['url']),entry['url'])
            self.assertTrue(entry['source'].startswith('https://'))
