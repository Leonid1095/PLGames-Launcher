import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

import content

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import build_content_manifest as bcm  # noqa: E402

DLL = b"MZ dxvk d3d9 x32"


def src_manifest(image=""):
    return {
        "schema": 1, "content_version": "2026.10.1",
        "components": [
            {"id": "hd_water", "name": "HD-вода", "type": "mpq",
             "files": [{"name": "Patch-ruRU-V.mpq", "folder": "Data/ruRU"}]},
            {"id": "dxvk", "name": "DXVK", "type": "files", "version": "2.4",
             "files": [{"path": "d3d9.dll", "src": "files/dxvk/d3d9.dll"}]},
        ],
        "editions": [
            {"id": "classic", "name": "Классика", "components": []},
            {"id": "remaster", "name": "Ремастер", "image": image, "components": ["hd_water", "dxvk"]},
        ],
    }


class BuildContentManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "files", "dxvk"))
        with open(os.path.join(self.tmp, "files", "dxvk", "d3d9.dll"), "wb") as f:
            f.write(DLL)
        self.src = os.path.join(self.tmp, "manifest.src.json")
        self.out = os.path.join(self.tmp, "out")

    def _write(self, data):
        with open(self.src, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_builds_both_layouts_with_hashes(self):
        self._write(src_manifest())
        manifest = bcm.build(self.src, self.out, server_base="https://srv.test/c/", github_base="https://gh.test/r/")
        entry = manifest["components"][1]["files"][0]
        self.assertEqual(entry["size"], len(DLL))
        self.assertEqual(entry["sha256"], hashlib.sha256(DLL).hexdigest())
        self.assertEqual(entry["urls"], ["https://srv.test/c/dxvk/2.4/d3d9.dll", "https://gh.test/r/dxvk-2.4-d3d9.dll"])
        self.assertNotIn("src", entry)
        with open(os.path.join(self.out, "server", "dxvk", "2.4", "d3d9.dll"), "rb") as f:
            self.assertEqual(f.read(), DLL)
        self.assertTrue(os.path.isfile(os.path.join(self.out, "github", "dxvk-2.4-d3d9.dll")))
        for layout in ("server", "github"):
            with open(os.path.join(self.out, layout, "manifest.json"), encoding="utf-8") as f:
                content.parse_manifest(json.load(f))

    def test_refuses_manifest_the_launcher_would_reject(self):
        self._write(src_manifest(image="http://insecure/img.jpg"))
        with self.assertRaises(content.ManifestError):
            bcm.build(self.src, self.out)

    def test_repo_source_manifest_builds(self):
        out = os.path.join(self.tmp, "repo-out")
        bcm.build(os.path.join(ROOT, "content", "manifest.src.json"), out)
        self.assertTrue(os.path.isfile(os.path.join(out, "server", "manifest.json")))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
