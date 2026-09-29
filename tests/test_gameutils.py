import os
import sys
import tempfile
import unittest

import gameutils


class SafeJoinTests(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()

    def test_relative_path_stays_inside(self):
        self.assertEqual(gameutils.safe_join(self.base, "Data/ruRU"),
                         os.path.join(os.path.abspath(self.base), "Data", "ruRU"))

    def test_rejects_escapes_and_absolute(self):
        for bad in ("..", "../x", "Data/../../x", "C:/Windows/x", "\\\\server\\share\\x", ""):
            self.assertIsNone(gameutils.safe_join(self.base, bad), bad)


class ConfigWtfTests(unittest.TestCase):
    def setUp(self):
        self.gd = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.gd, "WTF"))
        self.path = os.path.join(self.gd, "WTF", "Config.wtf")

    def _raw(self, data):
        with open(self.path, "wb") as f:
            f.write(data)

    def test_updates_existing_and_appends_new(self):
        self._raw(b'SET farclip "777"\r\nSET realmName "Chronos"\r\n')
        self.assertTrue(gameutils.write_config_wtf(self.gd, {"farclip": "1277", "spellEffectLevel": "6"}))
        cfg = gameutils.read_config_wtf(self.gd)
        self.assertEqual(cfg["farclip"], "1277")
        self.assertEqual(cfg["spellEffectLevel"], "6")
        self.assertEqual(cfg["realmName"], "Chronos")

    def test_none_removes_key(self):
        self._raw(b'SET farclip "777"\nSET gxWindow "1"\n')
        self.assertTrue(gameutils.write_config_wtf(self.gd, {"farclip": None}))
        cfg = gameutils.read_config_wtf(self.gd)
        self.assertNotIn("farclip", cfg)
        self.assertEqual(cfg["gxWindow"], "1")

    def test_preserves_non_utf8_bytes(self):
        self._raw('SET realmName "Хронос"\n'.encode("cp1251") + b'SET farclip "777"\n')
        self.assertTrue(gameutils.write_config_wtf(self.gd, {"farclip": "1277"}))
        with open(self.path, "rb") as f:
            raw = f.read()
        self.assertIn("Хронос".encode("cp1251"), raw)
        self.assertIn(b'SET farclip "1277"', raw)

    def test_key_match_ignores_case(self):
        """WoW не различает регистр CVar и при выходе пишет своё написание — дублей быть не должно."""
        self._raw(b'SET FarClip "777"\nSET gxWindow "1"\n')
        self.assertTrue(gameutils.write_config_wtf(self.gd, {"farclip": "1277"}))
        with open(self.path, "rb") as f:
            lines = [l for l in f.read().splitlines() if l.lower().startswith(b"set farclip ")]
        self.assertEqual(lines, [b'SET farclip "1277"'])

    def test_creates_file_when_missing(self):
        gd = tempfile.mkdtemp()
        self.assertTrue(gameutils.write_config_wtf(gd, {"farclip": "777"}))
        self.assertEqual(gameutils.read_config_wtf(gd), {"farclip": "777"})


class MpqTests(unittest.TestCase):
    def setUp(self):
        self.gd = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.gd, "Data", "ruRU"))
        with open(os.path.join(self.gd, "Data", "ruRU", "patch-ruRU-4.MPQ"), "wb") as f:
            f.write(b"x" * 2048)

    def test_status_and_toggle_roundtrip(self):
        def st():
            return gameutils.mpq_status(self.gd, "patch-ruRU-4.MPQ", "Data/ruRU")[:2]

        self.assertEqual(st(), (True, True))
        self.assertTrue(gameutils.toggle_mpq(self.gd, "patch-ruRU-4.MPQ", "Data/ruRU", False))
        self.assertTrue(os.path.isfile(os.path.join(self.gd, "Data", "ruRU", "patch-ruRU-4.MPQ.disabled")))
        self.assertEqual(st(), (True, False))
        self.assertTrue(gameutils.toggle_mpq(self.gd, "patch-ruRU-4.MPQ", "Data/ruRU", True))
        self.assertEqual(st(), (True, True))

    def test_missing_file(self):
        self.assertEqual(gameutils.mpq_status(self.gd, "nope.MPQ", "Data"), (False, False, 0))

    def test_rejects_bad_names_and_folders(self):
        self.assertFalse(gameutils.toggle_mpq(self.gd, "../x.MPQ", "Data", False))
        self.assertEqual(gameutils.mpq_status(self.gd, "patch-ruRU-4.MPQ", "../.."), (False, False, 0))


class KillOnCloseJobTests(unittest.TestCase):
    def test_child_dies_with_parent(self):
        """Распаковщик не должен переживать лаунчер: родитель завершился → ребёнок убит."""
        import subprocess
        import time
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        parent = (
            "import subprocess, sys, gameutils\n"
            "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],\n"
            "                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)\n"
            "gameutils.kill_on_close(p)\n"
            "print(p.pid, flush=True)\n"
        )
        out = subprocess.run([sys.executable, "-c", parent], cwd=root, capture_output=True, text=True, timeout=30)
        child_pid = int(out.stdout.strip())
        deadline = time.time() + 5
        while time.time() < deadline and gameutils.pid_alive(child_pid):
            time.sleep(0.1)
        self.assertFalse(gameutils.pid_alive(child_pid))


def _own_image_path():
    import ctypes
    buf = ctypes.create_unicode_buffer(32768)
    ctypes.windll.kernel32.GetModuleFileNameW(None, buf, len(buf))
    return buf.value


class ProcessTests(unittest.TestCase):
    def test_detects_current_interpreter(self):
        self.assertTrue(gameutils.is_process_running(os.path.basename(sys.executable)))

    def test_unknown_process(self):
        self.assertFalse(gameutils.is_process_running("plgames_no_such_process_42.exe"))

    def test_game_running_only_from_its_own_folder(self):
        exe = _own_image_path()
        name = os.path.basename(exe)
        self.assertTrue(gameutils.is_game_running(os.path.dirname(exe), exe_names=(name,)))
        # Тот же exe запущен, но из другой папки — это не «наша» игра
        self.assertFalse(gameutils.is_game_running(tempfile.mkdtemp(), exe_names=(name,)))
        self.assertFalse(gameutils.is_game_running(os.path.dirname(exe), exe_names=("plgames_nope_42.exe",)))
