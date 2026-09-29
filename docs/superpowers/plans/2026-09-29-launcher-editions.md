# Графические издания и установка клиента — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Лаунчер умеет устанавливать клиент (распаковка RAR5 после торрента) и переключать графические издания Классика / Ремастер / Ультра / «Своё» по манифесту компонентов.

**Architecture:**
- Логика вынесена из монолита `app.py` в модули без UI:
  - `gameutils` — работа с папкой клиента;
  - `client_install` — распаковка;
  - `content` — манифест, состояние, планировщик, исполнитель с откатом;
  - `hardware` — видеокарта и рекомендация;
  - `editions` — фасад для UI с фоновым потоком.
- `app.py` получает тонкие методы `Api`, вкладку «ИЗДАНИЯ» и изменения в JS.
- Манифест ищется по цепочке: сервер → GitHub → кэш → встроенный `content_default.json`.

**Tech Stack:** Python 3.13, pywebview 5, requests, `unittest`, PyInstaller onefile, системный `tar.exe` (libarchive) или вшитый 7-Zip.

**Spec:** `docs/superpowers/specs/2026-09-29-launcher-editions-design.md`

## Global Constraints

- Рабочий каталог — `launcher/` (репозиторий PLGames-Launcher). Все пути ниже указаны относительно него.
- Тесты: `python -m unittest discover -s tests -t . -v`, запускать из `launcher/`.
- Модули `gameutils`, `client_install`, `content`, `hardware` и `editions` не импортируют `webview` и `app`.
- Все подпроцессы запускаются с `creationflags=0x08000000` (`CREATE_NO_WINDOW`).
- Путь из манифеста или `state.json` в файловую систему попадает только через `gameutils.safe_join`.
- Разрешённые расширения файлов из манифеста: `.dll .ini .fx .fxh .png .dds .mpq .conf .txt .json`. Имя `wow.exe` запрещено.
- Ссылки в манифесте только `https://`.
- `wow.exe` не патчим. На проде Warden делает 31 проверку памяти, действие — кик.
- Тексты интерфейса на русском.
- Коммиты делаются только по команде владельца. Шаги «Commit» ниже означают точки, где коммит уместен.

---

### Task 1: `gameutils.py` — общие утилиты клиента

**Files:**
- Create: `gameutils.py`, `tests/__init__.py`, `tests/test_gameutils.py`
- Modify: `app.py`. Удалить определения `_safe_join`, `read_config_wtf`, `write_config_wtf`, `mpq_status`, `toggle_mpq` (строки ~262-395) и импортировать их из `gameutils`.

**Interfaces — Produces:**
- `NO_WINDOW: int`
- `safe_join(base: str, rel: str) -> str | None`
- `read_config_wtf(gp) -> dict[str, str]`
- `write_config_wtf(gp, settings: dict[str, str | None]) -> bool`. Значение `None` удаляет ключ.
- `mpq_status(gp, fname, folder) -> tuple[bool, bool, float]`: установлен, включён, размер в МБ.
- `toggle_mpq(gp, fname, folder, enable) -> bool`
- `is_process_running(image_name) -> bool`

- [ ] **Step 1: тесты** (`tests/test_gameutils.py`)

```python
import os
import sys
import tempfile
import unittest

import gameutils


class SafeJoinTests(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()

    def test_relative_path_stays_inside(self):
        self.assertEqual(gameutils.safe_join(self.base, "Data/ruRU"),
                         os.path.join(os.path.abspath(self.base), "Data", "ruRU"))

    def test_rejects_escapes_and_absolute(self):
        for bad in ("..", "../x", "Data/../../x", "C:/Windows/x", "\\\\server\\share\\x", ""):
            self.assertIsNone(gameutils.safe_join(self.base, bad), bad)


class ConfigWtfTests(unittest.TestCase):
    def setUp(self):
        self.gd = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.gd, "WTF"))
        self.path = os.path.join(self.gd, "WTF", "Config.wtf")

    def _raw(self, data):
        with open(self.path, "wb") as f:
            f.write(data)

    def test_updates_existing_and_appends_new(self):
        self._raw(b'SET farclip "777"\r\nSET realmName "Chronos"\r\n')
        self.assertTrue(gameutils.write_config_wtf(self.gd, {"farclip": "1277", "spellEffectLevel": "6"}))
        cfg = gameutils.read_config_wtf(self.gd)
        self.assertEqual(cfg["farclip"], "1277")
        self.assertEqual(cfg["spellEffectLevel"], "6")
        self.assertEqual(cfg["realmName"], "Chronos")

    def test_none_removes_key(self):
        self._raw(b'SET farclip "777"\nSET gxWindow "1"\n')
        self.assertTrue(gameutils.write_config_wtf(self.gd, {"farclip": None}))
        cfg = gameutils.read_config_wtf(self.gd)
        self.assertNotIn("farclip", cfg)
        self.assertEqual(cfg["gxWindow"], "1")

    def test_preserves_non_utf8_bytes(self):
        self._raw('SET realmName "Хронос"\n'.encode("cp1251") + b'SET farclip "777"\n')
        self.assertTrue(gameutils.write_config_wtf(self.gd, {"farclip": "1277"}))
        with open(self.path, "rb") as f:
            raw = f.read()
        self.assertIn("Хронос".encode("cp1251"), raw)
        self.assertIn(b'SET farclip "1277"', raw)

    def test_creates_file_when_missing(self):
        gd = tempfile.mkdtemp()
        self.assertTrue(gameutils.write_config_wtf(gd, {"farclip": "777"}))
        self.assertEqual(gameutils.read_config_wtf(gd), {"farclip": "777"})


class MpqTests(unittest.TestCase):
    def setUp(self):
        self.gd = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.gd, "Data", "ruRU"))
        with open(os.path.join(self.gd, "Data", "ruRU", "patch-ruRU-4.MPQ"), "wb") as f:
            f.write(b"x" * 2048)

    def test_status_and_toggle_roundtrip(self):
        st = lambda: gameutils.mpq_status(self.gd, "patch-ruRU-4.MPQ", "Data/ruRU")[:2]
        self.assertEqual(st(), (True, True))
        self.assertTrue(gameutils.toggle_mpq(self.gd, "patch-ruRU-4.MPQ", "Data/ruRU", False))
        self.assertTrue(os.path.isfile(os.path.join(self.gd, "Data", "ruRU", "patch-ruRU-4.MPQ.disabled")))
        self.assertEqual(st(), (True, False))
        self.assertTrue(gameutils.toggle_mpq(self.gd, "patch-ruRU-4.MPQ", "Data/ruRU", True))
        self.assertEqual(st(), (True, True))

    def test_missing_file(self):
        self.assertEqual(gameutils.mpq_status(self.gd, "nope.MPQ", "Data"), (False, False, 0))

    def test_rejects_bad_names_and_folders(self):
        self.assertFalse(gameutils.toggle_mpq(self.gd, "../x.MPQ", "Data", False))
        self.assertEqual(gameutils.mpq_status(self.gd, "patch-ruRU-4.MPQ", "../.."), (False, False, 0))


class ProcessTests(unittest.TestCase):
    def test_detects_current_interpreter(self):
        self.assertTrue(gameutils.is_process_running(os.path.basename(sys.executable)))

    def test_unknown_process(self):
        self.assertFalse(gameutils.is_process_running("plgames_no_such_process_42.exe"))
```

- [ ] **Step 2:** запустить тесты и убедиться, что они падают: `ModuleNotFoundError: gameutils`.

- [ ] **Step 3: реализация** (`gameutils.py`)

```python
"""Утилиты для папки клиента WoW 3.3.5a: безопасные пути, Config.wtf, MPQ-патчи,
проверка запущенной игры. Без UI — общие для app.py, content.py и тестов."""

import os
import re
import subprocess

NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: не мигать консолью из GUI-процесса

_SET_RE = re.compile(r'^SET\s+(\S+)\s+"?([^"]*)"?\s*$')
_SET_KEY_RE = re.compile(r'^SET\s+(\S+)\s+')


def safe_join(base, rel):
    """Join rel onto base, refusing absolute paths or ones that escape base.
    Защищает от путей из манифеста/сервера вида '..\\..\\' или 'C:/Windows/...'."""
    if not rel:
        return None
    full = os.path.abspath(os.path.normpath(os.path.join(base, rel)))
    base_abs = os.path.abspath(os.path.normpath(base))
    try:
        if os.path.commonpath([base_abs, full]) != base_abs:
            return None
    except ValueError:
        return None  # разные диски
    return full


def _config_path(gp):
    return os.path.join(gp, "WTF", "Config.wtf")


def read_config_wtf(gp):
    cfg = {}
    p = _config_path(gp)
    if not os.path.isfile(p):
        return cfg
    try:
        with open(p, "r", encoding="utf-8", errors="surrogateescape") as f:
            for line in f:
                m = _SET_RE.match(line.strip())
                if m:
                    cfg[m.group(1)] = m.group(2)
    except OSError:
        pass
    return cfg


def write_config_wtf(gp, settings):
    """Пишет SET-строки в WTF/Config.wtf, сохраняя остальные строки байт-в-байт.
    Значение None удаляет ключ. True — если файл записан."""
    p = _config_path(gp)
    lines, written = [], set()
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8", errors="surrogateescape") as f:
                for line in f:
                    m = _SET_KEY_RE.match(line.strip())
                    if m and m.group(1) in settings:
                        key = m.group(1)
                        written.add(key)
                        if settings[key] is not None:
                            lines.append(f'SET {key} "{settings[key]}"\n')
                    else:
                        lines.append(line if line.endswith("\n") else line + "\n")
        except OSError:
            return False
    for key, value in settings.items():
        if key not in written and value is not None:
            lines.append(f'SET {key} "{value}"\n')
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", errors="surrogateescape") as f:
            f.writelines(lines)
        return True
    except OSError:
        return False


def _mpq_paths(gp, fname, folder):
    if not fname or os.path.basename(fname) != fname or "/" in fname:
        return None, None
    base = safe_join(gp, folder)
    if not base:
        return None, None
    active = os.path.join(base, fname)
    return active, active + ".disabled"


def mpq_status(gp, fname, folder):
    """(установлен, включён, размер МБ). Выключенный патч лежит как <имя>.disabled."""
    active, disabled = _mpq_paths(gp, fname, folder)
    if active and os.path.isfile(active):
        return True, True, round(os.path.getsize(active) / 1048576, 1)
    if disabled and os.path.isfile(disabled):
        return True, False, round(os.path.getsize(disabled) / 1048576, 1)
    return False, False, 0


def toggle_mpq(gp, fname, folder, enable):
    active, disabled = _mpq_paths(gp, fname, folder)
    if not active:
        return False
    try:
        if enable and os.path.isfile(disabled):
            os.rename(disabled, active)
        elif not enable and os.path.isfile(active):
            os.rename(active, disabled)
        return True
    except OSError:
        return False


def is_process_running(image_name):
    """True, если процесс с таким именем exe запущен (tasklist, без консоли)."""
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/NH", "/FO", "CSV"],
                             capture_output=True, timeout=10, creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return False
    text = out.stdout.decode("cp866", errors="replace").lower()
    return f'"{image_name.lower()}"' in text
```

- [ ] **Step 4: `app.py` импортирует утилиты.** Удалить из `app.py` старые определения пяти функций и добавить после `from urllib.parse import urlparse`:

```python
import gameutils
from gameutils import (safe_join as _safe_join, read_config_wtf, write_config_wtf,
                       mpq_status, toggle_mpq)
```

- [ ] **Step 5:** тесты проходят, `python -c "import ast;ast.parse(open('app.py',encoding='utf-8').read())"` не падает.

- [ ] **Step 6: Commit.** `feat: gameutils — общие утилиты клиента с тестами`

---

### Task 2: `client_install.py` — распаковка клиента

**Files:** Create `client_install.py`, `tests/test_client_install.py`

**Interfaces:**
- Consumes: `gameutils.NO_WINDOW`
- Produces:
  - `ExtractError(Exception)`
  - `find_extractor() -> SevenZip | SystemTar | None`
  - `find_game_dir(root, max_depth=2) -> str | None`
  - `ExtractJob(extractor_factory=find_extractor, poll_interval=1.0)`, методы:
    - `.start(archive, dest, on_done=None) -> (bool, str)`
    - `.status() -> dict`, где `state` ∈ `idle | preparing | extracting | finished | error | cancelled`; поля `progress`, `done_mb`, `total_mb`, `game_dir`, `error`, `archive`
    - `.cancel()`
    - `.running() -> bool`
  - `on_done(game_dir)` вызывается в потоке при успехе.

- [ ] **Step 1: тесты** (`tests/test_client_install.py`)

```python
import os
import shutil
import tempfile
import time
import unittest
import zipfile

import client_install as ci

SLT = """7-Zip 24.09 (x64)

Listing archive: C:\\x\\PLGames.rar

--
Path = C:\\x\\PLGames.rar
Type = Rar5

----------
Path = PLGames_Wow3.3.5\\Data\\common.MPQ
Folder = -
Size = 2856083241

Path = PLGames_Wow3.3.5\\Wow.exe
Folder = -
Size = 7704216

Path = PLGames_Wow3.3.5
Folder = +
Size = 0
"""

TAR_V = """drwxr-xr-x  0 0      0           0 Mar 05  2014 PLGames_Wow3.3.5/Data
-rw-r--r--  0 0      0    15588224 Mar 05  2014 PLGames_Wow3.3.5/Battle.net.dll
-rw-r--r--  0 0      0  1756781838 Mar 05  2014 PLGames_Wow3.3.5/Data/common-2.MPQ
"""


class ParseTests(unittest.TestCase):
    def test_7z_slt(self):
        self.assertEqual(ci._parse_7z_slt(SLT), (2856083241 + 7704216, {"PLGames_Wow3.3.5"}))

    def test_tar_sizes(self):
        self.assertEqual(ci._parse_tar_sizes(TAR_V), 15588224 + 1756781838)

    def test_roots_from_names(self):
        names = "PLGames_Wow3.3.5/Battle.net.dll\n./other/x\nroot.txt\n.hidden/y\n"
        self.assertEqual(ci._roots_from_names(names), {"PLGames_Wow3.3.5", "other", "root.txt", ".hidden"})


class FindGameDirTests(unittest.TestCase):
    def test_finds_nested_and_respects_depth(self):
        root = tempfile.mkdtemp()
        deep = os.path.join(root, "A", "B")
        os.makedirs(deep)
        open(os.path.join(deep, "Wow.exe"), "wb").close()
        self.assertEqual(ci.find_game_dir(root), deep)
        self.assertIsNone(ci.find_game_dir(root, max_depth=1))


def _wait(job, timeout=60):
    end = time.time() + timeout
    while job.status()["state"] in ("preparing", "extracting") and time.time() < end:
        time.sleep(0.05)
    return job.status()


class FakeExtractor:
    ok_codes = (0,)

    def __init__(self, total, roots):
        self.total, self.roots = total, roots

    def inspect(self, archive):
        return self.total, self.roots

    def extract_cmd(self, archive, dest):
        raise AssertionError("не должен дойти до распаковки")


class ExtractJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dest = os.path.join(self.tmp, "dest")
        os.makedirs(self.dest)

    def _zip(self, files):
        path = os.path.join(self.tmp, "client.zip")
        with zipfile.ZipFile(path, "w") as z:
            for name, data in files.items():
                z.writestr(name, data)
        return path

    @unittest.skipIf(ci.find_extractor() is None, "нет ни 7-Zip, ни tar.exe")
    def test_extracts_and_finds_game_dir(self):
        archive = self._zip({"Client/Wow.exe": b"exe", "Client/Data/common.MPQ": b"m" * 5000})
        done = []
        job = ci.ExtractJob(poll_interval=0.05)
        self.assertEqual(job.start(archive, self.dest, on_done=done.append), (True, ""))
        st = _wait(job)
        self.assertEqual(st["state"], "finished", st)
        game_dir = os.path.join(self.dest, "Client")
        self.assertEqual(os.path.normcase(st["game_dir"]), os.path.normcase(game_dir))
        self.assertEqual(done, [st["game_dir"]])
        self.assertTrue(os.path.isfile(os.path.join(game_dir, "Data", "common.MPQ")))
        self.assertFalse(os.path.exists(os.path.join(self.dest, ci.STAGING_DIR)))
        self.assertEqual(st["progress"], 100)

    @unittest.skipIf(ci.find_extractor() is None, "нет ни 7-Zip, ни tar.exe")
    def test_existing_target_fails_before_extracting(self):
        archive = self._zip({"Client/Wow.exe": b"exe"})
        os.makedirs(os.path.join(self.dest, "Client"))
        open(os.path.join(self.dest, "Client", "mine.txt"), "w").close()
        job = ci.ExtractJob(poll_interval=0.05)
        job.start(archive, self.dest)
        st = _wait(job)
        self.assertEqual(st["state"], "error")
        self.assertIn("уже есть", st["error"])
        self.assertEqual(os.listdir(os.path.join(self.dest, "Client")), ["mine.txt"])

    @unittest.skipIf(ci.find_extractor() is None, "нет ни 7-Zip, ни tar.exe")
    def test_archive_without_wow_exe(self):
        archive = self._zip({"Stuff/readme.txt": b"hi"})
        job = ci.ExtractJob(poll_interval=0.05)
        job.start(archive, self.dest)
        st = _wait(job)
        self.assertEqual(st["state"], "error")
        self.assertIn("wow.exe", st["error"])

    @unittest.skipIf(ci.find_extractor() is None, "нет ни 7-Zip, ни tar.exe")
    def test_corrupt_archive(self):
        archive = os.path.join(self.tmp, "broken.rar")
        with open(archive, "wb") as f:
            f.write(b"definitely not an archive")
        job = ci.ExtractJob(poll_interval=0.05)
        job.start(archive, self.dest)
        self.assertEqual(_wait(job)["state"], "error")

    def test_not_enough_space(self):
        archive = self._zip({"Client/Wow.exe": b"exe"})
        job = ci.ExtractJob(extractor_factory=lambda: FakeExtractor(10 ** 16, {"Client"}), poll_interval=0.05)
        job.start(archive, self.dest)
        st = _wait(job)
        self.assertEqual(st["state"], "error")
        self.assertIn("Недостаточно места", st["error"])

    def test_no_extractor(self):
        archive = self._zip({"Client/Wow.exe": b"exe"})
        job = ci.ExtractJob(extractor_factory=lambda: None, poll_interval=0.05)
        job.start(archive, self.dest)
        st = _wait(job)
        self.assertEqual(st["state"], "error")
        self.assertIn("распаковщик", st["error"])

    def test_start_validates_inputs(self):
        job = ci.ExtractJob()
        self.assertEqual(job.start(os.path.join(self.tmp, "nope.rar"), self.dest), (False, "Архив не найден"))
        archive = self._zip({"a.txt": b"1"})
        self.assertEqual(job.start(archive, os.path.join(self.tmp, "nodir")), (False, "Папка назначения не найдена"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
```

- [ ] **Step 2:** тесты падают: `ModuleNotFoundError: client_install`.

- [ ] **Step 3: реализация** (`client_install.py`)

```python
"""Установка клиента: распаковка архива с клиентом (RAR5) в выбранную папку.

Распаковщик: вшитый 7-Zip (7z.exe + 7z.dll в _MEIPASS или рядом с лаунчером), иначе
системный tar.exe (libarchive; Windows 11 читает RAR5). Распаковка идёт во
временную папку внутри назначения и переносится на место только целиком —
прерванная распаковка не оставляет полуклиента."""

import os
import shutil
import subprocess
import sys
import threading
import time

from gameutils import NO_WINDOW

GAME_EXES = ("wow.exe",)
FREE_SPACE_MARGIN = 1 << 30  # 1 ГБ сверх размера клиента
STAGING_DIR = ".plgames_extract"
LOG_FILE = ".plgames_extract.log"


class ExtractError(Exception):
    pass


class ExtractCancelled(ExtractError):
    pass


def _parse_7z_slt(text):
    """`7z l -slt`: (сумма размеров файлов, имена верхнего уровня)."""
    total, roots = 0, set()
    text = text.replace("\r\n", "\n")
    if "\n----------\n" in text:
        text = text.split("\n----------\n", 1)[1]
    for block in text.split("\n\n"):
        fields = {}
        for line in block.split("\n"):
            key, sep, value = line.partition(" = ")
            if sep:
                fields[key.strip()] = value.strip()
        path = fields.get("Path")
        if not path:
            continue
        roots.add(path.replace("\\", "/").split("/", 1)[0])
        size = fields.get("Size", "")
        if fields.get("Folder") != "+" and size.isdigit():
            total += int(size)
    return total, roots


def _parse_tar_sizes(text):
    """`tar -tvf`: сумма размеров обычных файлов (5-е поле; дата локализована, её не трогаем)."""
    total = 0
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].startswith("-") and parts[4].isdigit():
            total += int(parts[4])
    return total


def _roots_from_names(text):
    roots = set()
    for line in text.splitlines():
        name = line.strip().replace("\\", "/")
        while name.startswith("./"):
            name = name[2:]
        name = name.lstrip("/")
        if name:
            roots.add(name.split("/", 1)[0])
    return roots


def _run(cmd, timeout=900):
    r = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=NO_WINDOW)
    return r.returncode, r.stdout.decode("utf-8", errors="replace")


class SevenZip:
    name = "7-Zip"
    ok_codes = (0, 1)  # 1 = предупреждения, файлы распакованы

    def __init__(self, exe):
        self.exe = exe

    def inspect(self, archive):
        rc, out = _run([self.exe, "l", "-slt", "-sccUTF-8", archive])
        if rc != 0:
            raise ExtractError("Архив повреждён или не поддерживается")
        return _parse_7z_slt(out)

    def extract_cmd(self, archive, dest):
        return [self.exe, "x", "-y", "-bd", f"-o{dest}", archive]


class SystemTar:
    name = "tar"
    ok_codes = (0,)

    def __init__(self, exe):
        self.exe = exe

    def inspect(self, archive):
        rc, verbose = _run([self.exe, "-tvf", archive])
        rc2, names = _run([self.exe, "-tf", archive]) if rc == 0 else (rc, "")
        if rc != 0 or rc2 != 0:
            raise ExtractError("Не удалось прочитать архив. Установите 7-Zip или распакуйте архив "
                               "вручную и укажите папку с игрой.")
        return _parse_tar_sizes(verbose), _roots_from_names(names)

    def extract_cmd(self, archive, dest):
        return [self.exe, "-xf", archive, "-C", dest]


def _bundle_dirs():
    dirs = []
    if getattr(sys, "_MEIPASS", None):
        dirs.append(sys._MEIPASS)
    if getattr(sys, "frozen", False):
        dirs.append(os.path.dirname(sys.executable))
    else:
        dirs.append(os.path.dirname(os.path.abspath(__file__)))
    return dirs


def find_extractor():
    for d in _bundle_dirs():
        exe = os.path.join(d, "7z.exe")
        if os.path.isfile(exe) and os.path.isfile(os.path.join(d, "7z.dll")):
            return SevenZip(exe)
    tar = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "tar.exe")
    if os.path.isfile(tar):
        return SystemTar(tar)
    return None


def find_game_dir(root, max_depth=2):
    """Папка с wow.exe: root и вложенные папки до max_depth уровней (поиск в ширину)."""
    level = [root]
    for _ in range(max_depth + 1):
        nxt = []
        for d in level:
            try:
                entries = sorted(os.listdir(d))
            except OSError:
                continue
            if any(e.lower() in GAME_EXES for e in entries):
                return d
            nxt.extend(os.path.join(d, e) for e in entries if os.path.isdir(os.path.join(d, e)))
        level = nxt
    return None


def dir_size(path):
    total = 0
    for dirpath, _, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass
    return total


def _tail(path, limit=300):
    try:
        with open(path, "rb") as f:
            data = f.read()
        return data[-limit:].decode("utf-8", errors="replace").strip()
    except OSError:
        return ""


class ExtractJob:
    """Фоновая распаковка с прогрессом (байты на диске / размер из листинга)."""

    def __init__(self, extractor_factory=find_extractor, poll_interval=1.0):
        self._factory = extractor_factory
        self._poll = poll_interval
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread = None
        self._status = {"state": "idle"}

    def status(self):
        with self._lock:
            return dict(self._status)

    def _set(self, **kw):
        with self._lock:
            self._status.update(kw)

    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, archive, dest, on_done=None):
        if self.running():
            return False, "Распаковка уже идёт"
        if not os.path.isfile(archive):
            return False, "Архив не найден"
        if not os.path.isdir(dest):
            return False, "Папка назначения не найдена"
        self._cancel.clear()
        with self._lock:
            self._status = {"state": "preparing", "progress": 0, "done_mb": 0, "total_mb": 0,
                            "archive": archive, "dest": dest}
        self._thread = threading.Thread(target=self._run, args=(archive, dest, on_done), daemon=True)
        self._thread.start()
        return True, ""

    def cancel(self):
        self._cancel.set()

    def _run(self, archive, dest, on_done):
        staging = os.path.join(dest, STAGING_DIR)
        try:
            game_dir = self._extract(archive, dest, staging)
            if on_done:
                on_done(game_dir)
            self._set(state="finished", progress=100, game_dir=game_dir)
        except ExtractCancelled as e:
            self._set(state="cancelled", error=str(e))
        except ExtractError as e:
            self._set(state="error", error=str(e))
        except Exception as e:  # диск, права, subprocess
            self._set(state="error", error=f"Ошибка распаковки: {e}")
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _extract(self, archive, dest, staging):
        ext = self._factory()
        if ext is None:
            raise ExtractError("Не найден распаковщик. Установите 7-Zip или распакуйте архив вручную "
                               "и укажите папку с игрой.")
        total, roots = ext.inspect(archive)
        if total <= 0 or not roots:
            raise ExtractError("Архив пуст или не читается")
        taken = sorted(r for r in roots if os.path.lexists(os.path.join(dest, r)))
        if taken:
            raise ExtractError(f"В папке уже есть «{taken[0]}». Выберите другую папку или удалите её.")
        free = shutil.disk_usage(dest).free
        if free < total + FREE_SPACE_MARGIN:
            raise ExtractError(f"Недостаточно места: нужно {(total + FREE_SPACE_MARGIN) / 2**30:.1f} ГБ, "
                               f"свободно {free / 2**30:.1f} ГБ")
        self._set(state="extracting", total_mb=round(total / 2**20))
        shutil.rmtree(staging, ignore_errors=True)
        os.makedirs(staging)
        log_path = os.path.join(dest, LOG_FILE)
        with open(log_path, "wb") as log:
            proc = subprocess.Popen(ext.extract_cmd(archive, staging), stdout=log, stderr=log,
                                    stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
            while proc.poll() is None:
                if self._cancel.is_set():
                    proc.kill()
                    proc.wait()
                    raise ExtractCancelled("Распаковка отменена")
                done = dir_size(staging)
                self._set(done_mb=round(done / 2**20), progress=min(99, int(done * 100 / total)))
                time.sleep(self._poll)
        if proc.returncode not in ext.ok_codes:
            raise ExtractError(f"Распаковщик завершился с ошибкой (код {proc.returncode}): {_tail(log_path)}")
        for name in os.listdir(staging):
            os.replace(os.path.join(staging, name), os.path.join(dest, name))
        try:
            os.remove(log_path)
        except OSError:
            pass
        for root in sorted(roots):
            path = os.path.join(dest, root)
            if os.path.isfile(path) and root.lower() in GAME_EXES:
                return dest
            if os.path.isdir(path):
                found = find_game_dir(path)
                if found:
                    return found
        raise ExtractError("В архиве не найден wow.exe")
```

- [ ] **Step 4:** тесты проходят.
- [ ] **Step 5: Commit.** `feat: распаковка клиента (7-Zip / системный tar) с прогрессом`

---

### Task 3: `content.py` — манифест, состояние, планировщик, исполнитель

**Files:** Create `content.py`, `tests/test_content.py`

**Interfaces:**
- Consumes: `gameutils.safe_join`, `read_config_wtf`, `write_config_wtf`, `mpq_status`, `toggle_mpq`, `is_process_running`.
- Produces:
  - Исключения: `ManifestError`, `PlanError`, `ApplyError`.
  - Датаклассы: `Manifest`, `Component`, `Edition`, `TableRow`, `FileEntry`, `MpqFile`, `Action(kind, component)`.
  - `parse_manifest(dict) -> Manifest`
  - `load_manifest(urls, cache_path, builtin_path=None, session=None, timeout=5) -> (Manifest, source)`
  - `table_checks(m) -> [{"label", "checks": {edition_id: bool}}]`
  - `empty_state()`, `load_state(gd)`, `save_state(gd, state)`
  - `component_status(m, gd, state) -> {id: {available, active, partial, outdated}}`
  - `detect_edition(m, status) -> edition_id | "custom"`
  - `plan(m, status, state, target_ids) -> [Action]`
  - `Executor(m, gd, state, session=None, progress=None, is_running=None).run(actions, edition=None) -> state`
  - `progress` вызывается как `progress(stage="download"|"apply", done=int, total=int, text=str)`.

- [ ] **Step 1: тесты** (`tests/test_content.py`)

```python
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import content
import gameutils

DLL = b"MZ fake dxvk d3d9"
CONF = b"d3d9.samplerAnisotropy = 16\n"
BASE = "https://cdn.test"
MIRROR = "https://mirror.test"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def manifest_dict(dll_urls=None):
    return {
        "schema": 1, "content_version": "t1",
        "components": [
            {"id": "hd_textures", "name": "HD-текстуры", "group": "Графика", "type": "mpq",
             "files": [{"name": "patch-ruRU-4.MPQ", "folder": "Data/ruRU"},
                       {"name": "patch-ruRU-5.MPQ", "folder": "Data/ruRU"}]},
            {"id": "hd_water", "name": "Вода", "group": "Эффекты", "type": "mpq",
             "files": [{"name": "Patch-ruRU-V.mpq", "folder": "Data/ruRU"}]},
            {"id": "missing_pack", "name": "Нет в клиенте", "group": "Графика", "type": "mpq",
             "files": [{"name": "patch-Z.MPQ", "folder": "Data"}]},
            {"id": "dxvk", "name": "DXVK", "group": "Производительность", "type": "files", "version": "2.4",
             "files": [{"path": "d3d9.dll", "size": len(DLL), "sha256": sha(DLL),
                        "urls": dll_urls or [BASE + "/dxvk/d3d9.dll"]},
                       {"path": "dxvk.conf", "size": len(CONF), "sha256": sha(CONF),
                        "urls": [BASE + "/dxvk/dxvk.conf"]}]},
            {"id": "gfx_ultra", "name": "Ультра-настройки", "group": "Настройки", "type": "config",
             "values": {"farclip": "1277", "spellEffectLevel": "6"}},
        ],
        "editions": [
            {"id": "classic", "name": "Классика", "components": []},
            {"id": "remaster", "name": "Ремастер", "components": ["hd_textures", "hd_water", "missing_pack", "dxvk"]},
            {"id": "ultra", "name": "Ультра",
             "components": ["hd_textures", "hd_water", "missing_pack", "dxvk", "gfx_ultra"]},
        ],
        "table": [
            {"label": "Оригинал", "editions": ["classic"]},
            {"label": "HD", "components": ["hd_textures", "hd_water"]},
            {"label": "Макс", "components": ["gfx_ultra"]},
        ],
    }


class FakeResponse:
    def __init__(self, status=200, body=b"", json_data=None):
        self.status_code, self.body, self._json = status, body, json_data

    def iter_content(self, chunk):
        for i in range(0, len(self.body), chunk):
            yield self.body[i:i + chunk]

    def json(self):
        if self._json is None:
            raise ValueError("not json")
        return self._json

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, **kw):
        self.calls.append(url)
        if url not in self.routes:
            raise ConnectionError("unreachable " + url)
        return self.routes[url]


def good_routes():
    return {BASE + "/dxvk/d3d9.dll": FakeResponse(body=DLL), BASE + "/dxvk/dxvk.conf": FakeResponse(body=CONF)}


def make_client(root):
    gd = os.path.join(root, "Game")
    os.makedirs(os.path.join(gd, "Data", "ruRU"))
    os.makedirs(os.path.join(gd, "WTF"))
    open(os.path.join(gd, "Wow.exe"), "wb").close()
    for name in ("patch-ruRU-4.MPQ", "patch-ruRU-5.MPQ", "Patch-ruRU-V.mpq"):
        with open(os.path.join(gd, "Data", "ruRU", name), "wb") as f:
            f.write(b"mpq")
    with open(os.path.join(gd, "WTF", "Config.wtf"), "w") as f:
        f.write('SET farclip "777"\n')
    return gd


NOT_RUNNING = lambda name: False  # noqa: E731


class ParseManifestTests(unittest.TestCase):
    def test_valid_manifest(self):
        m = content.parse_manifest(manifest_dict())
        self.assertEqual([c.id for c in m.components][:2], ["hd_textures", "hd_water"])
        self.assertEqual(m.component("gfx_ultra").values_dict(), {"farclip": "1277", "spellEffectLevel": "6"})
        rows = content.table_checks(m)
        self.assertEqual(rows[0]["checks"], {"classic": True, "remaster": False, "ultra": False})
        self.assertEqual(rows[1]["checks"], {"classic": False, "remaster": True, "ultra": True})
        self.assertEqual(rows[2]["checks"], {"classic": False, "remaster": False, "ultra": True})

    def _bad(self, mutate, msg):
        d = manifest_dict()
        mutate(d)
        with self.assertRaises(content.ManifestError, msg=msg):
            content.parse_manifest(d)

    def test_rejects_unsafe_paths_and_types(self):
        for bad in ("../evil.dll", "C:/x.dll", "sub/../../x.dll", "run.exe", "Wow.exe", "/abs.dll"):
            self._bad(lambda d, b=bad: d["components"][3]["files"][0].__setitem__("path", b), bad)

    def test_rejects_http_bad_sha_unknown_members_and_schema(self):
        self._bad(lambda d: d["components"][3]["files"][0].__setitem__("urls", ["http://x/d3d9.dll"]), "http")
        self._bad(lambda d: d["components"][3]["files"][0].__setitem__("sha256", "abc"), "sha")
        self._bad(lambda d: d["editions"][1]["components"].append("nope"), "unknown")
        self._bad(lambda d: d.__setitem__("schema", 2), "schema")
        self._bad(lambda d: d["components"][0]["files"][0].__setitem__("folder", "../.."), "folder")

    def test_shared_file_requires_conflict(self):
        d = manifest_dict()
        reshade = {"id": "reshade", "name": "ReShade", "type": "files", "version": "6",
                   "files": [{"path": "d3d9.dll", "size": 1, "sha256": sha(b"r"), "urls": [BASE + "/r.dll"]}]}
        d["components"].append(dict(reshade))
        with self.assertRaises(content.ManifestError):
            content.parse_manifest(d)
        d["components"][-1]["conflicts"] = ["dxvk"]
        content.parse_manifest(d)


class LoadManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache = os.path.join(self.tmp, "cache", "manifest.json")
        self.builtin = os.path.join(self.tmp, "builtin.json")
        with open(self.builtin, "w", encoding="utf-8") as f:
            json.dump(manifest_dict(), f)

    def test_network_success_writes_cache(self):
        s = FakeSession({"https://a/m.json": FakeResponse(json_data=manifest_dict())})
        m, src = content.load_manifest(["https://a/m.json"], self.cache, self.builtin, session=s)
        self.assertEqual(src, "https://a/m.json")
        self.assertTrue(os.path.isfile(self.cache))

    def test_falls_back_mirror_then_cache_then_builtin(self):
        bad = FakeResponse(json_data={"schema": 99})
        s = FakeSession({"https://a/m.json": FakeResponse(status=404),
                         "https://b/m.json": FakeResponse(json_data=manifest_dict())})
        self.assertEqual(content.load_manifest(["https://a/m.json", "https://b/m.json"], self.cache,
                                               self.builtin, session=s)[1], "https://b/m.json")
        offline = FakeSession({"https://a/m.json": bad})
        self.assertEqual(content.load_manifest(["https://a/m.json"], self.cache, self.builtin,
                                               session=offline)[1], "cache")
        os.remove(self.cache)
        self.assertEqual(content.load_manifest(["https://a/m.json"], self.cache, self.builtin,
                                               session=offline)[1], "builtin")

    def test_everything_fails(self):
        with self.assertRaises(content.ManifestError):
            content.load_manifest(["https://a/m.json"], self.cache, None, session=FakeSession({}))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class StatusAndPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.gd = make_client(self.tmp)
        self.m = content.parse_manifest(manifest_dict())

    def status(self, state=None):
        return content.component_status(self.m, self.gd, state or content.load_state(self.gd))

    def test_fresh_client_is_custom_and_missing_pack_unavailable(self):
        st = self.status()
        self.assertTrue(st["hd_textures"]["active"])
        self.assertFalse(st["missing_pack"]["available"])
        self.assertEqual(content.detect_edition(self.m, st), "custom")

    def test_all_disabled_is_classic(self):
        for name in ("patch-ruRU-4.MPQ", "patch-ruRU-5.MPQ", "Patch-ruRU-V.mpq"):
            gameutils.toggle_mpq(self.gd, name, "Data/ruRU", False)
        self.assertEqual(content.detect_edition(self.m, self.status()), "classic")

    def test_partially_enabled_component_is_custom(self):
        for name in ("patch-ruRU-4.MPQ", "Patch-ruRU-V.mpq"):
            gameutils.toggle_mpq(self.gd, name, "Data/ruRU", False)
        st = self.status()
        self.assertTrue(st["hd_textures"]["partial"])
        self.assertFalse(st["hd_textures"]["active"])
        self.assertEqual(content.detect_edition(self.m, st), "custom")

    def test_plan_classic_and_ultra_from_fresh(self):
        st, state = self.status(), content.load_state(self.gd)
        classic = content.plan(self.m, st, state, set())
        self.assertEqual([(a.kind, a.component) for a in classic],
                         [("mpq_off", "hd_textures"), ("mpq_off", "hd_water")])
        ultra = content.plan(self.m, st, state, set(self.m.editions[2].components))
        self.assertEqual([(a.kind, a.component) for a in ultra],
                         [("files_install", "dxvk"), ("config_apply", "gfx_ultra")])

    def test_outdated_files_reinstalled(self):
        state = content.empty_state()
        state["components"]["dxvk"] = {"version": "2.3", "files": {"d3d9.dll": "x", "dxvk.conf": "y"}}
        acts = content.plan(self.m, self.status(state), state, {"dxvk"})
        self.assertEqual([(a.kind, a.component) for a in acts],
                         [("mpq_off", "hd_textures"), ("mpq_off", "hd_water"),
                          ("files_remove", "dxvk"), ("files_install", "dxvk")])

    def test_conflicts_and_unknown_rejected(self):
        d = manifest_dict()
        d["components"].append({"id": "reshade", "name": "ReShade", "type": "files", "version": "6",
                                "conflicts": ["dxvk"],
                                "files": [{"path": "d3d9.dll", "size": 1, "sha256": sha(b"r"),
                                           "urls": [BASE + "/r.dll"]}]})
        m = content.parse_manifest(d)
        st = content.component_status(m, self.gd, content.empty_state())
        with self.assertRaises(content.PlanError):
            content.plan(m, st, content.empty_state(), {"dxvk", "reshade"})
        with self.assertRaises(content.PlanError):
            content.plan(m, st, content.empty_state(), {"nope"})

    def test_state_roundtrip_and_corrupt_file(self):
        state = content.empty_state()
        state["edition"] = "ultra"
        content.save_state(self.gd, state)
        self.assertEqual(content.load_state(self.gd)["edition"], "ultra")
        with open(os.path.join(self.gd, "PLGames", "state.json"), "w") as f:
            f.write("{broken")
        self.assertIsNone(content.load_state(self.gd)["edition"])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.gd = make_client(self.tmp)
        self.m = content.parse_manifest(manifest_dict())

    def apply(self, edition_id, session=None, is_running=NOT_RUNNING):
        state = content.load_state(self.gd)
        st = content.component_status(self.m, self.gd, state)
        ed = next(e for e in self.m.editions if e.id == edition_id)
        acts = content.plan(self.m, st, state, set(ed.components))
        ex = content.Executor(self.m, self.gd, state, session=session or FakeSession(good_routes()),
                              is_running=is_running)
        return ex.run(acts, edition=edition_id)

    def p(self, *parts):
        return os.path.join(self.gd, *parts)

    def read(self, *parts):
        with open(self.p(*parts), "rb") as f:
            return f.read()

    def test_ultra_installs_verifies_and_records(self):
        state = self.apply("ultra")
        self.assertEqual(self.read("d3d9.dll"), DLL)
        self.assertEqual(self.read("dxvk.conf"), CONF)
        self.assertEqual(gameutils.read_config_wtf(self.gd)["farclip"], "1277")
        self.assertEqual(state["components"]["dxvk"]["version"], "2.4")
        self.assertEqual(content.load_state(self.gd)["edition"], "ultra")
        self.assertFalse(os.path.exists(self.p("PLGames", "tmp")))
        st = content.component_status(self.m, self.gd, content.load_state(self.gd))
        self.assertEqual(content.detect_edition(self.m, st), "ultra")

    def test_back_to_classic_restores_everything(self):
        self.apply("ultra")
        self.apply("classic")
        self.assertFalse(os.path.exists(self.p("d3d9.dll")))
        self.assertEqual(gameutils.read_config_wtf(self.gd)["farclip"], "777")
        self.assertNotIn("spellEffectLevel", gameutils.read_config_wtf(self.gd))
        self.assertTrue(os.path.isfile(self.p("Data", "ruRU", "patch-ruRU-4.MPQ.disabled")))
        self.assertEqual(content.load_state(self.gd)["components"], {})

    def test_foreign_file_backed_up_and_restored(self):
        with open(self.p("d3d9.dll"), "wb") as f:
            f.write(b"user reshade")
        self.apply("ultra")
        self.assertEqual(self.read("PLGames", "backup", "d3d9.dll"), b"user reshade")
        self.apply("classic")
        self.assertEqual(self.read("d3d9.dll"), b"user reshade")
        self.assertFalse(os.path.exists(self.p("PLGames", "backup", "d3d9.dll")))

    def test_bad_checksum_falls_back_to_mirror(self):
        m = content.parse_manifest(manifest_dict(dll_urls=[BASE + "/bad.dll", MIRROR + "/d3d9.dll"]))
        self.m = m
        routes = good_routes()
        routes[BASE + "/bad.dll"] = FakeResponse(body=b"tampered!!")
        routes[MIRROR + "/d3d9.dll"] = FakeResponse(body=DLL)
        s = FakeSession(routes)
        self.apply("ultra", session=s)
        self.assertEqual(self.read("d3d9.dll"), DLL)
        self.assertIn(BASE + "/bad.dll", s.calls)

    def test_download_failure_leaves_client_untouched(self):
        routes = good_routes()
        routes[BASE + "/dxvk/d3d9.dll"] = FakeResponse(body=b"tampered!!")
        with self.assertRaises(content.ApplyError):
            self.apply("ultra", session=FakeSession(routes))
        self.assertFalse(os.path.exists(self.p("d3d9.dll")))
        self.assertEqual(gameutils.read_config_wtf(self.gd)["farclip"], "777")
        self.assertFalse(os.path.exists(self.p("PLGames", "state.json")))

    def test_failure_mid_apply_rolls_back(self):
        real = gameutils.toggle_mpq

        def flaky(gp, name, folder, enable):
            return False if name == "Patch-ruRU-V.mpq" else real(gp, name, folder, enable)

        with mock.patch.object(gameutils, "toggle_mpq", side_effect=flaky):
            with self.assertRaises(content.ApplyError):
                self.apply("classic")
        self.assertTrue(os.path.isfile(self.p("Data", "ruRU", "patch-ruRU-4.MPQ")))
        self.assertFalse(os.path.exists(self.p("Data", "ruRU", "patch-ruRU-4.MPQ.disabled")))
        self.assertFalse(os.path.exists(self.p("PLGames", "state.json")))

    def test_refuses_while_game_running(self):
        with self.assertRaises(content.ApplyError) as cm:
            self.apply("classic", is_running=lambda name: True)
        self.assertIn("Закройте игру", str(cm.exception))

    def test_no_actions_only_records_edition(self):
        for name in ("patch-ruRU-4.MPQ", "patch-ruRU-5.MPQ", "Patch-ruRU-V.mpq"):
            gameutils.toggle_mpq(self.gd, name, "Data/ruRU", False)
        self.apply("classic", is_running=lambda name: True)  # игра запущена — но менять нечего
        self.assertEqual(content.load_state(self.gd)["edition"], "classic")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
```

- [ ] **Step 2:** тесты падают: `ModuleNotFoundError: content`.

- [ ] **Step 3: реализация** (`content.py`). Полный модуль приведён в файле `content.py`, созданном на этом шаге. Ключевые решения:
  - датаклассы `frozen=True`;
  - `parse_manifest` проверяет всё из Global Constraints и дополнительно требует, чтобы два files-компонента с общим путём были объявлены конфликтующими;
  - `plan` выдаёт сначала удаления, потом установки, а устаревший компонент получает пару «удалить + установить»;
  - `Executor.run` сначала скачивает всё в `PLGames/tmp` с проверкой размера и SHA-256 и перебором зеркал, затем применяет изменения по журналу отмены;
  - чужой файл на месте нашего переносится в `PLGames/backup/<path>` и возвращается при удалении компонента;
  - для config-компонента запоминаются `previous`/`applied`, при выключении возвращается `previous`, а `None` удаляет ключ;
  - `state.json` пишется атомарно в конце, внутри защищённого блока.

- [ ] **Step 4:** тесты проходят.
- [ ] **Step 5: Commit.** `feat: content — манифест изданий, планировщик и исполнитель с откатом`

---

### Task 4: `hardware.py` и `editions.py` — рекомендация и фасад для UI

**Files:** Create `hardware.py`, `editions.py`, `tests/test_editions.py`

**Interfaces:**
- `hardware.detect_gpus() -> [{"name", "vram_mb"}]`
- `hardware.recommend_edition(gpus) -> "classic" | "remaster" | "ultra"`
- `EditionService(urls, cache_path, builtin_path, session_factory=None, gpu_detector=hardware.detect_gpus, is_running=None)`, методы:
  - `.preload()`
  - `.manifest(refresh=False)`
  - `.recommended()`
  - `.view(game_dir) -> dict` с полями `ok, installed, source, content_version, active, chosen, recommended, editions[], table[], components[], job`
  - `.start_apply(game_dir, edition_id=None, component_ids=None) -> (bool, str)`
  - `.status() -> {"state": idle|running|finished|error, "progress", "text", "error"}`
  - `.busy()`

- [ ] **Step 1: тесты** (`tests/test_editions.py`)

```python
import json
import os
import shutil
import tempfile
import time
import unittest

import editions
import hardware
from tests.test_content import FakeSession, good_routes, make_client, manifest_dict


class RecommendTests(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(hardware.recommend_edition([]), "remaster")
        self.assertEqual(hardware.recommend_edition([{"name": "Intel(R) UHD Graphics 620", "vram_mb": 1024}]), "classic")
        self.assertEqual(hardware.recommend_edition([{"name": "Intel(R) UHD Graphics", "vram_mb": 1024},
                                                     {"name": "NVIDIA GeForce RTX 3060", "vram_mb": 4095}]), "ultra")
        self.assertEqual(hardware.recommend_edition([{"name": "NVIDIA GeForce GTX 1050", "vram_mb": 2048}]), "remaster")


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.gd = make_client(self.tmp)
        builtin = os.path.join(self.tmp, "builtin.json")
        with open(builtin, "w", encoding="utf-8") as f:
            json.dump(manifest_dict(), f)
        self.svc = editions.EditionService(
            ["https://offline/m.json"], os.path.join(self.tmp, "cache.json"), builtin,
            session_factory=lambda: FakeSession(good_routes()),
            gpu_detector=lambda: [{"name": "NVIDIA GeForce RTX 3060", "vram_mb": 4095}],
            is_running=lambda name: False)

    def wait(self):
        end = time.time() + 10
        while self.svc.busy() and time.time() < end:
            time.sleep(0.02)
        return self.svc.status()

    def test_view_of_fresh_client(self):
        v = self.svc.view(self.gd)
        self.assertTrue(v["ok"] and v["installed"])
        self.assertEqual(v["source"], "builtin")
        self.assertEqual(v["active"], "custom")
        self.assertIsNone(v["chosen"])
        self.assertEqual(v["recommended"], "ultra")
        self.assertEqual([e["id"] for e in v["editions"]], ["classic", "remaster", "ultra"])

    def test_view_without_game(self):
        v = self.svc.view("")
        self.assertFalse(v["installed"])
        self.assertIsNone(v["active"])

    def test_apply_edition_then_custom(self):
        self.assertEqual(self.svc.start_apply(self.gd, edition_id="ultra"), (True, ""))
        self.assertEqual(self.wait()["state"], "finished")
        v = self.svc.view(self.gd)
        self.assertEqual((v["active"], v["chosen"]), ("ultra", "ultra"))
        self.assertEqual(self.svc.start_apply(self.gd, component_ids=["hd_water"]), (True, ""))
        self.assertEqual(self.wait()["state"], "finished")
        v = self.svc.view(self.gd)
        self.assertEqual((v["active"], v["chosen"]), ("custom", "custom"))

    def test_rejects_unknown_edition_and_missing_game(self):
        self.assertEqual(self.svc.start_apply(self.gd, edition_id="nope"), (False, "Неизвестное издание"))
        self.assertFalse(self.svc.start_apply("", edition_id="ultra")[0])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
```

- [ ] **Step 2:** тесты падают.
- [ ] **Step 3: реализация.**
  - `hardware.py`: видеокарта берётся через PowerShell `Get-CimInstance Win32_VideoController | ConvertTo-Json`. Встроенной считается карта, в имени которой есть Intel HD/UHD/Iris/Graphics, Microsoft Basic, Radeon(TM) Graphics или Vega. Правила рекомендации: нет данных → `remaster`; только встроенные → `classic`; дискретная с 3900 МБ видеопамяти и больше → `ultra`; иначе → `remaster`.
  - `editions.py`: фасад по интерфейсу выше.
    - Манифест кэшируется в памяти под замком.
    - Применение идёт в фоновом потоке.
    - Прогресс: при наличии загрузок 0–80 % приходится на загрузку и 80–100 % на применение, без загрузок применение занимает 0–100 %.
    - Метка в `state.json`: при выборе по компонентам пишется `custom`, при выборе издания — его id.
- [ ] **Step 4:** тесты проходят.
- [ ] **Step 5: Commit.** `feat: editions — фасад изданий и рекомендация под видеокарту`

---

### Task 5: встроенный манифест `content_default.json`

**Files:** Create `content_default.json`, `tests/test_default_manifest.py`

Встроенный манифест переводит 19 захардкоженных `hd_patches` в компоненты:
- **MPQ-компоненты:** `hd_textures`, `hd_characters`, `hd_creatures`, `hd_armor`, `hd_weapons`, `hd_spells`, `hd_water`, `dungeon_maps`.
- **Настройки:** `gfx_high` (farclip 777, groundEffectDensity 128, spellEffectLevel 4) и `gfx_ultra` (1277 / 256 / 6, конфликтует с `gfx_high`).
- **Издания:**
  - `classic` = только `dungeon_maps`;
  - `remaster` = все HD + `dungeon_maps` + `gfx_high`;
  - `ultra` = все HD + `dungeon_maps` + `gfx_ultra`.
- **Таблица сравнения:** 6 строк, у строки «Оригинальная графика» галочка задана явно: `editions: ["classic"]`.

- [ ] **Step 1: тест**

```python
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
```

- [ ] **Step 2–4:** тест падает, создаётся JSON, тест проходит.
- [ ] **Step 5: Commit.** `feat: встроенный манифест изданий из текущих HD-патчей`

---

### Task 6: интеграция в `app.py` — API

**Files:** Modify `app.py`

- [ ] **Step 1: конфиг.**
  - В `PROJECTS` у `wow_chronos` удалить `hd_patches`, добавить `"client_archive": "PLGames_Wow3.3.5.rar"` и `"editions": True`.
  - У `windrose` удалить `hd_patches`.
  - Добавить константу:
    ```python
    CONTENT_MANIFEST_URLS = [
        f"{API_BASE}/launcher/content/manifest.json",
        f"https://github.com/{GITHUB_REPO}/releases/download/content-latest/manifest.json",
    ]
    ```
- [ ] **Step 2: `fetch_manifest`.** Удалить строку с `hd_patches`. Добавить поля, где побеждает локальное значение: `torrent_url`, `torrent_folder`, `client_archive`, `editions`. Сейчас `torrent_url` теряется, как только сервер начнёт отдавать манифест.
- [ ] **Step 3: хелперы.**
  - `_bundled(name)`: путь внутри `_MEIPASS` или рядом со скриптом.
  - `_appdata_dir()`: `%APPDATA%\PLGamesLauncher`.
  - Совместимость диалогов:
    ```python
    _FOLDER_DIALOG = webview.FileDialog.FOLDER if hasattr(webview, "FileDialog") else webview.FOLDER_DIALOG
    _OPEN_DIALOG = webview.FileDialog.OPEN if hasattr(webview, "FileDialog") else webview.OPEN_DIALOG
    ```
- [ ] **Step 4: `Api.__init__`.**
  - `self._window = None`.
  - `self._extract = client_install.ExtractJob()`.
  - `self._editions = EditionService(CONTENT_MANIFEST_URLS, os.path.join(_appdata_dir(), "content-manifest.json"), _bundled("content_default.json"))`, затем `self._editions.preload()`.
  - Все `self.window` заменить на `self._window`. В `main()` писать `api._window = window`: pywebview не обходит атрибуты с `_`, и шум в логе уходит.
- [ ] **Step 5: методы.**
  - Удалить `get_hd_patches` и `toggle_hd_patch`.
  - `get_projects` добавляет `"has_editions": bool(p.get("editions"))`.
  - `start_download` при успехе запоминает `settings["client_archives"][pid] = os.path.join(save_path, proj["client_archive"])`.
  - Новые методы, все возвращают JSON:
    - `start_extract(pid, archive="")`: архив берётся из `settings.client_archives` или из пути к игре; распаковка в папку архива; `on_done` пишет `game_paths[pid]`.
    - `get_extract_status(pid)`: статус плюс `archive_gb`.
    - `cancel_extract()`.
    - `browse_archive(pid)`: диалог `_OPEN_DIALOG` с фильтром `("Архив клиента (*.rar;*.zip;*.7z)",)`, затем `start_extract`.
    - `delete_client_archive(pid)`: отказ, если идёт раздача.
    - `get_editions(pid)`: для проекта без `editions` возвращает `{"ok": False}`.
    - `apply_edition(pid, edition_id)`.
    - `set_components(pid, ids_json)`.
    - `get_edition_status()`.
  - `launch_game` отказывает, пока `self._editions.busy()`: «Дождитесь применения издания».
  - `browse_game_path` использует `_FOLDER_DIALOG`.
- [ ] **Step 6:** `python -c "import ast; ast.parse(open('app.py', encoding='utf-8').read())"`, затем прогон всех тестов.
- [ ] **Step 7: Commit.** `feat: API установки клиента и изданий в лаунчере`

### Task 7: интеграция в `app.py` — интерфейс

**Files:** Modify `app.py` (HTML, CSS, JS)

- [ ] **Step 1: вкладка и страница.**
  - Вкладка `<button class="topbar-nav-btn" data-page="editions" id="nav-editions">ИЗДАНИЯ</button>` сразу после «ИГРАТЬ».
  - Страница `<div class="page-view" id="view-editions"><div class="ed-page" id="editions-content"></div></div>` после `view-news`.
  - `showPage` переключает `view-editions` и при открытии вызывает `loadEditions()`.
  - `selectProject` прячет вкладку, если `!activeProject.has_editions`.
- [ ] **Step 2: CSS** страницы изданий в токенах темы:
  - `.ed-head` (надзаголовок, заголовок, подзаголовок);
  - `.ed-grid` / `.ed-row`: сетка из колонки меток и N колонок изданий, число колонок через `--ed-cols`;
  - `.ed-card` с темами `ed-theme-classic` (бронза), `ed-theme-remaster` (сталь и синий), `ed-theme-ultra` (золото и фиолетовый);
  - `.ed-card-art`: градиент плюс римская цифра шрифтом Cinzel;
  - `.ed-badge` «Рекомендуем для вашего ПК»;
  - `.ed-btn` / `.current`;
  - `.ed-check` / `.ed-dash`;
  - `.ed-progress`;
  - `.edition-cta` на экране «Играть».
- [ ] **Step 3: JS.**
  - `loadEditions()`, `renderEditions()`, `chooseEdition(id)`, `pollEditionStatus()` (400 мс).
  - `toggleComponent(id, on)` для «Своё» в `loadSettings`: вместо блока HD-патчей выводятся компоненты по группам.
  - Удалить `togglePatch`.
  - Везде `esc()` / `safeUrl()`.
- [ ] **Step 4: установка клиента в JS.**
  - Когда в `pollDownloadStatus` приходит `finished`/`seeding`, вызывается `startExtract()`.
  - `pollExtractStatus()` (1 с) использует `download-bar` с текстом «Распаковка»; пауза скрыта, отмена вызывает `cancel_extract`.
  - По окончании: `loadGameView()`, `confirm` на удаление архива, переход на вкладку «ИЗДАНИЯ».
  - При состоянии «не установлена» под кнопкой установки показывается ссылка «Уже есть архив клиента?» → `startExtract('browse')`.
- [ ] **Step 5: призыв на экране «Играть».** В `hero-right` добавляется блок `#edition-cta`. `loadGameView` показывает его для WoW, если игра установлена и `view.chosen === null`. Кнопка «Настройки HD» переименовывается в «Графические издания» и ведёт на `showPage('editions')`.
- [ ] **Step 6: ручная проверка.**
  - Запустить `python app.py` на фейковом клиенте: `Wow.exe` плюс MPQ-заглушки, путь указать через настройки.
  - Открыть «ИЗДАНИЯ»: три карточки, таблица, бейдж рекомендации.
  - Выбрать «Классика»: MPQ получили `.disabled`, карточка «Активно».
  - Переключить компонент в настройках: активным становится «Своё».
  - Сделать скриншот окна и посмотреть его.
- [ ] **Step 7: Commit.** `feat: страница «Издания», режим «Своё» и распаковка клиента в UI`

### Task 8: сборка и публикация контента

**Files:** Modify `build.bat`, `.github/workflows/build-release.yml`, `.gitattributes`, `README.md`. Create `tools/build_content_manifest.py`, `content/manifest.src.json`, `tests/test_build_content_manifest.py`.

- [ ] **Step 1:** в `build.bat` и CI добавить `--add-data "content_default.json;."`. Если в папке есть `7z.exe` и `7z.dll`, добавить `--add-data "7z.exe;."` и `--add-data "7z.dll;."`. В `.gitattributes` прописать `*.dll binary`.
- [ ] **Step 2: тест сборщика манифеста.** Во временной папке есть `src.json` с files-компонентом `dxvk`, у файла `{"path": "d3d9.dll", "src": "files/d3d9.dll"}`. После `build()`:
  - у файла выставлены `size`, `sha256` и `urls` = [server, github];
  - файлы лежат в `out/server/dxvk/<ver>/d3d9.dll` и `out/github/dxvk-<ver>-d3d9.dll`;
  - `content.parse_manifest` принимает результат.
  - Отдельно: http-картинка в издании даёт `ManifestError`.
- [ ] **Step 3:** реализовать `tools/build_content_manifest.py` (argparse `--src` и `--out`, по умолчанию `content/manifest.src.json` и `dist-content`). `content/manifest.src.json` пока равен встроенному манифесту с `content_version: "2026.10.1"`. Слои DXVK и ReShade добавляются после проверки на реальном клиенте, см. Task 9.
- [ ] **Step 4:** в README коротко описать: как опубликовать контент (две папки → nginx `/launcher/content/` и GitHub Release `content-latest`), где лежит `state.json`, как откатиться.
- [ ] **Step 5: Commit.** `build: встроенный манифест в сборке, сборщик манифеста контента`

### Task 9 (ручной, нужен реальный клиент): слои «Ультра»

**Статус 2026-09-29.**

Сделано:
- DXVK 3.1.1 лежит в `content/files`, описан в `content/manifest.src.json`, только в «Своё».
- ReShade лежит в `content/files`, описан в `content/manifest.src.json`. Путь к нему:
  - первый вариант — обычная сборка с prod80. Владелец в игре оценил его как «выкручено, но слабо»;
  - заменён на **сборку с дополнениями** (`6.8.0-addon2`) с шейдерами Glamarye (затенение, FXAA, резкость, мягкий свет) и AdaptiveFog (туман). Лицензии обоих — MIT.
- Глубина в онлайне проверена на реальном клиенте:
  - Generic Depth выбирает буфер 2560x1440 INTZ;
  - нужен `DepthCopyBeforeClears=0`: WoW 3.3.5a не очищает этот буфер «по-обычному».
- Сборщик собирает пакет. `tools/try_content.py` применяет издание к клиенту без сервера, обновление компонента проверено на реальном клиенте.
- В «Ультра» добавлены настройки `environmentDetail`, `particleDensity`, `weatherDensity`, `baseMip`, `terrainMipLevel`, `skyCloudLOD`, `ffxGlow`. Ключи Config.wtf сравниваются без учёта регистра.
- Публикация — пререлиз GitHub `content-latest`. Сервер (nginx `/launcher/content/`) — отдельная серверная задача; пока его нет, лаунчер берёт контент с GitHub.

Не входит (нужно разрешение авторов): HD-небо Sectym (`Patch-ruRU-X`), Project Reforged.

Эксперимент «ReShade + DXVK» заменён запасным вариантом: компоненты объявлены конфликтующими.

Автоматически не делается, нужен клиент и живая видеокарта.
1. DXVK: взять 32-битный `d3d9.dll` из релиза doitsujin/dxvk и проверить старт WoW. DXVK 2.x требует Vulkan 1.3, поэтому на старых видеокартах нужен вариант 1.10.x.
2. Эксперимент ReShade + DXVK: ReShade как Vulkan-слой, зарегистрированный в HKCU без прав администратора. Если не получится, «Ультра» = ReShade (`d3d9.dll`) без DXVK, с `conflicts` в манифесте.
3. Собрать пресет, дописать компоненты в `content/manifest.src.json`, запустить сборщик и опубликовать.
4. Серверная задача (отдельная сессия): nginx `location /launcher/content/` на статическую папку.
