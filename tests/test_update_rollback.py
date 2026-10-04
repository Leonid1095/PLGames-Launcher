"""Скрипт обновления (_update.bat) по-настоящему в cmd: новая версия поднялась — остаётся,
умерла без отметки — возвращается прежняя. Вместо exe — .cmd-«лаунчеры»."""

import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest

import app

NO_WINDOW = 0x08000000


@unittest.skipUnless(os.name == "nt", "скрипт обновления — для Windows")
class UpdateScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.current = os.path.join(self.tmp, "launcher.cmd")
        self.marker = os.path.join(self.tmp, "update-ok")
        self.failed = os.path.join(self.tmp, "update-failed.json")
        self.ran = os.path.join(self.tmp, "ran.txt")
        self.old_body = f'@echo off\r\necho old> "{self.ran}"\r\nexit\r\n'
        with open(self.current, "w", newline="") as f:
            f.write(self.old_body)

    def run_update(self, new_body):
        update = os.path.join(self.tmp, "new.cmd")
        with open(update, "w", newline="") as f:
            f.write(new_body)
        bat = os.path.join(self.tmp, "_update.bat")
        with open(bat, "w", encoding="utf-8", newline="") as f:
            f.write(app._update_script(self.current, update, self.current + ".bak", self.marker, self.failed,
                                       "9.9.9", wait_seconds=20, grace_seconds=4, settle_pings=1))
        subprocess.run(["cmd", "/c", bat], timeout=90, creationflags=NO_WINDOW)
        end = time.time() + 10  # запущенный «лаунчер» работает отдельно — ждём его след
        while not os.path.isfile(self.ran) and time.time() < end:
            time.sleep(0.1)
        with open(self.ran) as f:
            return f.read().strip()

    def test_healthy_update_stays(self):
        body = f'@echo off\r\necho ok> "{self.marker}"\r\necho new> "{self.ran}"\r\nexit\r\n'
        self.assertEqual(self.run_update(body), "new")
        with open(self.current, newline="") as f:
            self.assertEqual(f.read(), body)
        self.assertTrue(os.path.isfile(self.current + ".bak"))
        self.assertFalse(os.path.exists(self.failed))

    def test_update_that_dies_is_rolled_back(self):
        self.assertEqual(self.run_update("@echo off\r\nexit /b 1\r\n"), "old")
        with open(self.current, newline="") as f:
            self.assertEqual(f.read(), self.old_body)
        with open(self.failed, encoding="utf-8-sig") as f:
            self.assertEqual(json.load(f)["version"], "9.9.9")


class FailedUpdateTests(unittest.TestCase):
    def test_reads_rollback_note(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "update-failed.json")
        from unittest import mock
        with mock.patch.object(app, "_update_failed_path", return_value=path):
            self.assertEqual(app._failed_update(), {})
            with open(path, "w", encoding="utf-8") as f:
                f.write('{"version": "0.5.2"} \r\n')
            self.assertEqual(app._failed_update()["version"], "0.5.2")
            with open(path, "w", encoding="utf-8") as f:
                f.write("garbage")
            self.assertEqual(app._failed_update(), {})
