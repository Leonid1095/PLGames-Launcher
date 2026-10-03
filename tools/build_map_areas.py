"""Таблица зон карты мира для аддона PLGames_Events.

Сервер присылает метку в координатах мира (карта, x, y) и id зоны. Чтобы поставить её на карту,
аддону нужны границы каждой зоны на карте мира — они лежат в DBFilesClient\\WorldMapArea.dbc клиента.
Скрипт берёт этот файл из самого старшего локального архива и пишет Lua-таблицу
addons/PLGames_Events/MapAreas.lua.

Запуск (из папки launcher/, нужен tools/bin/StormLib.dll):
    python tools/build_map_areas.py --client D:\\Games\\PLGames_Wow3.3.5
"""

import argparse
import os
import struct
import sys

DBC_NAME = "DBFilesClient\\WorldMapArea.dbc"
# от старшего к младшему: первый архив, где есть файл, и есть версия, которую видит игра
LOCALE_ARCHIVES = ("patch-{l}-3.MPQ", "patch-{l}-2.MPQ", "patch-{l}.MPQ", "lichking-locale-{l}.MPQ",
                   "expansion-locale-{l}.MPQ", "locale-{l}.MPQ")
OUT = os.path.join("addons", "PLGames_Events", "MapAreas.lua")


def parse_world_map_area(raw):
    """Записи WorldMapArea.dbc 3.3.5a: [(id, map, area, left, right, top, bottom)]."""
    magic, count, fields, rsize, _ = struct.unpack_from("<4s4I", raw, 0)
    if magic != b"WDBC" or fields != 11 or rsize != 44:
        raise ValueError(f"неожиданный формат WorldMapArea.dbc: {magic!r} {fields} полей по {rsize} байт")
    rows = []
    for i in range(count):
        rid, map_id, area, _name, left, right, top, bottom = struct.unpack_from("<4I4f", raw, 20 + i * rsize)
        rows.append((rid, map_id, area, left, right, top, bottom))
    return rows


def render_lua(rows):
    def num(v):
        return f"{v:.3f}".rstrip("0").rstrip(".")
    lines = ["-- Сгенерировано tools/build_map_areas.py из DBFilesClient\\WorldMapArea.dbc клиента 3.3.5a.",
             "-- Не править руками: перегенерировать скриптом.",
             "-- [WorldMapArea.ID] = { карта, зона (AreaTable; 0 — континент), лево, право, верх, низ }",
             "PLGamesEventsMapAreas = {"]
    for rid, map_id, area, left, right, top, bottom in sorted(rows):
        if left == right or top == bottom:
            continue  # у записи нет границ — на ней метку не поставить
        lines.append(f"  [{rid}] = {{{map_id}, {area}, {num(left)}, {num(right)}, {num(top)}, {num(bottom)}}},")
    lines.append("}")
    return "\r\n".join(lines) + "\r\n"


def read_dbc(client, locale="ruRU"):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import stormlib
    for pattern in LOCALE_ARCHIVES:
        path = os.path.join(client, "Data", locale, pattern.format(l=locale))
        if not os.path.isfile(path):
            continue
        with stormlib.Archive(path) as a:
            if a.has(DBC_NAME):
                return a.read(DBC_NAME), path
    raise SystemExit(f"{DBC_NAME} не найден в локальных архивах клиента")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Таблица зон карты мира для PLGames_Events")
    ap.add_argument("--client", required=True)
    ap.add_argument("--locale", default="ruRU")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args(argv)
    raw, source = read_dbc(args.client, args.locale)
    rows = parse_world_map_area(raw)
    text = render_lua(rows)
    with open(args.out, "wb") as f:
        f.write(text.encode("utf-8"))
    print(f"{len(rows)} записей из {source} -> {args.out}")


if __name__ == "__main__":
    main()
