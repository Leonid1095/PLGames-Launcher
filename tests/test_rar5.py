import os
import shutil
import subprocess
import tempfile
import unittest
import zlib

import rar5

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "client-mini.rar")  # 2 файла из настоящего архива клиента
SEVENZIP = os.path.join(ROOT, "7z.exe")


class VintTests(unittest.TestCase):
    def test_reads_multibyte_values(self):
        self.assertEqual(rar5.read_vint(bytes([0x05]), 0), (5, 1))
        self.assertEqual(rar5.read_vint(bytes([0x80, 0x01]), 0), (128, 2))
        self.assertEqual(rar5.read_vint(bytes([0xFF, 0xFF, 0x03, 0x09]), 0), (65535, 3))

    def test_truncated_value_is_an_error(self):
        with self.assertRaises(rar5.RarError):
            rar5.read_vint(bytes([0x80]), 0)


class IndexTests(unittest.TestCase):
    def test_index_of_real_archive_piece(self):
        idx = rar5.build_index(FIXTURE)
        self.assertEqual(idx["archive_size"], os.path.getsize(FIXTURE))
        names = [f["name"] for f in idx["files"]]
        self.assertEqual(names, ["PLGames_Wow3.3.5/Data/realmlist.wtf", "PLGames_Wow3.3.5/Data/ruRU/realmlist.wtf"])
        self.assertEqual([f["size"] for f in idx["files"]], [28, 30])
        self.assertEqual(idx["files"][0]["crc32"], "0b421448")
        # куски идут подряд сразу за главным заголовком
        main_len = len(bytes.fromhex(idx["main_header"]))
        self.assertEqual(idx["files"][0]["offset"], len(rar5.SIGNATURE) + main_len)
        self.assertEqual(idx["files"][1]["offset"], idx["files"][0]["offset"] + idx["files"][0]["length"])

    def test_rejects_damaged_header_and_foreign_files(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        data = bytearray(open(FIXTURE, "rb").read())
        data[len(rar5.SIGNATURE) + 6] ^= 0xFF  # байт внутри главного заголовка
        bad = os.path.join(tmp, "bad.rar")
        open(bad, "wb").write(bytes(data))
        with self.assertRaises(rar5.RarError):
            rar5.build_index(bad)
        zipfile = os.path.join(tmp, "x.rar")
        open(zipfile, "wb").write(b"PK\x03\x04 not a rar")
        with self.assertRaises(rar5.RarError):
            rar5.build_index(zipfile)


@unittest.skipUnless(os.path.isfile(SEVENZIP), "нужен 7z.exe рядом с лаунчером")
class MiniArchiveTests(unittest.TestCase):
    def test_single_piece_extracts_with_valid_crc(self):
        idx = rar5.build_index(FIXTURE)
        second = idx["files"][1]
        with open(FIXTURE, "rb") as f:
            f.seek(second["offset"])
            piece = f.read(second["length"])
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        mini = os.path.join(tmp, "one.rar")
        open(mini, "wb").write(rar5.mini_archive(bytes.fromhex(idx["main_header"]), [piece]))
        r = subprocess.run([SEVENZIP, "x", "-y", "-o" + os.path.join(tmp, "out"), mini], capture_output=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        out = open(os.path.join(tmp, "out", "PLGames_Wow3.3.5", "Data", "ruRU", "realmlist.wtf"), "rb").read()
        self.assertEqual(len(out), 30)
        self.assertEqual(f"{zlib.crc32(out) & 0xFFFFFFFF:08x}", second["crc32"])
