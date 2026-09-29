"""Графические издания клиента: манифест компонентов, состояние клиента,
планировщик и исполнитель. Без UI и без pywebview.

Типы компонентов:
  mpq    — включить/выключить MPQ, которые уже лежат в клиенте (суффикс .disabled);
  files  — скачать файлы (проверка размера и SHA-256) и положить в папку игры;
  config — значения для WTF/Config.wtf; при выключении возвращаются прежние.

Издание — именованный набор компонентов; «Своё» — набор, собранный вручную.
Состояние клиента хранится в <игра>/PLGames/state.json.
"""

import copy
import hashlib
import json
import os
import re
import shutil
import time
from dataclasses import dataclass

import gameutils

SCHEMA = 1
COMPONENT_TYPES = ("mpq", "files", "config")
ALLOWED_FILE_EXT = frozenset({".dll", ".ini", ".fx", ".fxh", ".png", ".dds", ".mpq", ".conf", ".txt", ".json"})
FORBIDDEN_FILE_NAMES = frozenset({"wow.exe"})
STATE_DIR = "PLGames"
STATE_FILE = "state.json"

_ID_RE = re.compile(r"^[a-z0-9_]{1,40}$")
_CFG_KEY_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class ManifestError(ValueError):
    """Манифест недоступен или не прошёл проверку."""


class PlanError(ValueError):
    """Целевой набор компонентов нельзя применить (конфликт, неизвестный id)."""


class ApplyError(RuntimeError):
    """Применение не удалось; клиент возвращён в исходное состояние."""


class ApplyCancelled(ApplyError):
    """Отменено на этапе загрузки — клиент ещё не менялся."""


# ---------------------------------------------------------------------------
# Манифест
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FileEntry:
    path: str
    size: int
    sha256: str
    urls: tuple
    mutable: bool = False  # конфиг, который игра/ReShade переписывает сами: правки — не «устаревание»


MUTABLE_MARK = "*"  # в state.json вместо SHA-256 у mutable-файлов


@dataclass(frozen=True)
class MpqFile:
    name: str
    folder: str


@dataclass(frozen=True)
class Component:
    id: str
    name: str
    group: str
    type: str
    version: str = ""
    files: tuple = ()      # FileEntry — для type="files"
    mpqs: tuple = ()       # MpqFile — для type="mpq"
    values: tuple = ()     # ((ключ, значение), ...) — для type="config"
    conflicts: tuple = ()

    def values_dict(self):
        return dict(self.values)


@dataclass(frozen=True)
class Edition:
    id: str
    name: str
    tagline: str
    image: str
    components: tuple


@dataclass(frozen=True)
class TableRow:
    label: str
    components: tuple
    editions: tuple  # явный список изданий с галочкой (перекрывает components)


@dataclass(frozen=True)
class Manifest:
    content_version: str
    components: tuple
    editions: tuple
    table: tuple

    def component(self, cid):
        for c in self.components:
            if c.id == cid:
                return c
        raise KeyError(cid)


def _field(obj, key, typ, ctx):
    value = obj.get(key) if isinstance(obj, dict) else None
    if not isinstance(value, typ):
        raise ManifestError(f"{ctx}: поле «{key}» отсутствует или имеет неверный тип")
    return value


def _rel_path(path, ctx, allowed_ext=None):
    norm = path.replace("\\", "/")
    parts = norm.split("/")
    if (not norm or len(norm) > 200 or norm.startswith("/") or ":" in norm
            or any(p in ("", ".", "..") for p in parts)):
        raise ManifestError(f"{ctx}: недопустимый путь «{path}»")
    if allowed_ext is not None and (os.path.splitext(norm)[1].lower() not in allowed_ext
                                    or parts[-1].lower() in FORBIDDEN_FILE_NAMES):
        raise ManifestError(f"{ctx}: недопустимый тип файла «{path}»")
    return norm


def _parse_component(raw, index):
    ctx = f"компонент №{index + 1}"
    cid = _field(raw, "id", str, ctx)
    if not _ID_RE.match(cid):
        raise ManifestError(f"{ctx}: недопустимый id «{cid}»")
    ctx = f"компонент «{cid}»"
    ctype = _field(raw, "type", str, ctx)
    if ctype not in COMPONENT_TYPES:
        raise ManifestError(f"{ctx}: неизвестный тип «{ctype}»")
    conflicts = raw.get("conflicts", [])
    if not isinstance(conflicts, list) or not all(isinstance(x, str) for x in conflicts):
        raise ManifestError(f"{ctx}: поле «conflicts» должно быть списком id")
    kw = {"id": cid, "name": _field(raw, "name", str, ctx), "group": str(raw.get("group") or "Прочее"),
          "type": ctype, "version": str(raw.get("version", "")), "conflicts": tuple(conflicts)}
    if ctype == "mpq":
        mpqs = []
        for f in _field(raw, "files", list, ctx):
            name = _field(f, "name", str, ctx)
            if os.path.basename(name) != name or "/" in name or os.path.splitext(name)[1].lower() != ".mpq":
                raise ManifestError(f"{ctx}: недопустимое имя MPQ «{name}»")
            mpqs.append(MpqFile(name=name, folder=_rel_path(_field(f, "folder", str, ctx), ctx)))
        if not mpqs:
            raise ManifestError(f"{ctx}: пустой список файлов")
        kw["mpqs"] = tuple(mpqs)
    elif ctype == "files":
        files = []
        for f in _field(raw, "files", list, ctx):
            path = _rel_path(_field(f, "path", str, ctx), ctx, ALLOWED_FILE_EXT)
            size = f.get("size")
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                raise ManifestError(f"{ctx}: неверный размер у «{path}»")
            sha = str(f.get("sha256", "")).lower()
            if not _SHA_RE.match(sha):
                raise ManifestError(f"{ctx}: неверный SHA-256 у «{path}»")
            urls = f.get("urls")
            if (not isinstance(urls, list) or not urls
                    or not all(isinstance(u, str) and u.startswith("https://") for u in urls)):
                raise ManifestError(f"{ctx}: у «{path}» должны быть https-ссылки")
            files.append(FileEntry(path=path, size=size, sha256=sha, urls=tuple(urls),
                                   mutable=bool(f.get("mutable", False))))
        if not files:
            raise ManifestError(f"{ctx}: пустой список файлов")
        if len({f.path.lower() for f in files}) != len(files):
            raise ManifestError(f"{ctx}: повторяющиеся пути файлов")
        kw["files"] = tuple(files)
    else:
        values = _field(raw, "values", dict, ctx)
        if not values:
            raise ManifestError(f"{ctx}: пустой набор значений")
        for k, v in values.items():
            if not _CFG_KEY_RE.match(k) or not isinstance(v, str) or any(ch in v for ch in '"\r\n'):
                raise ManifestError(f"{ctx}: недопустимое значение «{k}»")
        kw["values"] = tuple(sorted(values.items()))
    return Component(**kw)


def _find_conflict(by_id, ids):
    ids = set(ids)
    for cid in sorted(ids):
        for other in by_id[cid].conflicts:
            if other in ids:
                return cid, other
    return None


def parse_manifest(data):
    """Проверяет и разбирает манифест. Всё, что не прошло проверку, — ManifestError."""
    if not isinstance(data, dict):
        raise ManifestError("Манифест должен быть JSON-объектом")
    if data.get("schema") != SCHEMA:
        raise ManifestError(f"Неподдерживаемая версия схемы манифеста: {data.get('schema')!r}")

    components = []
    for i, raw in enumerate(_field(data, "components", list, "манифест")):
        comp = _parse_component(raw, i)
        if any(c.id == comp.id for c in components):
            raise ManifestError(f"Повторяющийся id компонента «{comp.id}»")
        components.append(comp)
    by_id = {c.id: c for c in components}
    for c in components:
        for other in c.conflicts:
            if other not in by_id:
                raise ManifestError(f"компонент «{c.id}»: неизвестный конфликт «{other}»")
    # Два files-компонента с общим путём обязаны быть взаимоисключающими —
    # иначе удаление одного снесёт файл другого.
    owners = {}
    for c in components:
        for f in c.files:
            for other in owners.get(f.path.lower(), []):
                if other not in c.conflicts and c.id not in by_id[other].conflicts:
                    raise ManifestError(f"Файл «{f.path}» есть в «{other}» и «{c.id}», "
                                        "но они не объявлены конфликтующими")
            owners.setdefault(f.path.lower(), []).append(c.id)

    editions = []
    for i, raw in enumerate(_field(data, "editions", list, "манифест")):
        ctx = f"издание №{i + 1}"
        eid = _field(raw, "id", str, ctx)
        if not _ID_RE.match(eid) or any(e.id == eid for e in editions):
            raise ManifestError(f"{ctx}: недопустимый или повторяющийся id «{eid}»")
        members = _field(raw, "components", list, ctx)
        unknown = [m for m in members if m not in by_id]
        if unknown:
            raise ManifestError(f"издание «{eid}»: неизвестный компонент «{unknown[0]}»")
        clash = _find_conflict(by_id, members)
        if clash:
            raise ManifestError(f"издание «{eid}»: несовместимые компоненты «{clash[0]}» и «{clash[1]}»")
        image = str(raw.get("image", ""))
        if image and not image.startswith("https://"):
            raise ManifestError(f"издание «{eid}»: картинка должна быть https-ссылкой")
        editions.append(Edition(id=eid, name=_field(raw, "name", str, ctx), tagline=str(raw.get("tagline", "")),
                                image=image, components=tuple(members)))
    if not editions:
        raise ManifestError("В манифесте нет изданий")

    eids = {e.id for e in editions}
    table = []
    for i, raw in enumerate(data.get("table", [])):
        ctx = f"строка таблицы №{i + 1}"
        label = _field(raw, "label", str, ctx)
        comps, explicit = raw.get("components", []), raw.get("editions", [])
        if not isinstance(comps, list) or not isinstance(explicit, list) or not (comps or explicit):
            raise ManifestError(f"{ctx}: нужны «components» или «editions»")
        bad = [x for x in comps if x not in by_id] + [x for x in explicit if x not in eids]
        if bad:
            raise ManifestError(f"{ctx}: неизвестный id «{bad[0]}»")
        table.append(TableRow(label=label, components=tuple(comps), editions=tuple(explicit)))

    return Manifest(content_version=str(data.get("content_version", "")), components=tuple(components),
                    editions=tuple(editions), table=tuple(table))


def table_checks(manifest):
    """Строки таблицы сравнения: галочка, если в издание входят все компоненты строки
    (или издание явно перечислено в строке)."""
    rows = []
    for r in manifest.table:
        checks = {e.id: (e.id in r.editions) if r.editions else all(c in e.components for c in r.components)
                  for e in manifest.editions}
        rows.append({"label": r.label, "checks": checks})
    return rows


def _write_json_atomic(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_manifest(urls, cache_path, builtin_path=None, session=None, timeout=5):
    """Манифест: сеть (urls по порядку) → кэш последнего валидного → встроенный.
    Возвращает (Manifest, источник): url, "cache" или "builtin"."""
    if session is None:
        import requests
        session = requests.Session()
    errors = []
    for url in urls:
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code != 200:
                raise ManifestError(f"HTTP {resp.status_code}")
            data = resp.json()
            manifest = parse_manifest(data)
        except Exception as e:  # сеть, JSON, валидация — пробуем следующий источник
            errors.append(f"{url}: {e}")
            continue
        try:
            _write_json_atomic(cache_path, data)
        except OSError:
            pass
        return manifest, url
    for path, source in ((cache_path, "cache"), (builtin_path, "builtin")):
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                return parse_manifest(json.load(f)), source
        except (OSError, ValueError) as e:  # ManifestError — тоже ValueError
            errors.append(f"{source}: {e}")
    raise ManifestError("Манифест изданий недоступен: " + "; ".join(errors))


# ---------------------------------------------------------------------------
# Состояние клиента
# ---------------------------------------------------------------------------

def state_path(game_dir):
    return os.path.join(game_dir, STATE_DIR, STATE_FILE)


def empty_state():
    return {"schema": SCHEMA, "edition": None, "content_version": "", "components": {}, "backups": {}}


def load_state(game_dir):
    state = empty_state()
    try:
        with open(state_path(game_dir), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return state
    if isinstance(data, dict) and data.get("schema") == SCHEMA:
        if isinstance(data.get("edition"), str):
            state["edition"] = data["edition"]
        state["content_version"] = str(data.get("content_version", ""))
        if isinstance(data.get("components"), dict):
            state["components"] = data["components"]
        if isinstance(data.get("backups"), dict):
            state["backups"] = data["backups"]
    return state


def save_state(game_dir, state):
    _write_json_atomic(state_path(game_dir), state)


def _file_ok(game_dir, entry):
    p = gameutils.safe_join(game_dir, entry.path)
    return bool(p) and os.path.isfile(p) and (entry.mutable or os.path.getsize(p) == entry.size)


def component_status(manifest, game_dir, state):
    """{id: {available, active, partial, outdated}} для каждого компонента.
    mpq: available — хотя бы один файл есть в клиенте; active — все имеющиеся включены.
    files/config: active — установлен нами (запись в state); outdated — версия/значения устарели."""
    out = {}
    records = state.get("components", {})
    for c in manifest.components:
        if c.type == "mpq":
            st = [gameutils.mpq_status(game_dir, m.name, m.folder) for m in c.mpqs]
            present = [s for s in st if s[0]]
            out[c.id] = {"available": bool(present), "active": bool(present) and all(s[1] for s in present),
                         "partial": any(s[1] for s in present), "outdated": False}
            continue
        rec = records.get(c.id)
        installed = isinstance(rec, dict)
        if c.type == "files":
            current = (installed and rec.get("version") == c.version
                       and set(rec.get("files") or {}) == {f.path for f in c.files}
                       and all(_file_ok(game_dir, f) for f in c.files))
        else:
            current = installed and rec.get("applied") == c.values_dict()
        out[c.id] = {"available": True, "active": installed, "partial": installed,
                     "outdated": installed and not current}
    return out


def detect_edition(manifest, status):
    """id издания, чьи доступные компоненты ровно совпадают с активными; иначе «custom»."""
    if any(s["partial"] and not s["active"] for s in status.values()):
        return "custom"
    active = {cid for cid, s in status.items() if s["active"]}
    for e in manifest.editions:
        if {cid for cid in e.components if status[cid]["available"]} == active:
            return e.id
    return "custom"


# ---------------------------------------------------------------------------
# Планировщик
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Action:
    kind: str       # mpq_on | mpq_off | files_install | files_remove | config_apply | config_revert
    component: str


def plan(manifest, status, state, target_ids):
    """Действия, переводящие клиент к целевому набору: сначала удаления, потом установки
    (так освобождаются общие файлы конфликтующих компонентов). Устаревший компонент
    переустанавливается парой «удалить + установить»."""
    target = set(target_ids)
    by_id = {c.id: c for c in manifest.components}
    unknown = sorted(target - set(by_id))
    if unknown:
        raise PlanError(f"Неизвестный компонент «{unknown[0]}»")
    clash = _find_conflict(by_id, target)
    if clash:
        raise PlanError(f"Компоненты «{by_id[clash[0]].name}» и «{by_id[clash[1]].name}» несовместимы")
    removes, installs = [], []
    for c in manifest.components:
        s, want = status[c.id], c.id in target
        if c.type == "mpq":
            if not s["available"]:
                continue
            if want and not s["active"]:
                installs.append(Action("mpq_on", c.id))
            elif not want and s["partial"]:
                removes.append(Action("mpq_off", c.id))
            continue
        on, off = ("files_install", "files_remove") if c.type == "files" else ("config_apply", "config_revert")
        if s["active"] and (not want or s["outdated"]):
            removes.append(Action(off, c.id))
        if want and (not s["active"] or s["outdated"]):
            installs.append(Action(on, c.id))
    return removes + installs


# ---------------------------------------------------------------------------
# Исполнитель
# ---------------------------------------------------------------------------

def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _move_back(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.replace(src, dst)


class Executor:
    """Применяет план к папке игры. Сначала все загрузки во временную папку (клиент
    не трогается), затем изменения с журналом отмены; при любой ошибке журнал
    откатывается, а state.json остаётся прежним."""

    def __init__(self, manifest, game_dir, state, session=None, progress=None, is_running=None, cancel=None):
        self.manifest = manifest
        self._cancel = cancel  # threading.Event: отмена действует только до начала изменений клиента
        self.game_dir = game_dir
        self.state = copy.deepcopy(state)
        self.state.setdefault("components", {})
        self.state.setdefault("backups", {})
        self._session = session
        self._progress = progress or (lambda **kw: None)
        self._is_running = is_running or gameutils.is_game_running
        work = os.path.join(game_dir, STATE_DIR)
        self._tmp = os.path.join(work, "tmp")
        self._backup_dir = os.path.join(work, "backup")

    def run(self, actions, edition=None):
        if not actions:
            self.state["edition"] = edition
            save_state(self.game_dir, self.state)
            return self.state
        if self._is_running(self.game_dir):
            raise ApplyError("Закройте игру, чтобы сменить издание")
        shutil.rmtree(self._tmp, ignore_errors=True)
        os.makedirs(self._tmp)
        try:
            downloads = self._download_all(actions)
            self._check_cancel()
            journal = []
            try:
                for i, action in enumerate(actions):
                    comp = self.manifest.component(action.component)
                    self._progress(stage="apply", done=i, total=len(actions), text=comp.name)
                    getattr(self, "_do_" + action.kind)(comp, downloads, journal)
                self.state["edition"] = edition
                self.state["content_version"] = self.manifest.content_version
                save_state(self.game_dir, self.state)
            except Exception as e:
                undo_errors = []
                for undo in reversed(journal):
                    try:
                        undo()
                    except Exception as ue:
                        undo_errors.append(str(ue))
                msg = str(e) if isinstance(e, ApplyError) else f"Не удалось применить изменения: {e}"
                if undo_errors:
                    msg += (f". Откат выполнен не полностью ({'; '.join(undo_errors[:3])}) — "
                            "проверьте клиент или выберите издание заново")
                raise ApplyError(msg) from e
            self._progress(stage="apply", done=len(actions), total=len(actions), text="готово")
            return self.state
        finally:
            shutil.rmtree(self._tmp, ignore_errors=True)

    # ---- загрузка ----

    def _check_cancel(self):
        if self._cancel is not None and self._cancel.is_set():
            raise ApplyCancelled("Смена издания отменена")

    def _session_obj(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
        return self._session

    def _download_all(self, actions):
        entries = [(comp, f) for a in actions if a.kind == "files_install"
                   for comp in [self.manifest.component(a.component)] for f in comp.files]
        total = sum(f.size for _, f in entries)
        done, result = 0, {}
        for comp, f in entries:
            dst = os.path.join(self._tmp, "dl", comp.id, hashlib.sha1(f.path.encode()).hexdigest())
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            base = done
            self._fetch(f, dst, lambda n, p=f.path: self._progress(stage="download", done=base + n,
                                                                   total=total, text=p))
            done += f.size
            result[(comp.id, f.path)] = dst
        return result

    def _fetch(self, entry, dst, on_bytes):
        errors = []
        for url in entry.urls:
            try:
                h, n = hashlib.sha256(), 0
                with self._session_obj().get(url, stream=True, timeout=(10, 60)) as resp:
                    if resp.status_code != 200:
                        raise ApplyError(f"HTTP {resp.status_code}")
                    with open(dst, "wb") as out:
                        for chunk in resp.iter_content(1 << 16):
                            self._check_cancel()
                            if not chunk:
                                continue
                            n += len(chunk)
                            if n > entry.size:
                                raise ApplyError("файл больше ожидаемого")
                            h.update(chunk)
                            out.write(chunk)
                            on_bytes(n)
                if n != entry.size or h.hexdigest() != entry.sha256:
                    raise ApplyError("контрольная сумма не совпала")
                return
            except ApplyCancelled:
                raise
            except Exception as e:  # следующее зеркало
                errors.append(f"{url}: {e}")
        raise ApplyError(f"Не удалось скачать {entry.path} ({'; '.join(errors)})")

    # ---- применение ----

    def _target(self, rel):
        path = gameutils.safe_join(self.game_dir, rel)
        if not path:
            raise ApplyError(f"Недопустимый путь «{rel}»")
        return path

    def _kept_path(self, rel):
        """Уникальное место в PLGames/backup/kept/<время>[-N]/<rel> для файла игрока."""
        stamp = time.strftime("%Y%m%d-%H%M%S")
        for n in range(1000):
            base = os.path.join(self._backup_dir, "kept", stamp if n == 0 else f"{stamp}-{n}")
            path = os.path.join(base, *rel.split("/"))
            if not os.path.lexists(path):
                return path
        raise ApplyError(f"Не удалось сохранить копию {rel} в {STATE_DIR}/backup/kept")

    def _move(self, src, dst, journal):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.replace(src, dst)
        journal.append(lambda: _move_back(dst, src))

    def _toggle(self, comp, enable, journal):
        for m in comp.mpqs:
            installed, enabled, _ = gameutils.mpq_status(self.game_dir, m.name, m.folder)
            if not installed or enabled == enable:
                continue
            if not gameutils.toggle_mpq(self.game_dir, m.name, m.folder, enable):
                verb = "включить" if enable else "выключить"
                raise ApplyError(f"Не удалось {verb} {m.name}: файл занят другой программой?")
            journal.append(lambda m=m: gameutils.toggle_mpq(self.game_dir, m.name, m.folder, not enable))

    def _do_mpq_on(self, comp, downloads, journal):
        self._toggle(comp, True, journal)

    def _do_mpq_off(self, comp, downloads, journal):
        self._toggle(comp, False, journal)

    def _do_files_install(self, comp, downloads, journal):
        record, backups = {}, self.state["backups"]
        for f in comp.files:
            dst = self._target(f.path)
            if os.path.lexists(dst):
                # Чужой файл на нашем месте (например, свой ReShade игрока) — бережём.
                bak = os.path.join(self._backup_dir, *f.path.split("/"))
                if os.path.lexists(bak):
                    raise ApplyError(f"Уже есть резервная копия {f.path} в {STATE_DIR}/backup — "
                                     "верните или удалите её вручную")
                self._move(dst, bak, journal)
                backups[f.path] = f"{STATE_DIR}/backup/{f.path}"
                journal.append(lambda p=f.path: backups.pop(p, None))
            self._move(downloads[(comp.id, f.path)], dst, journal)
            record[f.path] = MUTABLE_MARK if f.mutable else f.sha256
        self.state["components"][comp.id] = {"version": comp.version, "files": record}
        journal.append(lambda: self.state["components"].pop(comp.id, None))

    def _do_files_remove(self, comp, downloads, journal):
        record, backups = self.state["components"].get(comp.id) or {}, self.state["backups"]
        for rel, our_sha in list((record.get("files") or {}).items()):
            dst = gameutils.safe_join(self.game_dir, rel)
            if not dst:
                continue
            if os.path.isfile(dst):
                if our_sha == MUTABLE_MARK or _sha256_file(dst) == our_sha:
                    # Наш файл (или наш конфиг, переписанный игрой) — во временную папку, удалится после успеха.
                    undo_path = os.path.join(self._tmp, "undo", comp.id, hashlib.sha1(rel.encode()).hexdigest())
                    self._move(dst, undo_path, journal)
                else:
                    # Игрок заменил наш файл своим — не удаляем никогда, откладываем в backup/kept.
                    self._move(dst, self._kept_path(rel), journal)
            bak_rel = backups.get(rel)
            if bak_rel:
                bak = gameutils.safe_join(self.game_dir, bak_rel)
                if bak and os.path.lexists(bak):
                    self._move(bak, dst, journal)
                backups.pop(rel)
                journal.append(lambda r=rel, b=bak_rel: backups.__setitem__(r, b))
        old = self.state["components"].pop(comp.id, None)
        journal.append(lambda: self.state["components"].__setitem__(comp.id, old))
        self._prune_empty_dirs(record.get("files") or {})

    def _prune_empty_dirs(self, rel_paths):
        """Убрать опустевшие папки, оставшиеся от удалённых файлов (reshade-shaders/…).
        Непустые и сама папка игры не трогаются; откат пересоздаёт папки сам (_move_back)."""
        root = os.path.normcase(os.path.abspath(self.game_dir))
        for rel in rel_paths:
            path = gameutils.safe_join(self.game_dir, rel)
            parent = os.path.dirname(path) if path else None
            while parent and os.path.normcase(parent) != root:
                try:
                    os.rmdir(parent)  # только пустую
                except OSError:
                    break
                parent = os.path.dirname(parent)

    def _do_config_apply(self, comp, downloads, journal):
        values = comp.values_dict()
        current = {k.lower(): v for k, v in gameutils.read_config_wtf(self.game_dir).items()}
        previous = {k: current.get(k.lower()) for k in values}
        if not gameutils.write_config_wtf(self.game_dir, values):
            raise ApplyError("Не удалось записать WTF/Config.wtf")
        journal.append(lambda: gameutils.write_config_wtf(self.game_dir, previous))
        self.state["components"][comp.id] = {"previous": previous, "applied": values}
        journal.append(lambda: self.state["components"].pop(comp.id, None))

    def _do_config_revert(self, comp, downloads, journal):
        record = self.state["components"].get(comp.id) or {}
        previous = {k: v for k, v in (record.get("previous") or {}).items()
                    if _CFG_KEY_RE.match(str(k)) and (v is None or isinstance(v, str))}
        applied = record.get("applied") or comp.values_dict()
        if previous and not gameutils.write_config_wtf(self.game_dir, previous):
            raise ApplyError("Не удалось записать WTF/Config.wtf")
        journal.append(lambda: gameutils.write_config_wtf(self.game_dir, applied))
        old = self.state["components"].pop(comp.id, None)
        journal.append(lambda: self.state["components"].__setitem__(comp.id, old))
