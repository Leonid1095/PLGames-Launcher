"""Графические издания клиента: манифест компонентов, состояние клиента,
планировщик и исполнитель. Без UI и без pywebview.

Типы компонентов:
  mpq    — включить/выключить MPQ, которые уже лежат в клиенте (суффикс .disabled);
  files  — скачать файлы (проверка размера и SHA-256) и положить в папку игры;
  config — значения для WTF/Config.wtf; при выключении возвращаются прежние;
  zip    — архив с папками (аддоны): раскладывается в target, исполняемые файлы запрещены;
  installer — пакет со своим установщиком (Northlight): распаковывается вне клиента,
           его команды install/uninstall запускаются с {client} и {locale}.

У компонента есть область (scope): «edition» — входит в издания; «addon» — аддоны,
которые игрок включает отдельно, смена издания их не трогает.

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

SCHEMA = 1                 # state.json
MANIFEST_SCHEMAS = (1, 2)  # 2: есть zip/installer и области; лаунчеры до 0.5 читают только 1
COMPONENT_TYPES = ("mpq", "files", "config", "zip", "installer")
SCOPES = ("edition", "addon")
CAPABILITIES = {"vulkan13": "Vulkan 1.3"}  # возможности ПК, которые может требовать компонент (requires)
ALLOWED_FILE_EXT = frozenset({".dll", ".ini", ".fx", ".fxh", ".png", ".dds", ".mpq", ".conf", ".txt", ".json"})
FORBIDDEN_FILE_NAMES = frozenset({"wow.exe"})
# Что из архива аддона попадает в клиент; остальное (скриншоты, исходники) пропускается.
ADDON_FILE_EXT = frozenset({".lua", ".toc", ".xml", ".tga", ".blp", ".ttf", ".otf", ".mp3", ".ogg", ".wav",
                            ".txt", ".md"})
# Исполняемое в архиве аддона — повод отказаться от архива целиком.
EXECUTABLE_EXT = frozenset({".exe", ".dll", ".bat", ".cmd", ".com", ".scr", ".ps1", ".vbs", ".js", ".msi",
                            ".jar", ".pyd", ".sys"})
MAX_ARCHIVE_FILE = 64 * 1024 * 1024
MAX_ARCHIVE_TOTAL = 512 * 1024 * 1024
ARCHIVE_KEY = "\0archive"  # ключ загрузки архива компонента в словаре загрузок
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
    scope: str = "edition"
    archive: object = None  # FileEntry — для type="zip" и "installer"
    target: str = ""       # zip: куда раскладывать папки (Interface/AddOns)
    folders: tuple = ()    # zip: папки верхнего уровня, которые берутся из архива
    install: tuple = ()    # installer: команда, первый элемент — exe внутри пакета
    uninstall: tuple = ()
    progress: str = ""     # installer: regex строки прогресса (группы pct и label)
    marker: str = ""       # installer: файл в клиенте, который есть, пока установлено
    description: str = ""
    author: str = ""
    license: str = ""
    default: bool = False  # аддон, который ставится новым игрокам сразу
    requires: str = ""     # возможность ПК из CAPABILITIES; без неё в издании ставится fallback
    fallback: str = ""     # id компонента-замены

    def values_dict(self):
        return dict(self.values)


@dataclass(frozen=True)
class Edition:
    id: str
    name: str
    tagline: str
    image: str
    components: tuple
    note: str = ""  # предупреждение на карточке (объём загрузки, время установки)


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


_FOLDER_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\- ]{0,63}$")


def _parse_entry(f, path, ctx):
    """Размер, SHA-256 и https-зеркала одного скачиваемого файла."""
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
    return FileEntry(path=path, size=size, sha256=sha, urls=tuple(urls), mutable=bool(f.get("mutable", False)))


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
    scope = raw.get("scope", "edition")
    if scope not in SCOPES:
        raise ManifestError(f"{ctx}: неизвестная область «{scope}»")
    requires, fallback = raw.get("requires", ""), raw.get("fallback", "")
    if requires and requires not in CAPABILITIES:
        raise ManifestError(f"{ctx}: неизвестное требование «{requires}»")
    if not isinstance(fallback, str) or (fallback and not requires):
        raise ManifestError(f"{ctx}: замена «fallback» нужна только вместе с «requires»")
    kw = {"id": cid, "name": _field(raw, "name", str, ctx), "group": str(raw.get("group") or "Прочее"),
          "type": ctype, "version": str(raw.get("version", "")), "conflicts": tuple(conflicts),
          "scope": scope, "description": str(raw.get("description", ""))[:400],
          "author": str(raw.get("author", ""))[:120], "license": str(raw.get("license", ""))[:60],
          "default": bool(raw.get("default", False)), "requires": requires, "fallback": fallback}
    if ctype in ("zip", "installer"):
        kw["archive"] = _parse_entry(_field(raw, "archive", dict, ctx), f"{cid}.zip", ctx)
    if ctype == "zip":
        kw["target"] = _rel_path(_field(raw, "target", str, ctx), ctx)
        folders = _field(raw, "folders", list, ctx)
        if not folders or not all(isinstance(x, str) and _FOLDER_RE.match(x) for x in folders):
            raise ManifestError(f"{ctx}: недопустимый список папок")
        kw["folders"] = tuple(folders)
    elif ctype == "installer":
        for key in ("install", "uninstall"):
            argv = _field(raw, key, list, ctx)
            if not argv or not all(isinstance(a, str) and len(a) <= 200 for a in argv):
                raise ManifestError(f"{ctx}: пустая или неверная команда «{key}»")
            exe = _rel_path(argv[0], ctx)
            if not exe.lower().endswith(".exe"):
                raise ManifestError(f"{ctx}: команда «{key}» должна запускать .exe из пакета")
            kw[key] = (exe,) + tuple(argv[1:])
        pattern = str(raw.get("progress", ""))
        try:
            re.compile(pattern)
        except re.error:
            raise ManifestError(f"{ctx}: неверное выражение прогресса")
        kw["progress"] = pattern
        kw["marker"] = _rel_path(_field(raw, "marker", str, ctx), ctx)
    elif ctype == "mpq":
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
            files.append(_parse_entry(f, path, ctx))
        if not files:
            raise ManifestError(f"{ctx}: пустой список файлов")
        if len({f.path.lower() for f in files}) != len(files):
            raise ManifestError(f"{ctx}: повторяющиеся пути файлов")
        kw["files"] = tuple(files)
    elif ctype == "config":
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
    if data.get("schema") not in MANIFEST_SCHEMAS:
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
        if c.fallback:
            alt = by_id.get(c.fallback)
            if alt is None or alt.scope != c.scope or alt.requires:
                raise ManifestError(f"компонент «{c.id}»: недопустимая замена «{c.fallback}»")
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
        addons = [m for m in members if by_id[m].scope != "edition"]
        if addons:
            raise ManifestError(f"издание «{eid}»: аддон «{addons[0]}» не может входить в издание")
        clash = _find_conflict(by_id, members) or _find_conflict(by_id, _resolve(by_id, members, frozenset()))
        if clash:
            raise ManifestError(f"издание «{eid}»: несовместимые компоненты «{clash[0]}» и «{clash[1]}»")
        image = str(raw.get("image", ""))
        if image and not image.startswith("https://"):
            raise ManifestError(f"издание «{eid}»: картинка должна быть https-ссылкой")
        editions.append(Edition(id=eid, name=_field(raw, "name", str, ctx), tagline=str(raw.get("tagline", "")),
                                image=image, components=tuple(members), note=str(raw.get("note", ""))[:300]))
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
        if data.get("addons_initialized") is True:
            state["addons_initialized"] = True
    return state


def save_state(game_dir, state):
    _write_json_atomic(state_path(game_dir), state)


def _file_ok(game_dir, entry):
    p = gameutils.safe_join(game_dir, entry.path)
    return bool(p) and os.path.isfile(p) and (entry.mutable or os.path.getsize(p) == entry.size)


def component_status(manifest, game_dir, state):
    """{id: {available, active, partial, outdated, foreign}} для каждого компонента.
    mpq: available — хотя бы один файл есть в клиенте; active — все имеющиеся включены.
    files/config/zip/installer: active — установлен нами (запись в state); outdated — версия/значения устарели.
    foreign — у zip: папки аддона в клиенте есть, но поставил их игрок сам."""
    out = {}
    records = state.get("components", {})
    for c in manifest.components:
        if c.type == "mpq":
            st = [gameutils.mpq_status(game_dir, m.name, m.folder) for m in c.mpqs]
            present = [s for s in st if s[0]]
            out[c.id] = {"available": bool(present), "active": bool(present) and all(s[1] for s in present),
                         "partial": any(s[1] for s in present), "outdated": False, "foreign": False}
            continue
        rec = records.get(c.id)
        installed = isinstance(rec, dict)
        foreign = False  # zip: папки аддона уже лежат в клиенте, но поставил их не лаунчер
        if c.type == "files":
            current = (installed and rec.get("version") == c.version
                       and set(rec.get("files") or {}) == {f.path for f in c.files}
                       and all(_file_ok(game_dir, f) for f in c.files))
        elif c.type == "zip":
            root = gameutils.safe_join(game_dir, c.target)
            present = bool(root) and all(os.path.isdir(os.path.join(root, d)) for d in c.folders)
            current = installed and rec.get("version") == c.version and present
            # своя копия игрока — папка с .toc; пустые папки из раздачи клиента не в счёт
            foreign = (not installed and bool(root)
                       and any(os.path.isfile(os.path.join(root, d, d + ".toc")) for d in c.folders))
        elif c.type == "installer":
            marker = gameutils.safe_join(game_dir, c.marker)
            current = installed and rec.get("version") == c.version and bool(marker) and os.path.isfile(marker)
        else:
            current = installed and rec.get("applied") == c.values_dict()
        out[c.id] = {"available": True, "active": installed, "partial": installed,
                     "outdated": installed and not current, "foreign": foreign}
    return out


def download_bytes(manifest, status, component_ids):
    """Сколько придётся скачать, чтобы включить эти компоненты (уже установленное не считается)."""
    total = 0
    for cid in component_ids:
        c = manifest.component(cid)
        if status[cid]["active"] and not status[cid]["outdated"]:
            continue
        total += sum(f.size for f in c.files) + (c.archive.size if c.archive is not None else 0)
    return total


def _resolve(by_id, ids, caps):
    out = []
    for cid in ids:
        c = by_id[cid]
        pick = cid if not c.requires or c.requires in caps else c.fallback
        if pick and pick not in out:
            out.append(pick)
    return tuple(out)


def resolve_components(manifest, component_ids, caps):
    """Состав под этот ПК: компонент, которому не хватает возможности (requires не в caps),
    заменяется своим fallback, а без замены выпадает. Порядок сохраняется, повторов нет."""
    return _resolve({c.id: c for c in manifest.components}, component_ids, caps)


def detect_edition(manifest, status):
    """id издания, чьи доступные компоненты ровно совпадают с активными; иначе «custom».
    Издание узнаётся и в варианте с заменами (ПК без нужной возможности).
    Аддоны (scope=addon) на издание не влияют."""
    scoped = {c.id for c in manifest.components if c.scope == "edition"}
    if any(status[cid]["partial"] and not status[cid]["active"] for cid in scoped):
        return "custom"
    active = {cid for cid in scoped if status[cid]["active"]}
    for e in manifest.editions:
        for variant in (e.components, resolve_components(manifest, e.components, frozenset())):
            if {cid for cid in variant if status[cid]["available"]} == active:
                return e.id
    return "custom"


# ---------------------------------------------------------------------------
# Планировщик
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Action:
    kind: str       # mpq_on | mpq_off | files_install | files_remove | config_apply | config_revert
    component: str


_ACTIONS = {"files": ("files_install", "files_remove"), "config": ("config_apply", "config_revert"),
            "zip": ("zip_install", "zip_remove"), "installer": ("installer_run", "installer_remove")}


def plan(manifest, status, state, target_ids, scope="edition"):
    """Действия, переводящие клиент к целевому набору: сначала удаления, потом установки
    (так освобождаются общие файлы конфликтующих компонентов). Устаревший компонент
    переустанавливается парой «удалить + установить». Трогаются только компоненты
    области scope: издание не снимает аддоны, аддоны не меняют издание."""
    target = set(target_ids)
    by_id = {c.id: c for c in manifest.components}
    unknown = sorted(target - set(by_id))
    if unknown:
        raise PlanError(f"Неизвестный компонент «{unknown[0]}»")
    foreign = sorted(cid for cid in target if by_id[cid].scope != scope)
    if foreign:
        raise PlanError(f"Компонент «{by_id[foreign[0]].name}» здесь не выбирается")
    clash = _find_conflict(by_id, target)
    if clash:
        raise PlanError(f"Компоненты «{by_id[clash[0]].name}» и «{by_id[clash[1]].name}» несовместимы")
    removes, installs = [], []
    for c in manifest.components:
        if c.scope != scope:
            continue
        s, want = status[c.id], c.id in target
        if c.type == "mpq":
            if not s["available"]:
                continue
            if want and not s["active"]:
                installs.append(Action("mpq_on", c.id))
            elif not want and s["partial"]:
                removes.append(Action("mpq_off", c.id))
            continue
        on, off = _ACTIONS[c.type]
        if s["active"] and (not want or s["outdated"]):
            removes.append(Action(off, c.id))
        if want and (not s["active"] or s["outdated"]):
            installs.append(Action(on, c.id))
    return removes + installs


# ---------------------------------------------------------------------------
# Исполнитель
# ---------------------------------------------------------------------------

ADOPT = object()   # файл уже лежит в клиенте байт-в-байт — устанавливать нечего
MAX_RESUMES = 20  # сколько раз докачивать оборванный файл с одного зеркала (каждый раз с продвижением)


class _BadContent(Exception):
    """Сервер отдал не тот файл: размер или хеш не сходятся."""


def _sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h


def _sha256_file(path):
    return _sha256_of(path).hexdigest()


def _remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _move_back(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.replace(src, dst)


class Executor:
    """Применяет план к папке игры. Сначала все загрузки во временную папку (клиент
    не трогается), затем изменения с журналом отмены; при любой ошибке журнал
    откатывается, а state.json остаётся прежним."""

    def __init__(self, manifest, game_dir, state, session=None, progress=None, is_running=None, cancel=None,
                 installers_dir=None):
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
        # Скачанное живёт здесь до установки: обрыв, отмена или ошибка не заставляют качать заново.
        self._dl_dir = os.path.join(work, "downloads")
        # Пакеты с установщиком (Northlight) распаковываются вне клиента — так требует их установщик.
        self._installers_dir = installers_dir or os.path.join(
            os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "PLGamesLauncher", "installers")
        self._after_success = []

    def run(self, actions, edition=None):
        """edition=None — набор аддонов: записанное издание не меняется."""
        if not actions:
            if edition is not None:
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
                if edition is not None:
                    self.state["edition"] = edition
                self.state["content_version"] = self.manifest.content_version
                save_state(self.game_dir, self.state)
                for cleanup in self._after_success:
                    try:
                        cleanup()
                    except Exception:
                        pass
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
        entries = []  # (компонент, файл, ключ в словаре загрузок)
        for a in actions:
            comp = self.manifest.component(a.component)
            if a.kind == "files_install":
                entries += [(comp, f, f.path) for f in comp.files]
            elif a.kind in ("zip_install", "installer_run"):
                entries.append((comp, comp.archive, ARCHIVE_KEY))
            elif a.kind == "installer_remove" and not self._package_ready(comp):
                entries.append((comp, comp.archive, ARCHIVE_KEY))  # пакет удалили — нужен для деинсталляции
        total = sum(f.size for _, f, _ in entries)
        done, result, used = 0, {}, set()
        os.makedirs(self._dl_dir, exist_ok=True)
        self._prune_downloads()
        for comp, f, key in entries:
            base = done
            report = lambda n, p=f.path: self._progress(stage="download", done=base + n, total=total, text=p)
            if key != ARCHIVE_KEY and self._already_in_client(f):
                result[(comp.id, key)] = ADOPT
                report(f.size)
            else:
                src = self._fetch(f, report)
                if src in used:  # один и тот же файл нужен дважды — второй раз копией
                    copy = os.path.join(self._tmp, "dl", comp.id, hashlib.sha1(key.encode()).hexdigest())
                    os.makedirs(os.path.dirname(copy), exist_ok=True)
                    shutil.copyfile(src, copy)
                    src = copy
                used.add(src)
                result[(comp.id, key)] = src
            done += f.size
        return result

    def _already_in_client(self, entry):
        """В клиенте уже лежит ровно этот файл (например, игрок ставил пак сам) — не качаем."""
        if entry.mutable:
            return False
        path = gameutils.safe_join(self.game_dir, entry.path)
        return (bool(path) and os.path.isfile(path) and os.path.getsize(path) == entry.size
                and _sha256_file(path) == entry.sha256)

    def _prune_downloads(self):
        """Из кэша загрузок — всё, чего нет в текущем манифесте (старые версии)."""
        wanted = {f.sha256 for c in self.manifest.components for f in c.files}
        wanted |= {c.archive.sha256 for c in self.manifest.components if c.archive is not None}
        for name in os.listdir(self._dl_dir):
            if name.split(".", 1)[0] not in wanted:
                try:
                    os.remove(os.path.join(self._dl_dir, name))
                except OSError:
                    pass

    def _fetch(self, entry, on_bytes):
        """Скачать в кэш (докачивая оборванное) и вернуть путь к проверенному файлу."""
        final = os.path.join(self._dl_dir, entry.sha256)
        if os.path.isfile(final) and os.path.getsize(final) == entry.size:
            on_bytes(entry.size)
            return final
        part = final + ".part"
        errors = []
        for url in entry.urls:
            for _ in range(MAX_RESUMES):
                before = os.path.getsize(part) if os.path.isfile(part) else 0
                try:
                    self._fetch_once(url, entry, part, on_bytes)
                    os.replace(part, final)
                    return final
                except ApplyCancelled:
                    raise
                except _BadContent as e:  # не тот файл — с этого зеркала докачивать нечего
                    errors.append(f"{url}: {e}")
                    _remove_quietly(part)
                    break
                except Exception as e:
                    errors.append(f"{url}: {e}")
                    after = os.path.getsize(part) if os.path.isfile(part) else 0
                    if after <= before:
                        break  # без продвижения — следующее зеркало
        raise ApplyError(f"Не удалось скачать {entry.path} ({'; '.join(errors[-3:])})")

    def _fetch_once(self, url, entry, part, on_bytes):
        have = os.path.getsize(part) if os.path.isfile(part) else 0
        if have > entry.size:
            _remove_quietly(part)
            have = 0
        h = hashlib.sha256()
        if have == entry.size:
            h = _sha256_of(part)
        else:
            headers = {"Range": f"bytes={have}-"} if have else {}
            with self._session_obj().get(url, stream=True, timeout=(10, 60), headers=headers) as resp:
                if have and resp.status_code == 206:
                    h = _sha256_of(part)
                    mode = "ab"
                elif resp.status_code == 200:
                    have, mode = 0, "wb"  # сервер не умеет докачку — файл заново
                else:
                    raise ApplyError(f"HTTP {resp.status_code}")
                n = have
                on_bytes(n)
                with open(part, mode) as out:
                    for chunk in resp.iter_content(1 << 16):
                        self._check_cancel()
                        if not chunk:
                            continue
                        n += len(chunk)
                        if n > entry.size:
                            raise _BadContent("файл больше ожидаемого")
                        h.update(chunk)
                        out.write(chunk)
                        on_bytes(n)
            if n != entry.size:
                raise ConnectionError(f"загрузка оборвалась на {n} из {entry.size} байт")
        if h.hexdigest() != entry.sha256:
            raise _BadContent("контрольная сумма не совпала")

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
            if downloads[(comp.id, f.path)] is ADOPT:
                record[f.path] = f.sha256
                continue
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

    # ---- аддоны (zip) ----

    def _extract_addon_zip(self, zpath, comp, staged):
        """Распаковать только папки компонента и только файлы аддонов. Исполняемое, выход
        за пределы папки или слишком большой архив — отказ без изменений клиента."""
        import zipfile
        wanted = {f.lower(): f for f in comp.folders}
        found, total = set(), 0
        try:
            zf = zipfile.ZipFile(zpath)
        except zipfile.BadZipFile:
            raise ApplyError(f"{comp.name}: архив повреждён")
        with zf:
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                if name.endswith("/"):
                    continue
                parts = name.split("/")
                if (name.startswith("/") or ":" in name or any(p in ("", ".", "..") for p in parts)
                        or len(parts) < 2):
                    raise ApplyError(f"{comp.name}: недопустимый путь в архиве «{info.filename}»")
                ext = os.path.splitext(name)[1].lower()
                if ext in EXECUTABLE_EXT:
                    raise ApplyError(f"{comp.name}: в архиве исполняемый файл «{info.filename}»")
                folder = wanted.get(parts[0].lower())
                if folder is None or ext not in ADDON_FILE_EXT:
                    continue
                total += info.file_size
                if info.file_size > MAX_ARCHIVE_FILE or total > MAX_ARCHIVE_TOTAL:
                    raise ApplyError(f"{comp.name}: архив слишком большой")
                dst = os.path.join(staged, folder, *parts[1:])
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with zf.open(info) as src, open(dst, "wb") as out:
                    shutil.copyfileobj(src, out, 1 << 16)
                found.add(folder)
        missing = [f for f in comp.folders if f not in found]
        if missing:
            raise ApplyError(f"{comp.name}: в архиве нет папки «{missing[0]}»")

    def _do_zip_install(self, comp, downloads, journal):
        staged = os.path.join(self._tmp, "zip", comp.id)
        shutil.rmtree(staged, ignore_errors=True)
        self._extract_addon_zip(downloads[(comp.id, ARCHIVE_KEY)], comp, staged)
        root = self._target(comp.target)
        for folder in comp.folders:
            dst = os.path.join(root, folder)
            if os.path.lexists(dst):
                # Своя копия игрока (или старая версия) — не удаляем, откладываем в backup/kept.
                self._move(dst, self._kept_path(f"{comp.target}/{folder}"), journal)
            self._move(os.path.join(staged, folder), dst, journal)
        self.state["components"][comp.id] = {"version": comp.version, "folders": list(comp.folders)}
        journal.append(lambda: self.state["components"].pop(comp.id, None))
        self._after_success.append(lambda p=downloads[(comp.id, ARCHIVE_KEY)]: _remove_quietly(p))

    def _do_zip_remove(self, comp, downloads, journal):
        record = self.state["components"].get(comp.id) or {}
        root = gameutils.safe_join(self.game_dir, comp.target)
        for folder in record.get("folders") or comp.folders:
            if not root or not _FOLDER_RE.match(str(folder)):
                continue
            dst = os.path.join(root, folder)
            if os.path.lexists(dst):
                self._move(dst, os.path.join(self._tmp, "undo", comp.id, folder), journal)
        old = self.state["components"].pop(comp.id, None)
        journal.append(lambda: self.state["components"].__setitem__(comp.id, old))

    # ---- пакеты со своим установщиком (installer) ----

    def _package_dir(self, comp):
        return os.path.join(self._installers_dir, comp.id, comp.version or "0")

    def _package_ready(self, comp):
        record = self.state["components"].get(comp.id) or {}
        pkg = record.get("package_dir") or self._package_dir(comp)
        uninstall = record.get("uninstall") or list(comp.uninstall)
        exe = gameutils.safe_join(pkg, uninstall[0]) if uninstall else None
        return bool(exe) and os.path.isfile(exe)

    def _extract_package(self, comp, zpath, pkg):
        import zipfile
        shutil.rmtree(pkg, ignore_errors=True)
        try:
            with zipfile.ZipFile(zpath) as zf:
                for info in zf.infolist():
                    name = info.filename.replace("\\", "/")
                    if name.endswith("/"):
                        continue
                    dst = gameutils.safe_join(pkg, name)
                    if not dst:
                        raise ApplyError(f"{comp.name}: недопустимый путь в пакете «{info.filename}»")
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with zf.open(info) as src, open(dst, "wb") as out:
                        shutil.copyfileobj(src, out, 1 << 20)
        except zipfile.BadZipFile:
            raise ApplyError(f"{comp.name}: пакет повреждён")

    def _locale(self):
        cfg = {k.lower(): v for k, v in gameutils.read_config_wtf(self.game_dir).items()}
        loc = cfg.get("locale", "")
        return loc if re.match(r"^[a-z]{2}[A-Z]{2}$", loc) else "ruRU"

    def _argv(self, comp, template, pkg):
        exe = gameutils.safe_join(pkg, template[0])
        if not exe or not os.path.isfile(exe):
            raise ApplyError(f"{comp.name}: в пакете нет «{template[0]}»")
        subst = {"{client}": os.path.abspath(self.game_dir), "{locale}": self._locale()}
        return [exe] + [subst.get(a, a) for a in template[1:]]

    def _run_installer(self, comp, argv, pkg, what):
        pattern = re.compile(comp.progress) if comp.progress else None
        tail = []

        def on_line(line):
            line = line.rstrip()
            if not line:
                return
            tail.append(line)
            del tail[:-6]
            m = pattern.search(line) if pattern else None
            if m and "pct" in m.groupdict():
                self._progress(stage="install", done=int(m.group("pct")), total=100, text=f"{comp.name}: {line.strip()}")

        self._progress(stage="install", done=0, total=100, text=f"{comp.name}: {what}")
        rc = _run_process(argv, pkg, on_line)
        if rc != 0:
            detail = next((l for l in reversed(tail) if "error" in l.lower()), tail[-1] if tail else "")
            raise ApplyError(f"{comp.name}: {what} не удалась (код {rc}). {detail.strip()}")

    def _do_installer_run(self, comp, downloads, journal):
        pkg = self._package_dir(comp)
        self._extract_package(comp, downloads[(comp.id, ARCHIVE_KEY)], pkg)
        self._run_installer(comp, self._argv(comp, comp.install, pkg), pkg, "установка")
        uninstall = self._argv(comp, comp.uninstall, pkg)
        journal.append(lambda: _run_process(uninstall, pkg, lambda line: None))
        self.state["components"][comp.id] = {"version": comp.version, "package_dir": pkg,
                                             "uninstall": list(comp.uninstall)}
        journal.append(lambda: self.state["components"].pop(comp.id, None))
        self._after_success.append(lambda p=downloads[(comp.id, ARCHIVE_KEY)]: _remove_quietly(p))

    def _do_installer_remove(self, comp, downloads, journal):
        record = self.state["components"].get(comp.id) or {}
        pkg = record.get("package_dir") or self._package_dir(comp)
        template = record.get("uninstall") or list(comp.uninstall)
        if not self._package_ready(comp):
            pkg = self._package_dir(comp)
            self._extract_package(comp, downloads[(comp.id, ARCHIVE_KEY)], pkg)
            template = list(comp.uninstall)
        self._run_installer(comp, self._argv(comp, template, pkg), pkg, "удаление")
        install = self._argv(comp, comp.install, pkg) if comp.install else None
        if install:
            journal.append(lambda: _run_process(install, pkg, lambda line: None))
        old = self.state["components"].pop(comp.id, None)
        journal.append(lambda: self.state["components"].__setitem__(comp.id, old))
        self._after_success.append(lambda: shutil.rmtree(pkg, ignore_errors=True))


def _run_process(argv, cwd, on_line):
    """Запустить установщик пакета без окна, отдавая его вывод построчно. Код возврата."""
    import subprocess
    proc = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, creationflags=gameutils.NO_WINDOW,
                            encoding="utf-8", errors="replace")
    gameutils.kill_on_close(proc)  # закрыли лаунчер — установщик не остаётся висеть
    for line in proc.stdout:
        on_line(line)
    return proc.wait()
