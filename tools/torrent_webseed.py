"""Прямые HTTP-источники (web seed, BEP 19) в .torrent клиента.

aria2c качает и у раздающих, и по ссылке url-list — так клиент можно скачать, даже когда никто
не раздаёт. Поле лежит вне словаря info, поэтому info-hash не меняется: нынешние раздачи и уже
начатые загрузки остаются теми же. Скрипт это проверяет и без совпадения ничего не пишет.

Запуск (из папки launcher/):
    python tools/torrent_webseed.py PLGames_Wow3.3.5.torrent https://plgames-wow.ru/launcher/client/PLGames_Wow3.3.5.rar
"""

import argparse
import hashlib
import sys


def bdecode(data, i=0):
    """(значение, позиция после него). Строки остаются bytes."""
    c = data[i:i + 1]
    if c == b"i":
        j = data.index(b"e", i)
        return int(data[i + 1:j]), j + 1
    if c == b"l":
        i, out = i + 1, []
        while data[i:i + 1] != b"e":
            v, i = bdecode(data, i)
            out.append(v)
        return out, i + 1
    if c == b"d":
        i, out = i + 1, {}
        while data[i:i + 1] != b"e":
            k, i = bdecode(data, i)
            v, i = bdecode(data, i)
            out[k] = v
        return out, i + 1
    if not c.isdigit():
        raise ValueError(f"не bencode в позиции {i}")
    j = data.index(b":", i)
    n = int(data[i:j])
    return data[j + 1:j + 1 + n], j + 1 + n


def bencode(v):
    if isinstance(v, int):
        return b"i%de" % v
    if isinstance(v, (bytes, bytearray)):
        return b"%d:%s" % (len(v), bytes(v))
    if isinstance(v, str):
        return bencode(v.encode("utf-8"))
    if isinstance(v, list):
        return b"l" + b"".join(bencode(x) for x in v) + b"e"
    if isinstance(v, dict):
        return b"d" + b"".join(bencode(k) + bencode(v[k]) for k in sorted(v)) + b"e"
    raise TypeError(type(v))


def info_hash(torrent_bytes):
    t, _ = bdecode(torrent_bytes)
    return hashlib.sha1(bencode(t[b"info"])).hexdigest()


def add_webseeds(torrent_bytes, urls):
    """Новый .torrent с url-list = urls (старые ссылки сохраняются, повторы убираются)."""
    t, end = bdecode(torrent_bytes)
    if end != len(torrent_bytes) or b"info" not in t:
        raise ValueError("это не .torrent")
    # info должен перекодироваться байт-в-байт, иначе info-hash изменится
    start = torrent_bytes.index(b"4:info") + len(b"4:info")
    _, info_end = bdecode(torrent_bytes, start)
    if bencode(t[b"info"]) != torrent_bytes[start:info_end]:
        raise ValueError("словарь info в нестандартной кодировке — менять торрент небезопасно")
    old = t.get(b"url-list", [])
    old = [old] if isinstance(old, bytes) else list(old)
    seeds = []
    for u in old + [u.encode("utf-8") for u in urls]:
        if not u.startswith((b"https://", b"http://")):
            raise ValueError(f"не http-ссылка: {u!r}")
        if u not in seeds:
            seeds.append(u)
    t[b"url-list"] = seeds
    out = bencode(t)
    if info_hash(out) != info_hash(torrent_bytes):
        raise AssertionError("info-hash изменился")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Добавить web seed в .torrent")
    ap.add_argument("torrent")
    ap.add_argument("urls", nargs="+")
    args = ap.parse_args(argv)
    data = open(args.torrent, "rb").read()
    out = add_webseeds(data, args.urls)
    open(args.torrent, "wb").write(out)
    t, _ = bdecode(out)
    print(f"info-hash {info_hash(out)} (прежний), url-list: {[u.decode() for u in t[b'url-list']]}")


if __name__ == "__main__":
    sys.exit(main())
