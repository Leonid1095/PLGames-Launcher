"""Сборка каталога аддонов для лаунчера.

Вход:  content/addons.catalog.json — проверенный список аддонов 3.3.5a (источник, версия, правила
       упаковки: strip_prefix / rename_root_to / exclude_paths / addon_folders) и папка с исходными
       zip-архивами (имя <slug>.zip, SHA-256 сверяется с каталогом).
Выход: <out>/<slug>-<версия>.zip — нормализованные архивы: в корне сразу папки аддонов, только файлы
       аддонов, одинаковые даты — архив собирается байт-в-байт одинаково;
       компоненты scope=addon в content/manifest.src.json (старые аддоны заменяются).

Запуск (из папки launcher/):
    python tools/build_addon_packs.py --raw <папка с исходными zip> [--out dist-forever/addons]
"""

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import content  # noqa: E402

GROUPS = {"quests": "Квесты и карта", "raids": "Рейды и бои", "convenience": "Удобство", "interface": "Интерфейс"}
DEFAULT_ON = {"questie", "dbm"}  # нужны большинству игроков сервера; остальное игрок включает сам
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def clean_version(version):
    token = str(version).split()[0] if str(version).split() else "0"
    return re.sub(r"[^A-Za-z0-9._-]+", "-", token).strip("-")[:40] or "0"


def addon_members(package, names):
    """(имя в исходном архиве, путь в нашем архиве) по правилам каталога."""
    strip, rename = package.get("strip_prefix") or "", package.get("rename_root_to")
    excl = tuple(package.get("exclude_paths") or ())
    folders = set(package["addon_folders"])
    for name in names:
        if name.endswith("/") or not name.startswith(strip):
            continue
        rel = name[len(strip):]
        if rename:
            if rel.startswith(excl):
                continue
            rel = rename + "/" + rel
        parts = rel.split("/")
        if parts[0] not in folders or len(parts) < 2 or any(p in ("", ".", "..") for p in parts):
            continue
        if rel.split("/", 1)[-1].startswith(excl) if excl else False:
            continue
        if os.path.splitext(rel)[1].lower() not in content.ADDON_FILE_EXT:
            continue
        yield name, rel


def pack(entry, raw_zip, out_dir):
    package = entry["package"]
    data = open(raw_zip, "rb").read()
    if hashlib.sha256(data).hexdigest() != package["sha256"]:
        raise SystemExit(f"{entry['slug']}: SHA-256 исходного архива не совпадает с каталогом")
    version = clean_version(entry["version"])
    out = os.path.join(out_dir, f"{entry['slug']}-{version}.zip")
    with zipfile.ZipFile(raw_zip) as src:
        members = sorted(addon_members(package, src.namelist()), key=lambda x: x[1])
        found = {rel.split("/")[0] for _, rel in members}
        missing = set(package["addon_folders"]) - found
        if missing:
            raise SystemExit(f"{entry['slug']}: нет папок {sorted(missing)}")
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as dst:
            for name, rel in members:
                info = zipfile.ZipInfo(rel, FIXED_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                dst.writestr(info, src.read(name))
    return out, version, len(members)


def license_label(raw):
    """Короткая подпись лицензии для карточки: SPDX как есть, остальное — по-русски."""
    lic = re.split(r"\s*[(;]", raw or "")[0].strip()
    low = lic.lower()
    if not lic or low.startswith("none"):
        return "лицензия не указана"
    if low.startswith("all rights reserved"):
        return "все права у автора"
    if low.startswith(("custom", "licenseref-")):
        return "своя лицензия автора"
    return lic[:60]


def component(entry, version, zip_rel):
    desc = entry.get("description_ru", "")
    if entry.get("is_alternative"):
        desc += " Делает то же, что Details!, — включайте что-то одно."
    if entry["slug"] == "elvui":
        desc += " Заменяет панели, сумки и рамки — с Bartender4, Bagnon и Titan Panel не совмещайте."
    authors = re.split(r"\s*[(;]", entry.get("authors", ""))[0][:120]
    lic = license_label(entry.get("license", ""))
    return {"id": "addon_" + re.sub(r"[^a-z0-9_]", "_", entry["slug"].lower()), "name": entry["name"],
            "group": GROUPS.get(entry["group"], "Прочее"), "type": "zip", "version": version, "scope": "addon",
            "default": entry["slug"] in DEFAULT_ON, "description": desc[:400], "author": authors, "license": lic,
            "archive": {"src": zip_rel}, "target": "Interface/AddOns",
            "folders": list(entry["package"]["addon_folders"])}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Сборка каталога аддонов")
    ap.add_argument("--catalog", default=os.path.join("content", "addons.catalog.json"))
    ap.add_argument("--raw", required=True, help="папка с исходными <slug>.zip")
    ap.add_argument("--out", default=os.path.join("dist-forever", "addons"))
    ap.add_argument("--manifest", default=os.path.join("content", "manifest.src.json"))
    args = ap.parse_args(argv)
    catalog = json.load(open(args.catalog, encoding="utf-8"))
    os.makedirs(args.out, exist_ok=True)
    manifest_dir = os.path.dirname(os.path.abspath(args.manifest))
    comps = []
    for entry in catalog:
        out, version, n = pack(entry, os.path.join(args.raw, f"{entry['slug']}.zip"), args.out)
        rel = os.path.relpath(os.path.abspath(out), manifest_dir).replace(os.sep, "/")
        comps.append(component(entry, version, rel))
        print(f"{entry['slug']:12} {version:16} {n:5} файлов  {os.path.getsize(out) / 1024 ** 2:7.2f} МБ")
    raw = open(args.manifest, "rb").read().decode("utf-8")
    m = json.loads(raw)
    m["components"] = [c for c in m["components"] if c.get("scope") != "addon"] + comps
    text = json.dumps(m, ensure_ascii=False, indent=2)
    if "\r\n" in raw:
        text = text.replace("\n", "\r\n")
    open(args.manifest, "wb").write(text.encode("utf-8"))
    print(f"{len(comps)} аддонов в {args.manifest}; по умолчанию: {', '.join(sorted(DEFAULT_ON))}")


if __name__ == "__main__":
    main()
