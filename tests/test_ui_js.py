"""Синтаксис JS интерфейса лаунчера: одна опечатка в app.HTML — и окно открывается пустым.
Нужен node (есть в CI windows-latest); без него тест пропускается."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

import app


@unittest.skipUnless(shutil.which("node"), "нужен node")
class UiScriptTests(unittest.TestCase):
    def test_script_parses(self):
        html = app.HTML.replace("%RESOLUTIONS%", json.dumps(app.RESOLUTIONS))
        scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
        self.assertTrue(scripts)
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "ui.js")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(scripts))
        r = subprocess.run(["node", "--check", path], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
