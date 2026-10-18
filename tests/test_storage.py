# SPDX-License-Identifier: GPL-3.0-only
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import dualsense


class StorageTests(unittest.TestCase):
    def test_atomic_private_settings_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config/controllers.json'
            value={'names':{'hid:sample':'Controle novo'},'modes':{'hid:sample':'charge'}}
            dualsense.write_json(path,value)
            with patch.object(dualsense,'SETTINGS',path):
                self.assertEqual(dualsense.settings()['names'],value['names'])
                self.assertEqual(dualsense.settings()['modes'],value['modes'])
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertEqual(list(path.parent.glob('.controllers.json*')),[])

    def test_failed_serialization_preserves_existing_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'controllers.json'
            dualsense.write_json(path,{'modes':{'hid:sample':'charge'}})
            before=path.read_bytes()
            with self.assertRaises(TypeError):dualsense.write_json(path,{'bad':object()})
            self.assertEqual(path.read_bytes(),before)

    def test_relative_xdg_path_is_not_used(self):
        with patch.dict(os.environ,{'XDG_CONFIG_HOME':'relative'}):
            self.assertEqual(dualsense.xdg_directory('XDG_CONFIG_HOME','.config'),Path.home()/'.config')

    def test_migration_preserves_names_modes_and_existing_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);legacy=root/'source';legacy.mkdir()
            config=root/'config/controllers.json';cache=root/'state/battery-readings.json'
            (legacy/'controllers.json').write_text(json.dumps({'names':{'hid:sample':'Original'},'modes':{'hid:sample':'charge'}}))
            (legacy/'battery-readings.json').write_text('{}')
            with patch.object(dualsense,'__file__',str(legacy/'dualsense.py')),patch.object(dualsense,'SETTINGS',config),patch.object(dualsense,'CACHE',cache),patch.object(dualsense,'STATE_DIR',cache.parent):
                dualsense.migrate_legacy()
                self.assertEqual(json.loads(config.read_text())['modes']['hid:sample'],'charge')
                dualsense.write_json(config,{'names':{'hid:sample':'Renomeado'}})
                dualsense.migrate_legacy()
                self.assertEqual(json.loads(config.read_text())['names']['hid:sample'],'Renomeado')
            self.assertTrue((legacy/'controllers.json').exists())
