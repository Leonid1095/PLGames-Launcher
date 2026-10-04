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


class ProjectTabsTests(unittest.TestCase):
    """Вкладки верхнего меню — свои у каждой игры."""

    def test_defaults_follow_editions_flag(self):
        self.assertEqual(app.project_tabs({"editions": True}), ["play", "editions", "addons", "news", "settings"])
        self.assertEqual(app.project_tabs({}), ["play", "news", "settings"])

    def test_own_list_keeps_order_and_drops_unknown(self):
        proj = {"editions": True, "tabs": ["play", "addons", "mods", "editions", "addons", "settings"]}
        self.assertEqual(app.project_tabs(proj), ["play", "addons", "editions", "settings"])

    def test_edition_tabs_only_for_projects_with_editions(self):
        """Издания и аддоны делает лаунчер: сервер не может включить их чужой игре."""
        self.assertEqual(app.project_tabs({"tabs": ["play", "editions", "addons", "news"]}),
                         ["play", "news", "settings"])

    def test_play_and_settings_are_always_there(self):
        self.assertEqual(app.project_tabs({"tabs": ["news"]}), ["play", "news", "settings"])
        self.assertEqual(app.project_tabs({"tabs": "news"}), ["play", "news", "settings"])

    def test_server_manifest_can_set_tabs(self):
        server = {"projects": [{"id": "wow_chronos", "tabs": ["play", "news", "editions", "settings"]},
                               {"id": "newgame", "name": "New", "tabs": ["play", "news", "editions"]}]}

        class Resp:
            status_code = 200

            def json(self):
                return server

        with mock.patch("requests.get", return_value=Resp()):
            projects = {p["id"]: p for p in app.fetch_manifest()}
        self.assertEqual(app.project_tabs(projects["wow_chronos"]), ["play", "news", "editions", "settings"])
        self.assertEqual(app.project_tabs(projects["newgame"]), ["play", "news", "settings"])

    def test_get_projects_reports_tabs(self):
        api = app.Api.__new__(app.Api)
        api.projects = [dict(app.PROJECTS[0]), {"id": "other", "name": "Other", "full_name": "", "subtitle": "",
                                                 "type": "x", "description": "", "exe": ""}]
        import json
        got = {p["id"]: p["tabs"] for p in json.loads(api.get_projects())}
        self.assertEqual(got["wow_chronos"], ["play", "editions", "addons", "news", "settings"])
        self.assertEqual(got["other"], ["play", "news", "settings"])

    def test_only_wow_is_listed(self):
        """Вольная Гавань (Windrose) снята: сервер отключён."""
        self.assertEqual([p["id"] for p in app.PROJECTS], ["wow_chronos"])


class LaunchSelfCheckTests(unittest.TestCase):
    """Перед игрой: испорченное издание — восстановление, испорченный клиент — предложение починить."""

    def setUp(self):
        import clientrepair
        import zlib
        self.tmp = tempfile.mkdtemp()
        self.gd = os.path.join(self.tmp, "Game")
        os.makedirs(self.gd)
        with open(os.path.join(self.gd, "Wow.exe"), "wb") as f:
            f.write(b"abd")
        self.api = app.Api.__new__(app.Api)
        self.api.projects = [{"id": "wow", "exe": "Wow.exe", "editions": True, "realmlist": ""}]
        self.api.settings = {"game_paths": {"wow": self.gd}}
        self.heal_result = "ok"

        class Editions:
            def busy(inner):
                return False

            def heal(inner, gd):
                return self.heal_result
        self.api._editions = Editions()
        self.api._client_job = clientrepair.ClientJob()
        self.api._client_index = clientrepair.parse_index({
            "schema": 1, "archive": "c.rar", "archive_size": 10, "root": "", "main_header": "00",
            "files": [{"path": "Wow.exe", "size": 3, "crc32": f"{zlib.crc32(b'abc') & 0xFFFFFFFF:08x}",
                       "offset": 0, "length": 1}]})

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def launch(self):
        import json
        with mock.patch("subprocess.Popen") as popen:
            res = json.loads(self.api.launch_game("wow"))
        return res, popen

    def test_broken_client_asks_to_repair_and_does_not_start(self):
        res, popen = self.launch()
        self.assertTrue(res.get("need_repair"))
        self.assertIn("Wow.exe", res["msg"])
        popen.assert_not_called()

    def test_player_can_launch_anyway(self):
        import json
        with mock.patch("subprocess.Popen") as popen:
            res = json.loads(self.api.launch_game("wow", True))
        self.assertFalse(res.get("need_repair"))
        popen.assert_called_once()

    def test_edition_being_healed_waits(self):
        self.heal_result = "repair"
        res, popen = self.launch()
        self.assertTrue(res.get("healing"))
        popen.assert_not_called()
