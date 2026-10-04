"""Сборка манифеста графических изданий для публикации.

Вход:  content/manifest.src.json — тот же формат, что и манифест, но у файлов
       files-компонентов вместо size/sha256/urls указан "src" (путь относительно
       папки с manifest.src.json).
Выход: <out>/server/  manifest2.json + <компонент>/<версия>/<путь>
                      → залить в https://plgames-wow.ru/launcher/content/
       <out>/github/  manifest2.json + <компонент>-<версия>-<путь с __ вместо />
                      → ассеты GitHub Release «content-latest» в PLGames-Launcher

Результат проверяется тем же parse_manifest, что и в лаунчере: манифест, который
лаунчер отвергнет, не публикуется.

Запуск (из папки launcher/):
    python tools/build_content_manifest.py [--src content/manifest.src.json] [--out dist-content]
"""

import argparse
import copy
import hashlib
import json
import os
import shutil
import sys
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import clientrepair  # noqa: E402
import content  # noqa: E402

SERVER_BASE = "https://plgames-wow.ru/launcher/content/"
# Схема 2 публикуется отдельным файлом: лаунчеры 0.4.x читают manifest.json и не знают новых типов.
MANIFEST_NAME = "manifest2.json"
GITHUB_BASE = "https://github.com/Leonid1095/PLGames-Launcher/releases/download/content-latest/"


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _link_or_copy(src, dst):
    """Жёсткая ссылка (гигабайтные паки не копируются дважды), иначе копия."""
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


def asset_name(cid, version, rel):
    """Имя ассета GitHub Release: плоское, без слешей."""
    return f"{cid}-{version}-{rel.replace('/', '__')}"


def build(src_path, out_dir, server_base=SERVER_BASE, github_base=GITHUB_BASE, external_placeholders=False):
    """external_placeholders=True — для проверки структуры (тесты, CI): файлы вне папки манифеста
    (гигабайтные паки из dist-forever/) не читаются, вместо размера и хеша — заглушки."""
    with open(src_path, encoding="utf-8") as f:
        manifest = copy.deepcopy(json.load(f))
    root = os.path.dirname(os.path.abspath(src_path))
    server_dir, github_dir = os.path.join(out_dir, "server"), os.path.join(out_dir, "github")
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(server_dir)
    os.makedirs(github_dir)

    def publish(entry, local, cid, version, rel):
        if external_placeholders and not os.path.abspath(local).startswith(root + os.sep):
            entry.update(size=0, sha256="0" * 64, urls=[server_base + quote(f"{cid}/{version}/{rel}")])
            return
        server_rel = f"{cid}/{version}/{rel}"
        asset = asset_name(cid, version, rel)
        dst = os.path.join(server_dir, *server_rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        _link_or_copy(local, dst)
        _link_or_copy(local, os.path.join(github_dir, asset))
        entry["size"] = os.path.getsize(local)
        entry["sha256"] = _sha256(local)
        entry["urls"] = [server_base + quote(server_rel), github_base + quote(asset)]

    for comp in manifest.get("components", []):
        ctype = comp.get("type")
        if ctype not in ("files", "zip", "installer"):
            continue
        cid, version = comp["id"], str(comp.get("version") or "0")
        comp["version"] = version
        if ctype == "files":
            for entry in comp.get("files", []):
                publish(entry, os.path.join(root, entry.pop("src")), cid, version, entry["path"].replace("\\", "/"))
        else:
            archive = comp["archive"]
            local = os.path.join(root, archive.pop("src"))
            publish(archive, local, cid, version, os.path.basename(local))

    content.parse_manifest(manifest)
    for layout_dir in (server_dir, github_dir):
        with open(os.path.join(layout_dir, MANIFEST_NAME), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    # Индекс архива клиента (tools/build_client_index.py) публикуется рядом с манифестом
    index_src = os.path.join(root, clientrepair.INDEX_NAME)
    if os.path.isfile(index_src):
        with open(index_src, encoding="utf-8") as f:
            clientrepair.parse_index(json.load(f))
        for layout_dir in (server_dir, github_dir):
            shutil.copyfile(index_src, os.path.join(layout_dir, clientrepair.INDEX_NAME))
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description="Сборка манифеста графических изданий для публикации")
    ap.add_argument("--src", default=os.path.join("content", "manifest.src.json"))
    ap.add_argument("--out", default="dist-content")
    args = ap.parse_args(argv)
    manifest = build(args.src, args.out)
    files = sum(len(c.get("files", [])) for c in manifest["components"] if c.get("type") == "files")
    print(f"content_version {manifest.get('content_version')}: {len(manifest['components'])} компонентов, "
          f"{len(manifest['editions'])} изданий, {files} файлов для загрузки")
    print(f"  сервер: {os.path.join(args.out, 'server')}  ->  {SERVER_BASE}")
    print(f"  GitHub: {os.path.join(args.out, 'github')}  ->  Release «content-latest»")


if __name__ == "__main__":
    main()
