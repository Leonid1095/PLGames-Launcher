"""Зеркало контента изданий на нашем сервере: скачать с GitHub (пререлиз content-latest) манифесты,
индекс клиента и все файлы изданий и разложить по путям, которые ждёт лаунчер на сервере
(https://plgames-wow.ru/launcher/content/<компонент>/<версия>/<файл>). Каждый файл сверяется по SHA-256;
то, что уже лежит и совпадает, не качается.

Запуск на сервере (нужен только Python 3 и requests):
    python3 mirror_content.py /home/plgames/launcher-files/content
"""

import argparse
import hashlib
import json
import os
import sys

GITHUB = "https://github.com/Leonid1095/PLGames-Launcher/releases/download/content-latest/"
SERVER_BASE = "https://plgames-wow.ru/launcher/content/"
MANIFESTS = ("manifest2.json", "manifest.json")
EXTRA = ("client-index.json",)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_rel(rel):
    parts = rel.split("/")
    if not rel or rel.startswith("/") or any(p in ("", ".", "..") for p in parts) or ":" in rel:
        raise ValueError(f"недопустимый путь «{rel}»")
    return os.path.join(*parts)


def entries(manifest):
    """(путь на сервере, ссылка GitHub, размер, sha256) для всех скачиваемых файлов манифеста."""
    out = []
    for comp in manifest.get("components", []):
        files = list(comp.get("files", [])) if comp.get("type") == "files" else []
        if comp.get("type") in ("zip", "installer"):
            files.append(comp["archive"])
        for f in files:
            urls = f.get("urls", [])
            server = next((u for u in urls if u.startswith(SERVER_BASE)), None)
            github = next((u for u in urls if u.startswith(GITHUB)), None)
            if server and github:
                out.append((_safe_rel(server[len(SERVER_BASE):]), github, f["size"], f["sha256"]))
    return out


def _download(session, url, dst, size=None, sha=None):
    tmp = dst + ".part"
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    with session.get(url, stream=True, timeout=60) as r:
        if r.status_code != 200:
            raise RuntimeError(f"{url}: HTTP {r.status_code}")
        with open(tmp, "wb") as out:
            for chunk in r.iter_content(1 << 20):
                out.write(chunk)
    if size is not None and os.path.getsize(tmp) != size or sha is not None and _sha256(tmp) != sha:
        os.remove(tmp)
        raise RuntimeError(f"{url}: файл не совпал с манифестом")
    os.replace(tmp, dst)


def mirror(dest, session, log=print):
    fetched = skipped = 0
    for name in MANIFESTS + EXTRA:
        _download(session, GITHUB + name, os.path.join(dest, name + ".new"))
    for name in MANIFESTS:
        with open(os.path.join(dest, name + ".new"), encoding="utf-8") as f:
            manifest = json.load(f)
        for rel, url, size, sha in entries(manifest):
            dst = os.path.join(dest, rel)
            if os.path.isfile(dst) and os.path.getsize(dst) == size and _sha256(dst) == sha:
                skipped += 1
                continue
            log(f"  {rel} ({size / 2 ** 20:.0f} МБ)")
            _download(session, url, dst, size, sha)
            fetched += 1
    # манифесты — последними: лаунчер не увидит ссылок на ещё не скачанные файлы
    for name in MANIFESTS + EXTRA:
        os.replace(os.path.join(dest, name + ".new"), os.path.join(dest, name))
    log(f"готово: скачано {fetched}, уже было {skipped}")
    return fetched, skipped


def main(argv=None):
    ap = argparse.ArgumentParser(description="Зеркало контента изданий с GitHub на сервер")
    ap.add_argument("dest", help="папка, которую nginx отдаёт как /launcher/content/")
    args = ap.parse_args(argv)
    import requests
    mirror(args.dest, requests.Session())


if __name__ == "__main__":
    sys.exit(main())
