"""Проверка и починка файлов клиента игры по индексу архива раздачи (client-index.json).

Индекс строится из RAR-архива клиента (tools/build_client_index.py): для каждого файла — размер,
CRC32 и где лежит его кусок в архиве. Проверка сверяет файлы клиента с индексом. Починка берёт кусок
битого файла из архива — с диска игрока или с нашего сервера по Range, — собирает из него мини-архив
(rar5.mini_archive), распаковывает обычным распаковщиком, сверяет CRC32 и ставит файл на место."""

import json
import os
import re
import shutil
import subprocess
import threading
import zlib

import gameutils
import rar5

INDEX_NAME = "client-index.json"
# Меняются сами: настройки и аддоны игрока, кэш и логи игры, портативный лаунчер (обновляет себя)
_EXEMPT_PREFIXES = ("wtf/", "interface/", "cache/", "screenshots/", "logs/", "errors/", "plgameslauncher_portable/")
_CRC_RE = re.compile(r"^[0-9a-f]{8}$")
_CHUNK = 1 << 20
DISABLED = ".disabled"  # так издания выключают MPQ (gameutils.mpq_status)


class ClientIndexError(ValueError):
    pass


class RepairError(RuntimeError):
    pass


class RepairCancelled(RepairError):
    pass


# ---------------------------------------------------------------------------
# Индекс
# ---------------------------------------------------------------------------

def index_from_rar(path):
    """Индекс архива клиента: пути относительно корневой папки архива (в ней лежит Wow.exe)."""
    raw = rar5.build_index(path)
    names = [f["name"] for f in raw["files"]]
    tops = {n.split("/", 1)[0] for n in names}
    root = tops.pop() if len(tops) == 1 and all("/" in n for n in names) else ""
    cut = len(root) + 1 if root else 0
    return {"schema": 1, "archive": os.path.basename(path), "archive_size": raw["archive_size"], "root": root,
            "main_header": raw["main_header"],
            "files": [dict(path=f["name"][cut:], size=f["size"], crc32=f["crc32"], offset=f["offset"],
                           length=f["length"]) for f in raw["files"]]}


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def parse_index(data):
    """Проверка индекса из сети: безопасные пути, числа, CRC. Ошибка — ClientIndexError."""
    try:
        files = data["files"]
        if data.get("schema") != 1 or not isinstance(files, list) or not files:
            raise ClientIndexError("неизвестная версия индекса клиента")
        archive = str(data["archive"])
        if os.path.basename(archive) != archive or not archive.lower().endswith(".rar"):
            raise ClientIndexError("недопустимое имя архива")
        main = bytes.fromhex(data["main_header"])
        if not _int(data["archive_size"]) or not main:
            raise ClientIndexError("неверный размер или заголовок архива")
        out = []
        for f in files:
            path = str(f["path"]).replace("\\", "/")
            parts = path.split("/")
            if (not path or ":" in path or path.startswith("/") or any(p in ("", ".", "..") for p in parts)
                    or not all(_int(f[k]) for k in ("size", "offset", "length"))
                    or not _CRC_RE.match(str(f["crc32"]))):
                raise ClientIndexError(f"недопустимая запись индекса «{path}»")
            out.append({"path": path, "size": f["size"], "crc32": f["crc32"], "offset": f["offset"],
                        "length": f["length"]})
    except (KeyError, TypeError, ValueError) as e:
        if isinstance(e, ClientIndexError):
            raise
        raise ClientIndexError(f"индекс клиента повреждён: {e}")
    return {"schema": 1, "archive": archive, "archive_size": data["archive_size"],
            "root": str(data.get("root", "")), "main_header": main.hex(), "files": out}


def load_index(urls, cache_path, session, timeout=10):
    """Индекс: сеть (urls по порядку) → кэш последнего валидного; None, если нигде нет."""
    for url in urls:
        try:
            r = session.get(url, timeout=timeout)
            if r.status_code != 200:
                continue
            data = r.json()
            index = parse_index(data)
        except Exception:
            continue
        try:
            os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
            with open(cache_path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(cache_path + ".tmp", cache_path)
        except OSError:
            pass
        return index
    try:
        with open(cache_path, encoding="utf-8") as f:
            return parse_index(json.load(f))
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Проверка
# ---------------------------------------------------------------------------

def is_exempt(path):
    """Файлы, которые меняют игра, лаунчер и игрок: их расхождение с раздачей — не поломка."""
    low = path.lower()
    return low.endswith("realmlist.wtf") or low.startswith(_EXEMPT_PREFIXES)


def _on_disk(game_dir, rel):
    """(путь, выключен ли изданием). Выключенный MPQ лежит как <имя>.disabled."""
    p = gameutils.safe_join(game_dir, rel)
    if p and not os.path.isfile(p) and os.path.isfile(p + DISABLED):
        return p + DISABLED, True
    return p, False


def crc32_file(path, cancel=None, on_bytes=None):
    value = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            if cancel is not None and cancel.is_set():
                raise RepairCancelled("Проверка отменена")
            value = zlib.crc32(chunk, value)
            if on_bytes:
                on_bytes(len(chunk))
    return f"{value & 0xFFFFFFFF:08x}"


def check(game_dir, index, full=False, progress=None, cancel=None, exempt=is_exempt):
    """Расхождения клиента с раздачей: [{"path", "problem": missing | size | crc}].
    Быстрая проверка — размеры всех файлов и CRC32 Wow.exe; полная — CRC32 всех."""
    files = [f for f in index["files"] if not exempt(f["path"])]
    total = sum(f["size"] for f in files) if full else 0
    done = [0]

    def on_bytes(n):
        done[0] += n
        if progress:
            progress(done[0], total)

    problems = []
    for f in files:
        path, _ = _on_disk(game_dir, f["path"])
        if not path or not os.path.isfile(path):
            problems.append({"path": f["path"], "problem": "missing"})
            on_bytes(f["size"] if full else 0)
            continue
        if os.path.getsize(path) != f["size"]:
            problems.append({"path": f["path"], "problem": "size"})
            on_bytes(f["size"] if full else 0)
            continue
        if full or f["path"].lower() == "wow.exe":
            if crc32_file(path, cancel, on_bytes if full else None) != f["crc32"]:
                problems.append({"path": f["path"], "problem": "crc"})
    return problems


# ---------------------------------------------------------------------------
# Источники кусков архива
# ---------------------------------------------------------------------------

class LocalArchive:
    """Архив клиента на диске игрока. Годится, только если это тот же архив (размер совпадает)."""
    label = "архив на диске"

    def __init__(self, path, index):
        self.path = path
        self.ok = bool(path) and os.path.isfile(path) and os.path.getsize(path) == index["archive_size"]

    def chunks(self, offset, length):
        if not self.ok:
            raise RepairError("архив на диске не совпадает с раздачей")
        with open(self.path, "rb") as f:
            f.seek(offset)
            left = length
            while left > 0:
                chunk = f.read(min(_CHUNK, left))
                if not chunk:
                    raise RepairError("архив на диске короче, чем нужно")
                left -= len(chunk)
                yield chunk


class HttpArchive:
    """Архив клиента на нашем сервере: нужный кусок по Range. Сервер, который отдаёт файл
    целиком (200 вместо 206), не годится — это 20 ГБ ради одного файла."""
    label = "сервер"

    def __init__(self, urls, session, timeout=30):
        self.urls, self.session, self.timeout = list(urls), session, timeout

    def chunks(self, offset, length):
        last = "нет адресов"
        for url in self.urls:
            try:
                with self.session.get(url, headers={"Range": f"bytes={offset}-{offset + length - 1}"},
                                      stream=True, timeout=self.timeout) as r:
                    if r.status_code != 206:
                        last = f"HTTP {r.status_code} без докачки"
                        continue
                    got = 0
                    for chunk in r.iter_content(_CHUNK):
                        if chunk:
                            got += len(chunk)
                            if got > length:
                                raise RepairError("сервер прислал больше, чем просили")
                            yield chunk
                    if got != length:
                        raise RepairError("сервер оборвал передачу")
                    return
            except RepairError:
                raise
            except Exception as e:  # сеть: пробуем следующий адрес
                last = str(e)
        raise RepairError(f"сервер: {last}")


# ---------------------------------------------------------------------------
# Починка
# ---------------------------------------------------------------------------

def _extract(extractor, archive, dest):
    if extractor is None:
        raise RepairError("Нет распаковщика (7-Zip или tar)")
    os.makedirs(dest, exist_ok=True)
    r = subprocess.run(extractor.extract_cmd(archive, dest), capture_output=True,
                       creationflags=gameutils.NO_WINDOW)
    if r.returncode not in extractor.ok_codes:
        raise RepairError(f"распаковщик вернул код {r.returncode}")


def _fetch_file(entry, index, source, work, extractor, cancel):
    """Кусок файла из источника → мини-архив → распакованный файл с проверенным CRC32."""
    mini = os.path.join(work, "piece.rar")
    with open(mini, "wb") as out:
        out.write(rar5.SIGNATURE + bytes.fromhex(index["main_header"]))
        for chunk in source.chunks(entry["offset"], entry["length"]):
            if cancel is not None and cancel.is_set():
                raise RepairCancelled("Починка отменена")
            out.write(chunk)
        out.write(rar5.end_header())
    dest = os.path.join(work, "out")
    shutil.rmtree(dest, ignore_errors=True)
    _extract(extractor, mini, dest)
    got = os.path.join(dest, *([index["root"]] if index["root"] else []), *entry["path"].split("/"))
    if not os.path.isfile(got) or os.path.getsize(got) != entry["size"] or crc32_file(got) != entry["crc32"]:
        raise RepairError("файл из архива не прошёл проверку")
    os.remove(mini)
    return got


def repair(game_dir, index, problems, sources, extractor=None, progress=None, cancel=None):
    """Чинит файлы из problems, перебирая источники по порядку. Возвращает (исправленные пути,
    [(путь, причина)] неисправленных). Выключенный изданием файл остаётся выключенным."""
    if extractor is None:
        import client_install
        extractor = client_install.find_extractor()
    by_path = {f["path"]: f for f in index["files"]}
    work = os.path.join(game_dir, "PLGames", "repair")  # на том же диске: файл встаёт на место переносом
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    fixed, failed = [], []
    try:
        for i, p in enumerate(problems):
            entry = by_path.get(p["path"])
            if entry is None:
                failed.append((p["path"], "нет в индексе"))
                continue
            if progress:
                progress(i, len(problems), entry["path"])
            dst, _ = _on_disk(game_dir, entry["path"])
            reason = "нет источника" if dst else "недопустимый путь"
            for source in (sources if dst else ()):
                try:
                    got = _fetch_file(entry, index, source, work, extractor, cancel)
                except RepairCancelled:
                    raise
                except (RepairError, OSError) as e:
                    reason = f"{source.label}: {e}"
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                os.replace(got, dst)
                fixed.append(entry["path"])
                break
            else:
                failed.append((entry["path"], reason))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if progress:
        progress(len(problems), len(problems), "готово")
    return fixed, failed


# ---------------------------------------------------------------------------
# Фоновая работа для интерфейса
# ---------------------------------------------------------------------------

class ClientJob:
    """Проверка (и починка) клиента в фоне: статус для опроса из интерфейса, отмена."""

    def __init__(self):
        self._lock = threading.Lock()
        self._state = {"state": "idle"}
        self._thread = None
        self.cancel_event = threading.Event()

    def status(self):
        with self._lock:
            return dict(self._state)

    def _set(self, **kw):
        with self._lock:
            self._state.update(kw)

    def busy(self):
        return self._thread is not None and self._thread.is_alive()

    def cancel(self):
        self.cancel_event.set()

    def start(self, game_dir, index, sources_factory, full=True, problems=None):
        """problems=None — сначала проверка (полная или быстрая), потом починка найденного."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False, "Проверка уже идёт"
            self._state = {"state": "running", "progress": 0, "text": "Проверка файлов…"}
            self.cancel_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True,
                                            args=(game_dir, index, sources_factory, full, problems))
            self._thread.start()
        return True, ""

    def join(self, timeout=None):
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self, game_dir, index, sources_factory, full, problems):
        try:
            if problems is None:
                def on_check(done, total):
                    self._set(progress=int(done * 70 / total) if total else 0,
                              text=f"Проверка файлов: {done / 2 ** 30:.1f} из {total / 2 ** 30:.1f} ГБ")
                problems = check(game_dir, index, full=full, progress=on_check, cancel=self.cancel_event)
            if not problems:
                self._set(state="finished", progress=100, text="Файлы игры в порядке", fixed=[], failed=[])
                return

            def on_fix(i, n, path):
                self._set(progress=70 + int(i * 30 / max(n, 1)), text=f"Починка {i + 1} из {n}: {path}")
            fixed, failed = repair(game_dir, index, problems, sources_factory(), progress=on_fix,
                                   cancel=self.cancel_event)
            text = f"Исправлено файлов: {len(fixed)}" if not failed else \
                f"Исправлено {len(fixed)}, не удалось {len(failed)}"
            self._set(state="finished" if not failed else "error", progress=100, text=text,
                      fixed=fixed, failed=[{"path": p, "reason": r} for p, r in failed],
                      error="" if not failed else f"Не удалось починить: {failed[0][0]} ({failed[0][1]})")
        except RepairCancelled:
            self._set(state="error", error="Отменено")
        except Exception as e:
            self._set(state="error", error=f"Не удалось проверить файлы: {e}")
