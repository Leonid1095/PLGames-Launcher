import os
import tempfile
import unittest
from unittest import mock

import app


class BareFilenameTests(unittest.TestCase):
    """client_archive может прийти из серверного манифеста — только имя файла, без путей."""

    def test_rejects_paths(self):
        for bad in ("../x.rar", "C:\\Windows\\x.rar", "..\\x.rar", "a/b.rar", "..", ".", "", None):
            self.assertEqual(app._bare_filename(bad), "", bad)

    def test_accepts_plain_name(self):
        self.assertEqual(app._bare_filename("PLGames_Wow3.3.5.rar"), "PLGames_Wow3.3.5.rar")


class UpdateAssetTests(unittest.TestCase):
    """apply_update подменяет exe лаунчера скачанным файлом — брать можно только сам лаунчер."""

    def asset(self, name):
        return {"name": name, "browser_download_url": "https://example.test/" + name}

    def test_picks_launcher_exe_even_when_other_exe_comes_first(self):
        assets = [self.asset("aria2c.exe"), self.asset("PLGamesLauncher_Setup.exe"),
                  self.asset("PLGamesLauncher.exe"), self.asset("PLGames_Wow3.3.5.torrent")]
        self.assertEqual(app._pick_update_asset(assets), "https://example.test/PLGamesLauncher.exe")

    def test_no_launcher_exe_means_no_url(self):
        assets = [self.asset("aria2c.exe"), self.asset("PLGamesLauncher_Setup.exe")]
        self.assertEqual(app._pick_update_asset(assets), "")
        self.assertEqual(app._pick_update_asset(None), "")


class SupportFileTests(unittest.TestCase):
    """aria2c.exe и .torrent: файл рядом с лаунчером важнее вшитого в exe."""

    def setUp(self):
        self.local = tempfile.mkdtemp()
        self.bundle = tempfile.mkdtemp()
        patcher_dir = mock.patch.object(app, "_launcher_dir", return_value=self.local)
        patcher_bundled = mock.patch.object(app, "_bundled", side_effect=lambda n: os.path.join(self.bundle, n))
        patcher_dir.start()
        patcher_bundled.start()
        self.addCleanup(patcher_dir.stop)
        self.addCleanup(patcher_bundled.stop)

    def touch(self, folder, name):
        path = os.path.join(folder, name)
        with open(path, "wb") as f:
            f.write(b"x")
        return path

    def test_prefers_file_next_to_launcher(self):
        local = self.touch(self.local, "aria2c.exe")
        self.touch(self.bundle, "aria2c.exe")
        self.assertEqual(app._support_file("aria2c.exe"), local)

    def test_falls_back_to_bundled(self):
        bundled = self.touch(self.bundle, "aria2c.exe")
        self.assertEqual(app._support_file("aria2c.exe"), bundled)

    def test_missing_everywhere_points_next_to_launcher(self):
        self.assertEqual(app._support_file("aria2c.exe"), os.path.join(self.local, "aria2c.exe"))
