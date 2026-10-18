# SPDX-License-Identifier: GPL-3.0-only
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import autostart


class AutostartTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = self.root/'config'
        self.launcher = self.root/'app with "quotes" $HOME %u'/'launch.py'
        self.launcher.parent.mkdir()
        self.launcher.write_text('# launcher\n')

    def tearDown(self):
        self.temporary.cleanup()

    def test_enable_writes_a_hidden_start_entry_and_disable_removes_it(self):
        self.assertFalse(autostart.enabled(self.config))
        autostart.set_enabled(True, self.launcher, self.config)
        path = autostart.entry_path(self.config)
        text = path.read_text()
        self.assertTrue(autostart.enabled(self.config))
        self.assertIn('--background', text)
        self.assertIn(autostart.MARKER, text)
        self.assertEqual(path.stat().st_mode & 0o777, 0o644)
        # Desktop Entry quoting: no unescaped quote, variable or field code.
        exec_line = next(line for line in text.splitlines() if line.startswith('Exec='))
        self.assertNotIn(' $HOME', exec_line.replace('\\\\$HOME', ''))
        self.assertIn('%%u', exec_line)
        autostart.set_enabled(False, self.launcher, self.config)
        self.assertFalse(path.exists())
        self.assertFalse(autostart.enabled(self.config))

    def test_disabled_in_desktop_settings_counts_as_off(self):
        autostart.set_enabled(True, self.launcher, self.config)
        path = autostart.entry_path(self.config)
        path.write_text(path.read_text().replace('X-GNOME-Autostart-enabled=true', 'X-GNOME-Autostart-enabled=false'))
        self.assertFalse(autostart.enabled(self.config))

    def test_foreign_entries_and_links_are_preserved(self):
        path = autostart.entry_path(self.config)
        path.parent.mkdir(parents=True)
        path.write_text('[Desktop Entry]\nExec=other\n')
        for wanted in (True, False):
            with self.assertRaises(ValueError):
                autostart.set_enabled(wanted, self.launcher, self.config)
        self.assertIsNone(autostart.remove_if_ours(self.config))
        self.assertEqual(path.read_text(), '[Desktop Entry]\nExec=other\n')
        path.unlink();path.symlink_to(self.launcher)
        with self.assertRaises(ValueError):
            autostart.set_enabled(True, self.launcher, self.config)
        self.assertEqual(self.launcher.read_text(), '# launcher\n')

    def test_missing_or_relative_launcher_is_refused(self):
        for launcher in (self.root/'missing.py', Path('launch.py')):
            with self.assertRaises(ValueError):
                autostart.set_enabled(True, launcher, self.config)
        self.assertFalse(autostart.entry_path(self.config).exists())

    def test_uninstall_removes_only_its_own_entry(self):
        autostart.set_enabled(True, self.launcher, self.config)
        self.assertEqual(autostart.remove_if_ours(self.config), autostart.entry_path(self.config))
        self.assertFalse(autostart.entry_path(self.config).exists())
        self.assertIsNone(autostart.remove_if_ours(self.config))

    def test_hidden_start_marker_is_private_single_use_and_short_lived(self):
        state = self.root/'state'
        autostart.request_hidden_start(state)
        self.assertEqual((state/autostart.HIDDEN).stat().st_mode & 0o777, 0o600)
        self.assertTrue(autostart.consume_hidden_start(state))
        self.assertFalse(autostart.consume_hidden_start(state))
        autostart.request_hidden_start(state)
        self.assertFalse(autostart.consume_hidden_start(state, now=time.time()+autostart.HIDDEN_MAX_AGE+1))
        self.assertFalse((state/autostart.HIDDEN).exists())
        (state/autostart.HIDDEN).write_text('not a time')
        self.assertFalse(autostart.consume_hidden_start(state))

    def test_background_launch_never_reveals_a_running_app_and_manual_launch_clears_the_request(self):
        import launch
        state = self.root/'state'
        with patch.object(launch, 'STATE_DIR', state), patch.object(launch.os, 'geteuid', return_value=1000):
            with patch.object(launch, 'instance_running', return_value=True), patch.object(launch, 'activate_existing') as activate:
                launch.open_app(background=True)
            activate.assert_not_called()
            self.assertFalse((state/autostart.HIDDEN).exists())
            autostart.request_hidden_start(state)
            with patch.object(launch, 'activate_existing', return_value=True) as activate:
                launch.open_app()
            activate.assert_called_once()
            self.assertFalse((state/autostart.HIDDEN).exists(), 'A manual launch must show the window')


if __name__ == '__main__':
    unittest.main()
