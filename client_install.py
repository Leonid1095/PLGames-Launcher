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

from gameutils import NO_WINDOW, kill_on_close

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
        self._start_lock = threading.Lock()
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
        # pywebview вызывает API из разных потоков: проверка «занято» и запуск — атомарно.
        with self._start_lock:
            return self._start_locked(archive, dest, on_done)

    def _start_locked(self, archive, dest, on_done):
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

    def join(self, timeout=None):
        """Дождаться завершения фонового потока (после cancel — он сам уберёт staging)."""
        if self._thread is not None:
            self._thread.join(timeout)

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
        shutil.rmtree(staging, ignore_errors=True)  # остатки прошлой прерванной распаковки
        if os.path.lexists(staging):
            raise ExtractError(f"Не удаётся очистить папку {staging} от прошлой распаковки: файлы заняты. "
                               "Перезагрузите компьютер или удалите её вручную.")
        os.makedirs(staging)
        log_path = os.path.join(dest, LOG_FILE)
        with open(log_path, "wb") as log:
            proc = subprocess.Popen(ext.extract_cmd(archive, staging), stdout=log, stderr=log,
                                    stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
            kill_on_close(proc)  # лаунчер закрыли/упал — распаковщик умирает вместе с ним
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
