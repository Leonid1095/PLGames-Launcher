"""Сборка манифеста графических изданий для публикации.

Вход:  content/manifest.src.json — тот же формат, что и манифест, но у файлов
       files-компонентов вместо size/sha256/urls указан "src" (путь относительно
       папки с manifest.src.json).
Выход: <out>/server/  manifest.json + <компонент>/<версия>/<путь>
                      → залить в https://plgames-wow.ru/launcher/content/
       <out>/github/  manifest.json + <компонент>-<версия>-<путь с __ вместо />
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
import content  # noqa: E402

SERVER_BASE = "https://plgames-wow.ru/launcher/content/"
GITHUB_BASE = "https://github.com/Leonid1095/PLGames-Launcher/releases/download/content-latest/"


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def asset_name(cid, version, rel):
    """Имя ассета GitHub Release: плоское, без слешей."""
    return f"{cid}-{version}-{rel.replace('/', '__')}"


def build(src_path, out_dir, server_base=SERVER_BASE, github_base=GITHUB_BASE):
    with open(src_path, encoding="utf-8") as f:
        manifest = copy.deepcopy(json.load(f))
    root = os.path.dirname(os.path.abspath(src_path))
    server_dir, github_dir = os.path.join(out_dir, "server"), os.path.join(out_dir, "github")
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(server_dir)
    os.makedirs(github_dir)

    for comp in manifest.get("components", []):
        if comp.get("type") != "files":
            continue
        cid, version = comp["id"], str(comp.get("version") or "0")
        comp["version"] = version
        for entry in comp.get("files", []):
            local = os.path.join(root, entry.pop("src"))
            rel = entry["path"].replace("\\", "/")
            server_rel = f"{cid}/{version}/{rel}"
            asset = asset_name(cid, version, rel)
            dst = os.path.join(server_dir, *server_rel.split("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(local, dst)
            shutil.copyfile(local, os.path.join(github_dir, asset))
            entry["size"] = os.path.getsize(local)
            entry["sha256"] = _sha256(local)
            entry["urls"] = [server_base + quote(server_rel), github_base + quote(asset)]

    content.parse_manifest(manifest)
    for layout_dir in (server_dir, github_dir):
        with open(os.path.join(layout_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
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
