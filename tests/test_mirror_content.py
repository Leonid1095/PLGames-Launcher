import hashlib
import json
import os
import shutil
import tempfile
import unittest

from tools import mirror_content as mc


class Resp:
    def __init__(self, status, body):
        self.status_code, self.body = status, body

    def iter_content(self, n):
        yield self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Session:
    def __init__(self, files):
        self.files, self.calls = files, []

    def get(self, url, stream=False, timeout=None):
        self.calls.append(url)
        return Resp(200, self.files[url]) if url in self.files else Resp(404, b"")


def manifest(body, cid="dxvk", ver="2.4", name="d3d9.dll"):
    return {"components": [{"id": cid, "type": "files", "files": [{
        "path": name, "size": len(body), "sha256": hashlib.sha256(body).hexdigest(),
        "urls": [mc.SERVER_BASE + f"{cid}/{ver}/{name}", mc.GITHUB + f"{cid}-{ver}-{name}"]}]}]}


class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.dest = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dest, True)
        self.dll = b"MZ dll"
        self.files = {mc.GITHUB + "manifest2.json": json.dumps(manifest(self.dll)).encode(),
                      mc.GITHUB + "manifest.json": json.dumps(manifest(self.dll)).encode(),
                      mc.GITHUB + "client-index.json": b"{}",
                      mc.GITHUB + "dxvk-2.4-d3d9.dll": self.dll}

    def test_lays_out_server_paths_and_skips_what_is_there(self):
        s = Session(self.files)
        self.assertEqual(mc.mirror(self.dest, s, log=lambda *_: None), (1, 1))  # оба манифеста ссылаются на один файл
        with open(os.path.join(self.dest, "dxvk", "2.4", "d3d9.dll"), "rb") as f:
            self.assertEqual(f.read(), self.dll)
        for name in ("manifest2.json", "manifest.json", "client-index.json"):
            self.assertTrue(os.path.isfile(os.path.join(self.dest, name)))
        self.assertEqual(mc.mirror(self.dest, Session(self.files), log=lambda *_: None), (0, 2))

    def test_corrupted_download_is_refused_and_manifest_not_replaced(self):
        self.files[mc.GITHUB + "dxvk-2.4-d3d9.dll"] = b"MZ evil"
        with self.assertRaises(RuntimeError):
            mc.mirror(self.dest, Session(self.files), log=lambda *_: None)
        self.assertFalse(os.path.exists(os.path.join(self.dest, "dxvk", "2.4", "d3d9.dll")))
        self.assertFalse(os.path.exists(os.path.join(self.dest, "manifest2.json")))

    def test_rejects_paths_outside_the_folder(self):
        bad = manifest(self.dll)
        bad["components"][0]["files"][0]["urls"][0] = mc.SERVER_BASE + "../../etc/passwd"
        with self.assertRaises(ValueError):
            mc.entries(bad)
