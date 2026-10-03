"""Сборка MPQ издания «Forever» из паков Project Reforged и HD-неба Sectym.

Что делает:
- перепаковывает Reforged B / D / E / P в свои MPQ по ≤1,8 ГБ (GitHub не принимает файлы > 2 ГиБ);
- выбрасывает тайлы рельефа (.adt) и служебные файлы из D: рельеф клиента должен совпадать с
  картами сервера, иначе высоты и коллизии разойдутся;
- выбрасывает аддон ObjectFade из E: аддоны из MPQ клиент 3.3.5a не грузит;
- сводит SpellVisualKitModelAttach.dbc пака P с версией нашего HD-пака персонажей (patch-ruRU-A),
  который загружается позже и иначе перекрыл бы новые эффекты заклинаний;
- кладёт рядом HD-небо Sectym как есть.

Буквы выбраны так, чтобы порядок Reforged сохранился (B < D < E < P) и не задеть буквы клиента.

Запуск (нужен tools/bin/StormLib.dll, x64):
    python tools/build_forever_packs.py --reforged D:\\Games\\_reforged --sky <Patch-ruRU-X.mpq>
        --client D:\\Games\\PLGames_Wow3.3.5 --out dist-forever
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import time
from concurrent.futures import ProcessPoolExecutor

BS = "\\"
PART_LIMIT = int(1.8 * 1024 ** 3)

# пак Reforged -> буквы наших частей (Data/patch-<буква>.MPQ), по порядку
PACKS = {
    "B": ["A", "B"],
    "D": ["C", "D", "E"],
    "E": ["F", "G"],
    "P": ["I"],
}
MERGED_DBC_MPQ = "Data/ruRU/patch-ruRU-Y.MPQ"
SKY_MPQ = "Data/ruRU/Patch-ruRU-X.mpq"
ATTACH_DBC = "DBFilesClient" + BS + "SpellVisualKitModelAttach.dbc"
DROP_EXT = {"D": {".adt", ".json", ".mtl", ".png"}}
DROP_PREFIX = {"E": ("interface" + BS + "addons" + BS,)}
WMO_GROUP_RE = re.compile(r"_\d{3}\.wmo$", re.IGNORECASE)


def select_names(pack, names):
    """Имена, которые идут в наши части, без дублей (регистр в MPQ не важен), по алфавиту."""
    drop_ext = DROP_EXT.get(pack, set())
    drop_prefix = DROP_PREFIX.get(pack, ())
    seen, out = set(), []
    for name in names:
        key = name.replace("/", BS).lower()
        if key in seen or key.startswith("(") or os.path.splitext(key)[1] in drop_ext:
            continue
        if any(key.startswith(p) for p in drop_prefix):
            continue
        if pack == "P" and key == ATTACH_DBC.lower():
            continue  # сведённая версия уходит в отдельный MPQ
        seen.add(key)
        out.append(name.replace("/", BS))
    return sorted(out, key=str.lower)


def fix_wmo_group(data, max_pad=64 * 1024):
    """Группа WMO, у которой блок MOGP объявлен длиннее файла (обрезанный хвост после конвертации
    Reforged), дополняется нулями до объявленного размера. Клиент такие файлы терпит, а строгие
    читатели (сборщик карты света Northlight) падают. Прочие файлы возвращаются как есть."""
    off = 0
    while off + 8 <= len(data):
        tag, size = struct.unpack_from("<4sI", data, off)
        end = off + 8 + size
        if tag == b"PGOM":
            missing = end - len(data)
            return data + b"\0" * missing if 0 < missing <= max_pad else data
        if end > len(data):
            return data
        off = end
    return data


def merge_dbc(primary, secondary):
    """WDBC без строк: все записи primary плюс записи secondary с новыми ID (по первому полю)."""
    def parse(raw):
        magic, count, fields, rsize, ssize = struct.unpack_from("<4s4I", raw, 0)
        if magic != b"WDBC":
            raise ValueError("не WDBC")
        if ssize > 1:
            raise ValueError("сведение DBC со строками не поддерживается")
        body = raw[20:20 + count * rsize]
        recs = [body[i * rsize:(i + 1) * rsize] for i in range(count)]
        return fields, rsize, recs

    f1, r1, a = parse(primary)
    f2, r2, b = parse(secondary)
    if (f1, r1) != (f2, r2):
        raise ValueError(f"разная структура DBC: {(f1, r1)} и {(f2, r2)}")
    ids = {struct.unpack_from("<I", r)[0] for r in a}
    merged = a + [r for r in b if struct.unpack_from("<I", r)[0] not in ids]
    merged.sort(key=lambda r: struct.unpack_from("<I", r)[0])
    added = len(merged) - len(a)
    head = struct.pack("<4s4I", b"WDBC", len(merged), f1, r1, 1)
    return head + b"".join(merged) + b"\0", added


class PartWriter:
    """Пишет файлы подряд в части; новая часть — когда текущая перевалила за limit."""

    def __init__(self, paths, open_part, limit=PART_LIMIT, size_of=os.path.getsize):
        self._paths, self._open, self._limit, self._size_of = list(paths), open_part, limit, size_of
        self._idx, self._cur, self.used = -1, None, []

    def _next(self):
        if self._cur is not None:
            self._cur.close()
        self._idx += 1
        if self._idx >= len(self._paths):
            raise RuntimeError("не хватило букв для частей: увеличьте список в PACKS")
        self._cur = self._open(self._paths[self._idx])
        self.used.append(self._paths[self._idx])

    def add(self, name, data):
        if self._cur is None or self._size_of(self._paths[self._idx]) >= self._limit:
            self._next()
        self._cur.add(name, data)

    def close(self):
        if self._cur is not None:
            self._cur.close()
            self._cur = None


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_pack(args):
    """В отдельном процессе: перепаковать один пак Reforged в свои части."""
    pack, src, out_dir = args
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import stormlib
    names_all = []
    with stormlib.Archive(src) as a:
        names = select_names(pack, a.names())
        paths = [os.path.join(out_dir, "Data", f"patch-{letter}.MPQ") for letter in PACKS[pack]]
        for p in paths:
            if os.path.exists(p):
                os.remove(p)
        os.makedirs(os.path.dirname(paths[0]), exist_ok=True)
        w = PartWriter(paths, lambda p: stormlib.Archive(p, create=True, max_files=len(names)))
        t0 = time.time()
        for i, name in enumerate(names):
            try:
                data = a.read(name)
            except FileNotFoundError:
                continue  # в списке есть, в архиве нет — бывает у самодельных MPQ
            if WMO_GROUP_RE.search(name):
                data = fix_wmo_group(data)
            w.add(name, data)
            names_all.append(name)
            if i % 2000 == 0:
                print(f"  {pack}: {i}/{len(names)} ({time.time() - t0:.0f} с)", flush=True)
        w.close()
    return pack, w.used, len(names_all)


def build(reforged, sky, client, out_dir, jobs=4):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import stormlib
    os.makedirs(out_dir, exist_ok=True)
    tasks = [(p, os.path.join(reforged, f"patch-{p}.mpq"), out_dir) for p in PACKS]
    results = {}
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for pack, used, count in ex.map(_build_pack, tasks):
            results[pack] = (used, count)
            print(f"{pack}: {count} файлов -> {', '.join(os.path.basename(u) for u in used)}", flush=True)

    # сведённая таблица креплений эффектов: наш HD-пак персонажей + новые записи пака P
    with stormlib.Archive(os.path.join(reforged, "patch-P.mpq")) as p:
        reforged_dbc = p.read(ATTACH_DBC)
    with stormlib.Archive(os.path.join(client, "Data", "ruRU", "patch-ruRU-A.MPQ")) as a:
        client_dbc = a.read(ATTACH_DBC)
    merged, added = merge_dbc(client_dbc, reforged_dbc)
    dbc_mpq = os.path.join(out_dir, *MERGED_DBC_MPQ.split("/"))
    os.makedirs(os.path.dirname(dbc_mpq), exist_ok=True)
    if os.path.exists(dbc_mpq):
        os.remove(dbc_mpq)
    with stormlib.Archive(dbc_mpq, create=True, max_files=4) as m:
        m.add(ATTACH_DBC, merged)
    print(f"SpellVisualKitModelAttach: +{added} записей из Reforged P -> {MERGED_DBC_MPQ}")

    sky_dst = os.path.join(out_dir, *SKY_MPQ.split("/"))
    shutil.copyfile(sky, sky_dst)

    files = []
    for root, _, names in os.walk(out_dir):
        for n in names:
            p = os.path.join(root, n)
            rel = os.path.relpath(p, out_dir).replace(os.sep, "/")
            files.append({"path": rel, "size": os.path.getsize(p), "sha256": _sha256(p)})
    files.sort(key=lambda f: f["path"].lower())
    with open(os.path.join(out_dir, "forever-files.json"), "w", encoding="utf-8") as f:
        json.dump(files, f, ensure_ascii=False, indent=2)
    total = sum(f["size"] for f in files if f["path"] != "forever-files.json")
    print(f"Готово: {len(files)} файлов, {total / 1024 ** 3:.2f} ГБ -> {out_dir}")
    return files


def main(argv=None):
    ap = argparse.ArgumentParser(description="Сборка MPQ издания «Forever»")
    ap.add_argument("--reforged", required=True, help="папка с patch-B/D/E/P.mpq Project Reforged")
    ap.add_argument("--sky", required=True, help="Patch-ruRU-X.mpq — HD-небо Sectym")
    ap.add_argument("--client", required=True, help="клиент с нашими HD-паками (нужен patch-ruRU-A.MPQ)")
    ap.add_argument("--out", default="dist-forever")
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args(argv)
    build(args.reforged, args.sky, args.client, args.out, args.jobs)


if __name__ == "__main__":
    main()
