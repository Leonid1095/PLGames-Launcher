import os
import shutil
import sys
import tempfile
import time
import unittest
import zipfile

import client_install as ci

SLT = """7-Zip 24.09 (x64)

Listing archive: C:\\x\\PLGames.rar

--
Path = C:\\x\\PLGames.rar
Type = Rar5

----------
Path = PLGames_Wow3.3.5\\Data\\common.MPQ
Folder = -
Size = 2856083241

Path = PLGames_Wow3.3.5\\Wow.exe
Folder = -
Size = 7704216

Path = PLGames_Wow3.3.5
Folder = +
Size = 0
"""

TAR_V = """drwxr-xr-x  0 0      0           0 Mar 05  2014 PLGames_Wow3.3.5/Data
-rw-r--r--  0 0      0    15588224 Mar 05  2014 PLGames_Wow3.3.5/Battle.net.dll
-rw-r--r--  0 0      0  1756781838 Mar 05  2014 PLGames_Wow3.3.5/Data/common-2.MPQ
"""


class ParseTests(unittest.TestCase):
    def test_7z_slt(self):
        self.assertEqual(ci._parse_7z_slt(SLT), (2856083241 + 7704216, {"PLGames_Wow3.3.5"}))

    def test_tar_sizes(self):
        self.assertEqual(ci._parse_tar_sizes(TAR_V), 15588224 + 1756781838)

    def test_roots_from_names(self):
        names = "PLGames_Wow3.3.5/Battle.net.dll\n./other/x\nroot.txt\n.hidden/y\n"
        self.assertEqual(ci._roots_from_names(names), {"PLGames_Wow3.3.5", "other", "root.txt", ".hidden"})


class FindGameDirTests(unittest.TestCase):
    def test_finds_nested_and_respects_depth(self):
        root = tempfile.mkdtemp()
        deep = os.path.join(root, "A", "B")
        os.makedirs(deep)
        open(os.path.join(deep, "Wow.exe"), "wb").close()
        self.assertEqual(ci.find_game_dir(root), deep)
        self.assertIsNone(ci.find_game_dir(root, max_depth=1))


def _wait(job, timeout=60):
    end = time.time() + timeout
    while job.status()["state"] in ("preparing", "extracting") and time.time() < end:
        time.sleep(0.05)
    return job.status()


class FakeExtractor:
    ok_codes = (0,)

    def __init__(self, total, roots):
        self.total, self.roots = total, roots

    def inspect(self, archive):
        return self.total, self.roots

    def extract_cmd(self, archive, dest):
        raise AssertionError("не должен дойти до распаковки")


HAS_EXTRACTOR = ci.find_extractor() is not None


class ExtractJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dest = os.path.join(self.tmp, "dest")
        os.makedirs(self.dest)

    def _zip(self, files):
        path = os.path.join(self.tmp, "client.zip")
        with zipfile.ZipFile(path, "w") as z:
            for name, data in files.items():
                z.writestr(name, data)
        return path

    @unittest.skipUnless(HAS_EXTRACTOR, "нет ни 7-Zip, ни tar.exe")
    def test_extracts_and_finds_game_dir(self):
        archive = self._zip({"Client/Wow.exe": b"exe", "Client/Data/common.MPQ": b"m" * 5000})
        done = []
        job = ci.ExtractJob(poll_interval=0.05)
        self.assertEqual(job.start(archive, self.dest, on_done=done.append), (True, ""))
        st = _wait(job)
        self.assertEqual(st["state"], "finished", st)
        game_dir = os.path.join(self.dest, "Client")
        self.assertEqual(os.path.normcase(st["game_dir"]), os.path.normcase(game_dir))
        self.assertEqual(done, [st["game_dir"]])
        self.assertTrue(os.path.isfile(os.path.join(game_dir, "Data", "common.MPQ")))
        self.assertFalse(os.path.exists(os.path.join(self.dest, ci.STAGING_DIR)))
        self.assertEqual(st["progress"], 100)

    @unittest.skipUnless(HAS_EXTRACTOR, "нет ни 7-Zip, ни tar.exe")
    def test_existing_target_fails_before_extracting(self):
        archive = self._zip({"Client/Wow.exe": b"exe"})
        os.makedirs(os.path.join(self.dest, "Client"))
        open(os.path.join(self.dest, "Client", "mine.txt"), "w").close()
        job = ci.ExtractJob(poll_interval=0.05)
        job.start(archive, self.dest)
        st = _wait(job)
        self.assertEqual(st["state"], "error")
        self.assertIn("уже есть", st["error"])
        self.assertEqual(os.listdir(os.path.join(self.dest, "Client")), ["mine.txt"])

    @unittest.skipUnless(HAS_EXTRACTOR, "нет ни 7-Zip, ни tar.exe")
    def test_archive_without_wow_exe(self):
        archive = self._zip({"Stuff/readme.txt": b"hi"})
        job = ci.ExtractJob(poll_interval=0.05)
        job.start(archive, self.dest)
        st = _wait(job)
        self.assertEqual(st["state"], "error")
        self.assertIn("wow.exe", st["error"])

    @unittest.skipUnless(HAS_EXTRACTOR, "нет ни 7-Zip, ни tar.exe")
    def test_corrupt_archive(self):
        archive = os.path.join(self.tmp, "broken.rar")
        with open(archive, "wb") as f:
            f.write(b"definitely not an archive")
        job = ci.ExtractJob(poll_interval=0.05)
        job.start(archive, self.dest)
        self.assertEqual(_wait(job)["state"], "error")

    def test_not_enough_space(self):
        archive = self._zip({"Client/Wow.exe": b"exe"})
        job = ci.ExtractJob(extractor_factory=lambda: FakeExtractor(10 ** 16, {"Client"}), poll_interval=0.05)
        job.start(archive, self.dest)
        st = _wait(job)
        self.assertEqual(st["state"], "error")
        self.assertIn("Недостаточно места", st["error"])

    def test_no_extractor(self):
        archive = self._zip({"Client/Wow.exe": b"exe"})
        job = ci.ExtractJob(extractor_factory=lambda: None, poll_interval=0.05)
        job.start(archive, self.dest)
        st = _wait(job)
        self.assertEqual(st["state"], "error")
        self.assertIn("распаковщик", st["error"])

    def test_cancel_kills_extractor_and_cleans_staging(self):
        archive = self._zip({"Client/Wow.exe": b"exe"})

        class Slow(FakeExtractor):
            def extract_cmd(self, archive, dest):
                code = (f"import os, time; open(os.path.join(r'{dest}', 'part.bin'), 'wb').write(b'x' * 10); "
                        "time.sleep(30)")
                return [sys.executable, "-c", code]

        job = ci.ExtractJob(extractor_factory=lambda: Slow(100, {"Client"}), poll_interval=0.05)
        job.start(archive, self.dest)
        end = time.time() + 10
        while job.status()["state"] != "extracting" and time.time() < end:
            time.sleep(0.05)
        time.sleep(0.5)
        job.cancel()
        job.join(10)
        self.assertEqual(job.status()["state"], "cancelled")
        self.assertFalse(os.path.exists(os.path.join(self.dest, ci.STAGING_DIR)))
        self.assertFalse(os.path.exists(os.path.join(self.dest, "Client")))

    def test_start_validates_inputs(self):
        job = ci.ExtractJob()
        self.assertEqual(job.start(os.path.join(self.tmp, "nope.rar"), self.dest), (False, "Архив не найден"))
        archive = self._zip({"a.txt": b"1"})
        self.assertEqual(job.start(archive, os.path.join(self.tmp, "nodir")), (False, "Папка назначения не найдена"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
