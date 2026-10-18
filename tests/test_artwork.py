# SPDX-License-Identifier: GPL-3.0-only
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import artwork
from gi.repository import GdkPixbuf


class ArtworkTests(unittest.TestCase):
    def test_import_preserves_original_and_rejects_corrupt_replacement(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,XDG_DATA_HOME=directory):
            source=Path(directory)/'source.png'
            picture=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,False,8,24,16)
            picture.fill(0xeeeeeeff);picture.savev(str(source),'png',[],[])
            original=source.read_bytes()
            destination=artwork.import_photo('black',source)
            self.assertEqual(destination.read_bytes(),original)
            self.assertEqual(source.read_bytes(),original)
            self.assertEqual(destination.parent,artwork.library())
            bad=Path(directory)/'broken.png';bad.write_bytes(b'not an image')
            with self.assertRaises(ValueError):artwork.import_photo('black',bad)
            self.assertEqual(destination.read_bytes(),original)

    def test_unknown_model_cannot_write_outside_library(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,XDG_DATA_HOME=directory):
            with self.assertRaises(ValueError):artwork.import_photo('../../other',Path(directory)/'photo.png')
            self.assertFalse(artwork.library().exists())
            self.assertIsNone(artwork.photo_path('../../other'))

    def test_public_preview_ignores_private_photos(self):
        with patch.object(artwork,'library',side_effect=AssertionError('Private library accessed')):
            pixbuf,photo=artwork.picture('white',180,120,local=False)
            self.assertFalse(photo)
            self.assertGreater(pixbuf.get_width(),0)

    def test_catalog_keys_are_unique_and_safe(self):
        self.assertEqual(len(artwork.MODELS),len(artwork.BY_ID))
        for entry in artwork.MODELS:
            self.assertRegex(entry['id'],r'^[a-z0-9-]+$')
            self.assertRegex(entry['color'],r'^#[0-9a-fA-F]{6}$')
