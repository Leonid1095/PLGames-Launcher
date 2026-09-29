import json
import os
import unittest

import content

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class DefaultManifestTests(unittest.TestCase):
    def test_builtin_manifest_is_valid_and_covers_all_legacy_patches(self):
        with open(os.path.join(ROOT, "content_default.json"), encoding="utf-8") as f:
            m = content.parse_manifest(json.load(f))
        self.assertEqual([e.id for e in m.editions], ["classic", "remaster", "ultra"])
        names = {mpq.name for c in m.components for mpq in c.mpqs}
        self.assertEqual(len(names), 19)
        self.assertIn("Patch-ruRU-V.mpq", names)
