"""Аддоны, которые игрок поставил сам — не из каталога лаунчера и не серверные.

Список с проверкой того, что заметит игра (не та версия клиента, папка названа не как .toc),
и включение/выключение: выключенный аддон переезжает в <игра>/PLGames/addons-off и возвращается
обратно целиком. Настройки аддонов (WTF/…/SavedVariables) при этом не трогаются."""

import os
import re

ADDONS_REL = os.path.join("Interface", "AddOns")
OFF_REL = os.path.join("PLGames", "addons-off")
_FOLDER_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\- ]{0,63}$")
_COLOR_RE = re.compile(r"\|c[0-9A-Fa-f]{8}|\|r")
# Части раздачи клиента, а не выбор игрока: WDM (WoW Dungeon Maps) дописывает строки интерфейса для
# MPQ «Карты подземелий» — выключенный, он ломает эти карты. Как и Blizzard_*, в список не попадают.
CLIENT_FOLDERS = frozenset({"wdm"})


def read_toc(path, limit=8192):
    """Поля «## Ключ: значение» из начала .toc; None, если файла нет."""
    try:
        with open(path, "rb") as f:
            raw = f.read(limit)
    except OSError:
        return None
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1251", errors="replace")
    fields = {}
    for line in text.splitlines():
        if line.startswith("##"):
            key, sep, value = line[2:].partition(":")
            if sep:
                fields.setdefault(key.strip(), value.strip())
    return fields


def clean_title(title):
    """Название без цветовых кодов WoW (|cffRRGGBB…|r)."""
    return _COLOR_RE.sub("", title or "").strip()


def _has_files(path):
    for _, _, files in os.walk(path):
        if files:
            return True
    return False


def _info(path, folder):
    fields = read_toc(os.path.join(path, folder + ".toc"))
    loads = fields is not None  # клиент 3.3.5a грузит только <Папка>/<Папка>.toc
    if fields is None:
        tocs = sorted(n for n in os.listdir(path) if n.lower().endswith(".toc"))
        fields = (read_toc(os.path.join(path, tocs[0])) if tocs else None) or {}
    try:
        interface = int(fields.get("Interface", ""))
    except ValueError:
        interface = None
    deps = []
    for key, value in fields.items():
        if key.lower() in ("dependencies", "requireddeps") or key.lower().startswith("dep"):
            deps += [d.strip() for d in value.split(",") if d.strip()]
    return {"title": clean_title(fields.get("Title-ruRU") or fields.get("Title")) or folder,
            "version": fields.get("Version", "")[:40], "notes": clean_title(fields.get("Notes-ruRU")
                                                                           or fields.get("Notes", ""))[:200],
            "interface": interface, "compatible": None if interface is None else 30000 <= interface < 40000,
            "loads": loads, "deps": deps}


def scan(game_dir, owned, server):
    """Свои аддоны игрока группами: модули, зависящие от другого его аддона, входят в группу
    этого аддона. owned — папки аддонов каталога, server — папки серверных аддонов (в нижнем регистре)."""
    skip = {f.lower() for f in owned} | {f.lower() for f in server}
    entries = {}
    for rel, enabled in ((ADDONS_REL, True), (OFF_REL, False)):
        root = os.path.join(game_dir, rel)
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for name in names:
            low = name.lower()
            path = os.path.join(root, name)
            if (low in skip or low in CLIENT_FOLDERS or low.startswith("blizzard_") or not _FOLDER_RE.match(name)
                    or name in entries or not os.path.isdir(path) or not _has_files(path)):
                continue  # пустые папки (бывают в раздачах клиента) — не аддоны
            entries[name] = dict(_info(os.path.join(root, name), name), enabled=enabled)
    by_low = {n.lower(): n for n in entries}

    def root_of(name):
        seen = set()
        while name not in seen:
            seen.add(name)
            parent = next((by_low[d.lower()] for d in entries[name]["deps"]
                           if d.lower() in by_low and by_low[d.lower()] != name), None)
            if parent is None:
                return name
            name = parent
        return name

    groups = {}
    for name in entries:
        groups.setdefault(root_of(name), []).append(name)
    out = []
    for root, members in groups.items():
        info = entries[root]
        out.append({"folder": root, "title": info["title"], "version": info["version"], "notes": info["notes"],
                    "interface": info["interface"], "compatible": info["compatible"], "loads": info["loads"],
                    "enabled": info["enabled"],
                    "folders": [root] + sorted((m for m in members if m != root), key=str.lower)})
    return sorted(out, key=lambda a: a["title"].lower())


def set_enabled(game_dir, folder, enabled, owned, server):
    """Включить/выключить свой аддон игрока вместе с его модулями. (ok, сообщение)."""
    group = next((g for g in scan(game_dir, owned, server) if g["folder"] == folder), None)
    if group is None:
        return False, "Такого аддона нет среди установленных вами"
    src_root = os.path.join(game_dir, OFF_REL if enabled else ADDONS_REL)
    dst_root = os.path.join(game_dir, ADDONS_REL if enabled else OFF_REL)
    moves = [(os.path.join(src_root, f), os.path.join(dst_root, f)) for f in group["folders"]
             if os.path.isdir(os.path.join(src_root, f))]
    for _, dst in moves:
        if os.path.exists(dst):
            return False, f"Папка «{os.path.basename(dst)}» уже есть в {dst_root} — уберите одну из копий"
    try:
        os.makedirs(dst_root, exist_ok=True)
        for src, dst in moves:
            os.rename(src, dst)
    except OSError as e:
        return False, f"Не удалось перенести папку аддона: {e}"
    return True, ""
