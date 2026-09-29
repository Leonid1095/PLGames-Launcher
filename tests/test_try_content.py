import json
import os
import shutil
import sys
import tempfile
import unittest

import content
import gameutils
from tests.test_build_content_manifest import DLL, src_manifest
from tests.test_content import make_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import build_content_manifest as bcm  # noqa: E402
import try_content  # noqa: E402


class TryContentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "files", "dxvk"))
        with open(os.path.join(self.tmp, "files", "dxvk", "d3d9.dll"), "wb") as f:
            f.write(DLL)
        src = os.path.join(self.tmp, "manifest.src.json")
        with open(src, "w", encoding="utf-8") as f:
            json.dump(src_manifest(), f)
        self.dist = os.path.join(self.tmp, "dist")
        bcm.build(src, self.dist)
        self.gd = make_client(self.tmp)

    def test_applies_edition_from_local_build_and_reverts(self):
        state = try_content.apply(self.gd, self.dist, edition="remaster", is_running=lambda gd: False)
        self.assertEqual(state["edition"], "remaster")
        with open(os.path.join(self.gd, "d3d9.dll"), "rb") as f:
            self.assertEqual(f.read(), DLL)
        try_content.apply(self.gd, self.dist, edition="classic", is_running=lambda gd: False)
        self.assertFalse(os.path.exists(os.path.join(self.gd, "d3d9.dll")))
        self.assertTrue(gameutils.mpq_status(self.gd, "Patch-ruRU-V.mpq", "Data/ruRU")[0])
        self.assertEqual(content.load_state(self.gd)["edition"], "classic")

    def test_unknown_edition(self):
        with self.assertRaises(SystemExit):
            try_content.apply(self.gd, self.dist, edition="nope", is_running=lambda gd: False)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
