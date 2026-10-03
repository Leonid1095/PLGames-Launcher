import os
import shutil
import tempfile
import unittest

import useraddons


def toc(path, **fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for key, value in fields.items():
            f.write(f"## {key.replace('_', '-')}: {value}\n")
        f.write("Core.lua\n")


class UserAddonsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.gd = os.path.join(self.tmp, "Game")
        self.ad = os.path.join(self.gd, "Interface", "AddOns")
        os.makedirs(self.ad)
        toc(self.addon("Questie", "Questie.toc"), Interface="30300", Title="Questie")       # из каталога
        toc(self.addon("Blizzard_Calendar", "Blizzard_Calendar.toc"), Interface="30300")    # встроенный клиента
        toc(self.addon("PLGames_LiveCity", "PLGames_LiveCity.toc"), Interface="30300")      # аддон сервера
        toc(self.addon("Prat", "Prat.toc"), Interface="30300", Title="|cff00ff00Prat|r 3.0", Version="3.4.1",
            Title_ruRU="Prat (чат)")
        toc(self.addon("Prat_Modules", "Prat_Modules.toc"), Interface="30300", Dependencies="Prat")
        toc(self.addon("Retail", "Retail.toc"), Interface="100200", Title="Retail Thing")
        toc(self.addon("Broken-master", "Broken.toc"), Interface="30300", Title="Broken")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def addon(self, *parts):
        return os.path.join(self.ad, *parts)

    def scan(self):
        return {a["folder"]: a for a in useraddons.scan(self.gd, owned={"questie"}, server={"plgames_livecity"})}

    def test_lists_only_players_own_addons_grouped_by_dependency(self):
        found = self.scan()
        self.assertEqual(sorted(found), ["Broken-master", "Prat", "Retail"])
        prat = found["Prat"]
        self.assertEqual(prat["title"], "Prat (чат)")
        self.assertEqual(prat["version"], "3.4.1")
        self.assertEqual(prat["folders"], ["Prat", "Prat_Modules"])
        self.assertTrue(prat["enabled"] and prat["compatible"] and prat["loads"])

    def test_flags_problems_the_game_would_hit(self):
        found = self.scan()
        self.assertFalse(found["Retail"]["compatible"])  # не для 3.3.5
        self.assertFalse(found["Broken-master"]["loads"])  # имя папки не совпадает с .toc
        self.assertEqual(found["Broken-master"]["title"], "Broken")

    def test_disable_moves_whole_group_aside_and_enable_returns_it(self):
        ok, _ = useraddons.set_enabled(self.gd, "Prat", False, owned={"questie"}, server={"plgames_livecity"})
        self.assertTrue(ok)
        self.assertFalse(os.path.exists(self.addon("Prat")))
        self.assertFalse(os.path.exists(self.addon("Prat_Modules")))
        off = os.path.join(self.gd, "PLGames", "addons-off")
        self.assertTrue(os.path.isfile(os.path.join(off, "Prat_Modules", "Prat_Modules.toc")))
        self.assertFalse(self.scan()["Prat"]["enabled"])
        ok, _ = useraddons.set_enabled(self.gd, "Prat", True, owned={"questie"}, server={"plgames_livecity"})
        self.assertTrue(ok)
        self.assertTrue(os.path.isfile(self.addon("Prat_Modules", "Prat_Modules.toc")))
        self.assertTrue(self.scan()["Prat"]["enabled"])

    def test_refuses_foreign_or_unknown_folders(self):
        for folder in ("Questie", "PLGames_LiveCity", "Blizzard_Calendar", "Nope", "..", "Prat_Modules"):
            ok, msg = useraddons.set_enabled(self.gd, folder, False, owned={"questie"}, server={"plgames_livecity"})
            self.assertFalse(ok, folder)
            self.assertTrue(msg)
        self.assertTrue(os.path.isdir(self.addon("Questie")))

    def test_refuses_when_target_already_exists(self):
        os.makedirs(os.path.join(self.gd, "PLGames", "addons-off", "Retail"))
        ok, msg = useraddons.set_enabled(self.gd, "Retail", False, owned=set(), server=set())
        self.assertFalse(ok)
        self.assertTrue(os.path.isdir(self.addon("Retail")))

    def test_server_addon_info_from_bundle(self):
        info = useraddons.read_toc(self.addon("Prat", "Prat.toc"))
        self.assertEqual(info["Interface"], "30300")
        self.assertEqual(useraddons.clean_title("|cff5fb4ffLive City|r"), "Live City")

    def test_client_parts_are_not_players_addons(self):
        toc(self.addon("WDM", "WDM.toc"), Interface="30300", Title="WoW Dungeon Maps")
        self.assertNotIn("WDM", self.scan())
        self.assertFalse(useraddons.set_enabled(self.gd, "WDM", False, owned=set(), server=set())[0])

    def test_empty_folders_are_not_addons(self):
        os.makedirs(self.addon("Atlas"))
        os.makedirs(self.addon("Atlas_Battlegrounds", "Images"))
        self.assertNotIn("Atlas", self.scan())
        self.assertNotIn("Atlas_Battlegrounds", self.scan())

    def test_missing_addons_dir_is_empty_list(self):
        self.assertEqual(useraddons.scan(os.path.join(self.tmp, "nothing"), owned=set(), server=set()), [])
