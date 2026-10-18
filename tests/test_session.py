# SPDX-License-Identifier: GPL-3.0-only
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import launch
import session


class SessionTests(unittest.TestCase):
    def test_missing_unreachable_and_slow_systemd_are_optional(self):
        for result in (FileNotFoundError(), subprocess.TimeoutExpired('systemctl',3),
                       subprocess.CompletedProcess([],1)):
            with patch.object(session.subprocess,'run',side_effect=result if isinstance(result,Exception) else None,
                              return_value=result):
                self.assertFalse(session.systemd_available())

    def test_reopening_existing_app_never_starts_or_restarts_service(self):
        with patch.object(launch,'activate_existing',return_value=True), \
             patch.object(launch,'systemd_available') as service, \
             patch.object(launch.subprocess,'Popen') as spawn, \
             patch.object(launch.os,'execv') as execute:
            launch.open_app()
            service.assert_not_called();spawn.assert_not_called();execute.assert_not_called()

    def test_no_systemd_runs_the_same_single_instance_entrypoint(self):
        with patch.object(launch,'activate_existing',return_value=False), \
             patch.object(launch,'systemd_available',return_value=False), \
             patch.object(launch.os,'execv') as execute, \
             patch.object(launch.subprocess,'run') as command:
            launch.open_app('/tmp/example path')
            execute.assert_called_once_with('/usr/bin/python3',['/usr/bin/python3','/tmp/example path/window.py'])
            command.assert_not_called()

    def test_pending_update_opens_recovery_before_service_or_hardware(self):
        from maintenance import Locations
        with tempfile.TemporaryDirectory() as root:
            locations=Locations(Path(root)/'data',Path(root)/'config')
            locations.base.mkdir(parents=True);locations.pending.write_text('{}')
            with patch.object(launch,'activate_existing',return_value=False), \
                 patch.object(launch.Locations,'current',return_value=locations), \
                 patch.object(launch,'systemd_available') as manager, \
                 patch.object(launch.os,'execv') as execute:
                launch.open_app('/tmp/example')
                execute.assert_called_once_with('/usr/bin/python3',['/usr/bin/python3','/tmp/example/recovery_ui.py'])
                manager.assert_not_called()

    def test_failed_service_does_not_launch_unsupervised_competing_process(self):
        with tempfile.TemporaryDirectory() as root:
            config=Path(root)/'config/dualsense-usb'
            unit=config.parent/'systemd/user'/session.UNIT
            unit.parent.mkdir(parents=True);unit.touch()
            with patch.object(launch,'CONFIG_DIR',config), \
                 patch.object(launch,'activate_existing',return_value=False), \
                 patch.object(launch,'systemd_available',return_value=True), \
                 patch('install.import_desktop_environment'), \
                 patch.object(launch.subprocess,'run',side_effect=[subprocess.CompletedProcess([],1),subprocess.CalledProcessError(1,'start')]), \
                 patch.object(launch.subprocess,'Popen') as spawn, \
                 patch.object(launch.os,'execv') as execute:
                with self.assertRaises(subprocess.CalledProcessError):launch.open_app()
                spawn.assert_not_called();execute.assert_not_called()

    def test_detached_launch_logs_privately_without_enabling_autostart(self):
        with tempfile.TemporaryDirectory() as root:
            state=Path(root)/'state'
            with patch.object(launch,'STATE_DIR',state), \
                 patch.object(launch,'activate_existing',return_value=False), \
                 patch.object(launch,'systemd_available',return_value=False), \
                 patch.object(launch.subprocess,'Popen') as spawn:
                launch.open_app('/tmp/example',detach=True)
                self.assertEqual((state/'app.log').stat().st_mode&0o777,0o600)
                self.assertTrue(spawn.call_args.kwargs['start_new_session'])
                self.assertEqual(spawn.call_args.args[0],['/usr/bin/python3','/tmp/example/window.py'])
