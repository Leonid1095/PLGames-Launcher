"""Проверка контента изданий ДО публикации: применяет издание к клиенту прямо из
локальной сборки dist-content (tools/build_content_manifest.py), без сервера.

Работает тем же кодом, что и лаунчер (content.plan + content.Executor): хеши,
резервные копии чужих файлов, откат при ошибке, отказ при запущенной игре,
запись PLGames/state.json. Вернуть как было — та же команда с другим изданием.

Запуск (из папки launcher/, игра закрыта):
    python tools/build_content_manifest.py
    python tools/try_content.py "D:\\Games\\PLGames_Wow3.3.5" forever
    python tools/try_content.py "D:\\Games\\PLGames_Wow3.3.5" remaster
"""

import argparse
import json
import os
import sys
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import content  # noqa: E402
from build_content_manifest import MANIFEST_NAME, SERVER_BASE  # noqa: E402


def _say(text):
    """print, который не падает на консоли без кириллицы (cp1252 в CI)."""
    try:
        print(text)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "ascii"
        print(text.encode(enc, "replace").decode(enc))


class _LocalResponse:
    def __init__(self, path):
        self.status_code = 200
        self._path = path

    def iter_content(self, chunk):
        with open(self._path, "rb") as f:
            for block in iter(lambda: f.read(chunk), b""):
                yield block

    def json(self):
        with open(self._path, encoding="utf-8") as f:
            return json.load(f)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class LocalSession:
    """Отдаёт URL сервера из локальной папки dist-content/server."""

    def __init__(self, server_dir, base_url=SERVER_BASE):
        self._dir = os.path.abspath(server_dir)
        self._base = base_url

    def get(self, url, **kw):
        if not url.startswith(self._base):
            raise ConnectionError(f"не локальный URL: {url}")
        path = os.path.abspath(os.path.join(self._dir, *unquote(url[len(self._base):]).split("/")))
        if os.path.commonpath([self._dir, path]) != self._dir or not os.path.isfile(path):
            raise ConnectionError(f"нет в локальной сборке: {url}")
        return _LocalResponse(path)


def apply(game_dir, dist_dir, edition=None, components=None, is_running=None, addons=None, progress=None):
    server_dir = os.path.join(dist_dir, "server")
    with open(os.path.join(server_dir, MANIFEST_NAME), encoding="utf-8") as f:
        manifest = content.parse_manifest(json.load(f))
    scope = "edition"
    if addons is not None:
        target, label, scope = set(addons), None, "addon"
    elif edition is not None:
        ed = next((e for e in manifest.editions if e.id == edition), None)
        if ed is None:
            raise SystemExit(f"Нет издания «{edition}». Есть: {', '.join(e.id for e in manifest.editions)}")
        target, label = set(ed.components), ed.id
    else:
        target, label = set(components or ()), "custom"
    state = content.load_state(game_dir)
    status = content.component_status(manifest, game_dir, state)
    actions = content.plan(manifest, status, state, target, scope=scope)
    for a in actions:
        _say(f"  {a.kind:14} {manifest.component(a.component).name}")
    return content.Executor(manifest, game_dir, state, session=LocalSession(server_dir),
                            is_running=is_running, progress=progress).run(actions, edition=label)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Применить издание к клиенту из локальной сборки dist-content")
    ap.add_argument("game_dir")
    ap.add_argument("edition", nargs="?", help="classic / remaster / forever")
    ap.add_argument("--components", help="«Своё»: id компонентов через запятую")
    ap.add_argument("--addons", help="набор аддонов: id через запятую (пусто — снять все)")
    ap.add_argument("--dist", default="dist-content")
    args = ap.parse_args(argv)
    if not args.edition and args.components is None and args.addons is None:
        ap.error("укажите издание, --components или --addons")
    comps = [c for c in (args.components or "").split(",") if c]
    try:
        last = {}

        def progress(stage, done, total, text):
            if stage == "install" and text != last.get("t"):
                last["t"] = text
                _say(f"    {text}")

        addons = [a for a in args.addons.split(",") if a] if args.addons is not None else None
        state = apply(args.game_dir, args.dist, edition=args.edition, components=comps if not args.edition else None,
                      addons=addons, progress=progress)
    except (content.ApplyError, content.PlanError, content.ManifestError) as e:
        raise SystemExit(f"Ошибка: {e}")
    _say(f"Готово: издание «{state['edition']}», компоненты с файлами: {', '.join(state['components']) or 'нет'}")


if __name__ == "__main__":
    main()
