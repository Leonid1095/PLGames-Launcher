import os
import shutil
import tempfile
import unittest
import zlib

import clientrepair as cr
import client_install

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "client-mini.rar")  # Data/realmlist.wtf, Data/ruRU/realmlist.wtf
NO_EXEMPT = lambda path: False  # noqa: E731 — в образце только realmlist.wtf, который обычно не проверяется


def crc(b):
    return f"{zlib.crc32(b) & 0xFFFFFFFF:08x}"


class FakeResp:
    def __init__(self, status, body, headers=None):
        self.status_code, self.body, self.headers = status, body, headers or {}

    def iter_content(self, chunk):
        for i in range(0, len(self.body), chunk):
            yield self.body[i:i + chunk]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class RangeSession:
    """Отдаёт кусок файла по заголовку Range, как nginx."""

    def __init__(self, path, honour_range=True):
        self.data, self.honour, self.calls = open(path, "rb").read(), honour_range, []

    def get(self, url, headers=None, stream=False, timeout=None):
        self.calls.append((url, dict(headers or {})))
        if not self.honour:
            return FakeResp(200, self.data)
        start, end = headers["Range"].split("=")[1].split("-")
        return FakeResp(206, self.data[int(start):int(end) + 1],
                        {"Content-Range": f"bytes {start}-{end}/{len(self.data)}"})


class ClientRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.index = cr.index_from_rar(FIXTURE)
        self.gd = os.path.join(self.tmp, "Game")
        for rel, body in (("Data/realmlist.wtf", None), ("Data/ruRU/realmlist.wtf", None)):
            os.makedirs(os.path.join(self.gd, *rel.split("/")[:-1]), exist_ok=True)
        self.extract_good_client()

    def extract_good_client(self):
        ex = client_install.find_extractor()
        out = os.path.join(self.tmp, "ref")
        cr._extract(ex, FIXTURE, out)
        for f in self.index["files"]:
            src = os.path.join(out, self.index["root"], *f["path"].split("/"))
            shutil.copyfile(src, self.path(f["path"]))

    def path(self, rel):
        return os.path.join(self.gd, *rel.split("/"))

    def test_index_strips_root_folder(self):
        self.assertEqual(self.index["root"], "PLGames_Wow3.3.5")
        self.assertEqual(self.index["archive"], "client-mini.rar")
        self.assertEqual([f["path"] for f in self.index["files"]], ["Data/realmlist.wtf", "Data/ruRU/realmlist.wtf"])
        self.assertEqual(cr.parse_index(self.index)["files"][0]["crc32"], "0b421448")

    def test_parse_index_rejects_unsafe_entries(self):
        for breaker in (lambda f: f.update(path="../evil.dll"), lambda f: f.update(path="C:/x"),
                        lambda f: f.update(crc32="zz"), lambda f: f.update(size=-1),
                        lambda f: f.update(offset="1")):
            bad = cr.index_from_rar(FIXTURE)
            breaker(bad["files"][0])
            with self.assertRaises(cr.ClientIndexError):
                cr.parse_index(bad)

    def test_clean_client_has_no_problems(self):
        self.assertEqual(cr.check(self.gd, self.index, full=True, exempt=NO_EXEMPT), [])

    def test_finds_missing_wrong_size_and_corrupted(self):
        os.remove(self.path("Data/realmlist.wtf"))
        with open(self.path("Data/ruRU/realmlist.wtf"), "r+b") as f:
            f.write(b"X")  # тот же размер, другое содержимое
        quick = cr.check(self.gd, self.index, exempt=NO_EXEMPT)
        self.assertEqual(quick, [{"path": "Data/realmlist.wtf", "problem": "missing"}])
        full = cr.check(self.gd, self.index, full=True, exempt=NO_EXEMPT)
        self.assertEqual(full, [{"path": "Data/realmlist.wtf", "problem": "missing"},
                                {"path": "Data/ruRU/realmlist.wtf", "problem": "crc"}])
        with open(self.path("Data/ruRU/realmlist.wtf"), "ab") as f:
            f.write(b"!")
        self.assertIn({"path": "Data/ruRU/realmlist.wtf", "problem": "size"},
                      cr.check(self.gd, self.index, exempt=NO_EXEMPT))

    def test_file_switched_off_by_edition_is_fine(self):
        os.rename(self.path("Data/realmlist.wtf"), self.path("Data/realmlist.wtf") + ".disabled")
        self.assertEqual(cr.check(self.gd, self.index, full=True, exempt=NO_EXEMPT), [])

    def test_default_exemptions(self):
        for p in ("Data/realmlist.wtf", "WTF/Config.wtf", "Interface/AddOns/WDM/WDM.toc", "Cache/x", "Logs/a.txt",
                  "PLGamesLauncher_Portable/PLGamesLauncher.exe"):
            self.assertTrue(cr.is_exempt(p), p)
        for p in ("Wow.exe", "Data/common.MPQ", "Data/ruRU/patch-ruRU-4.MPQ"):
            self.assertFalse(cr.is_exempt(p), p)

    def test_repair_from_local_archive(self):
        os.remove(self.path("Data/realmlist.wtf"))
        good = open(self.path("Data/ruRU/realmlist.wtf"), "rb").read()
        open(self.path("Data/ruRU/realmlist.wtf"), "wb").write(b"broken")
        problems = cr.check(self.gd, self.index, full=True, exempt=NO_EXEMPT)
        fixed, failed = cr.repair(self.gd, self.index, problems, [cr.LocalArchive(FIXTURE, self.index)])
        self.assertEqual((sorted(fixed), failed), (["Data/realmlist.wtf", "Data/ruRU/realmlist.wtf"], []))
        self.assertEqual(open(self.path("Data/ruRU/realmlist.wtf"), "rb").read(), good)
        self.assertEqual(cr.check(self.gd, self.index, full=True, exempt=NO_EXEMPT), [])
        self.assertFalse(os.path.exists(os.path.join(self.gd, "PLGames", "repair")))

    def test_repair_keeps_edition_switch(self):
        disabled = self.path("Data/realmlist.wtf") + ".disabled"
        os.rename(self.path("Data/realmlist.wtf"), disabled)
        open(disabled, "wb").write(b"x" * 28)
        problems = cr.check(self.gd, self.index, full=True, exempt=NO_EXEMPT)
        self.assertEqual(problems, [{"path": "Data/realmlist.wtf", "problem": "crc"}])
        cr.repair(self.gd, self.index, problems, [cr.LocalArchive(FIXTURE, self.index)])
        self.assertFalse(os.path.exists(self.path("Data/realmlist.wtf")))
        self.assertEqual(crc(open(disabled, "rb").read()), "0b421448")

    def test_repair_over_http_range_and_source_order(self):
        os.remove(self.path("Data/ruRU/realmlist.wtf"))
        problems = cr.check(self.gd, self.index, exempt=NO_EXEMPT)
        wrong_local = os.path.join(self.tmp, "other.rar")
        open(wrong_local, "wb").write(b"not the same archive")
        s = RangeSession(FIXTURE)
        sources = [cr.LocalArchive(wrong_local, self.index), cr.HttpArchive(["https://srv/c.rar"], s)]
        fixed, failed = cr.repair(self.gd, self.index, problems, sources)
        self.assertEqual((fixed, failed), (["Data/ruRU/realmlist.wtf"], []))
        f = self.index["files"][1]
        self.assertEqual(s.calls, [("https://srv/c.rar", {"Range": f"bytes={f['offset']}-{f['offset'] + f['length'] - 1}"})])

    def test_server_without_range_support_is_not_downloaded_whole(self):
        os.remove(self.path("Data/ruRU/realmlist.wtf"))
        problems = cr.check(self.gd, self.index, exempt=NO_EXEMPT)
        fixed, failed = cr.repair(self.gd, self.index, problems,
                                  [cr.HttpArchive(["https://srv/c.rar"], RangeSession(FIXTURE, honour_range=False))])
        self.assertEqual(fixed, [])
        self.assertEqual(failed[0][0], "Data/ruRU/realmlist.wtf")
        self.assertFalse(os.path.exists(self.path("Data/ruRU/realmlist.wtf")))
