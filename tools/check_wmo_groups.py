"""Проверка групп WMO в собранных MPQ: блок MOGP не должен выходить за конец файла.

Northlight (и другие строгие читатели) отказываются от таких файлов, клиент их терпит.
Запуск: python tools/check_wmo_groups.py dist-forever/Data/patch-C.MPQ dist-forever/Data/patch-D.MPQ
"""

import re
import struct
import sys

import stormlib

GROUP_RE = re.compile(r"_\d{3}\.wmo$", re.IGNORECASE)


def mogp_problem(data):
    """None, если блоки укладываются в файл; иначе описание."""
    off = 0
    while off + 8 <= len(data):
        tag, size = struct.unpack_from("<4sI", data, off)
        end = off + 8 + size
        if end > len(data):
            return f"{tag[::-1].decode('ascii', 'replace')} size {size} at {off} exceeds file ({len(data)})"
        if tag == b"PGOM":
            return None  # MOGP — последний внешний блок группы
        off = end
    return "no MOGP"


def main(paths):
    bad = []
    for path in paths:
        with stormlib.Archive(path) as a:
            for name in a.names():
                if GROUP_RE.search(name):
                    problem = mogp_problem(a.read(name))
                    if problem:
                        bad.append((path, name, problem))
    for p, n, why in bad:
        print(f"{n}\t{why}")
    print(f"битых групп: {len(bad)}", file=sys.stderr)
    return bad


if __name__ == "__main__":
    main(sys.argv[1:])
