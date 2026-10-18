# SPDX-License-Identifier: GPL-3.0-only
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from access_guard import active_clients,AccessGuard


class AccessGuardTests(unittest.TestCase):
    def test_only_matching_controller_and_other_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            proc=Path(directory)
            for pid,node,name in [(123,'/dev/hidraw8','steam'),(124,'/dev/input/event4','game.exe'),(125,'/dev/input/event9','unrelated'),(999,'/dev/hidraw8','our app')]:
                process=proc/str(pid);(process/'fd').mkdir(parents=True)
                (process/'fd/7').symlink_to(node);(process/'comm').write_text(name)
            self.assertEqual(active_clients({'/dev/hidraw8'},proc,999),{'steam'})
            self.assertEqual(active_clients({'/dev/input/event4'},proc,999),{'game.exe'})
            self.assertEqual(active_clients({'/dev/input/event0'},proc,999),set())

    def test_manual_play_exception_and_disabled_guard(self):
        guard=AccessGuard()
        with patch('access_guard.controller_nodes',return_value={'/dev/hidraw8'}),patch('access_guard.active_clients',return_value={'steam'}) as scan:
            device=Path('/sys/bus/usb/devices/1-1')
            ids={'1-1':'hid:sample'}
            self.assertEqual(guard.check([device],ids,{'enabled':False},now=0),{})
            self.assertEqual(guard.check([device],ids,{'enabled':True,'play_exceptions':['hid:sample']},now=1),{})
            scan.assert_not_called()
            self.assertEqual(guard.check([device],ids,{'enabled':True},now=4),{'hid:sample':'steam'})
            self.assertEqual(guard.check([device],ids,{'enabled':True},now=5),{})
            self.assertEqual(scan.call_count,1)
