import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import build_addon_packs as bap  # noqa: E402


class AddonMembersTests(unittest.TestCase):
    def test_strip_rename_and_exclude(self):
        package = {"strip_prefix": "Questie-abc/", "rename_root_to": "Questie-335", "exclude_paths": ["tools/"],
                   "addon_folders": ["Questie-335"]}
        names = ["Questie-abc/", "Questie-abc/Questie-335.toc", "Questie-abc/Modules/Q.lua",
                 "Questie-abc/tools/gen.py", "Questie-abc/tools/data.lua", "Questie-abc/shot.png", "Other/x.lua"]
        got = [rel for _, rel in bap.addon_members(package, names)]
        self.assertEqual(got, ["Questie-335/Questie-335.toc", "Questie-335/Modules/Q.lua"])

    def test_only_listed_folders_and_addon_file_types(self):
        package = {"strip_prefix": "", "addon_folders": ["DBM-Core", "DBM-GUI"]}
        names = ["DBM-Core/DBM-Core.toc", "DBM-GUI/x.xml", "DBM-VPVEM/voice.ogg", "DBM-Core/run.exe",
                 "DBM-Core/../evil.lua"]
        got = [rel for _, rel in bap.addon_members(package, names)]
        self.assertEqual(got, ["DBM-Core/DBM-Core.toc", "DBM-GUI/x.xml"])

    def test_license_label(self):
        self.assertEqual(bap.license_label("none stated (no LICENSE in repo)"), "лицензия не указана")
        self.assertEqual(bap.license_label("All rights reserved (in TOC)"), "все права у автора")
        self.assertEqual(bap.license_label("GPL-2.0"), "GPL-2.0")

    def test_clean_version(self):
        self.assertEqual(bap.clean_version("10.1.13_alpha (main @ 6165654)"), "10.1.13_alpha")
        self.assertEqual(bap.clean_version("v40000-1.0.0 (code)"), "v40000-1.0.0")
