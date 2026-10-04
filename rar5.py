"""Минимальное чтение RAR5 для починки клиента: где в архиве лежит каждый файл и как вырезать его
в самостоятельный мини-архив.

Архив клиента — RAR5 без «solid»: каждый файл упакован независимо, его заголовок и данные лежат
одним куском. Мини-архив = сигнатура + главный заголовок архива + этот кусок + заголовок конца.
Его распаковывает обычный распаковщик (7-Zip, tar), а CRC32 внутри куска проверяет результат.
Формат: https://www.rarlab.com/technote.htm (RAR 5.0 archive format)."""

import struct
import zlib

SIGNATURE = b"Rar!\x1a\x07\x01\x00"
HEAD_MAIN, HEAD_FILE, HEAD_SERVICE, HEAD_CRYPT, HEAD_END = 1, 2, 3, 4, 5
_FILE_DIR, _FILE_MTIME, _FILE_CRC = 0x1, 0x2, 0x4
_HFL_EXTRA, _HFL_DATA = 0x1, 0x2


class RarError(ValueError):
    pass


def read_vint(buf, i):
    """Целое переменной длины RAR5: по 7 бит в байте, старший бит — «дальше ещё байт»."""
    value, shift = 0, 0
    while True:
        if i >= len(buf) or shift > 63:
            raise RarError("обрезанное число в заголовке")
        b = buf[i]
        value |= (b & 0x7F) << shift
        i += 1
        if not b & 0x80:
            return value, i
        shift += 7


def end_header():
    """Заголовок конца архива: тип 5, флаги 0, флаги конца 0."""
    body = bytes([HEAD_END, 0, 0])
    sized = bytes([len(body)]) + body
    return struct.pack("<I", zlib.crc32(sized) & 0xFFFFFFFF) + sized


def mini_archive(main_header, pieces):
    """Самостоятельный архив из главного заголовка и кусков файлов (заголовок + данные каждого)."""
    return SIGNATURE + main_header + b"".join(pieces) + end_header()


def iter_blocks(f):
    """Блоки архива: dict(type, offset, length — заголовок вместе с данными; у файлов ещё
    name, size, crc32, is_dir). f — открытый двоичный файл."""
    f.seek(0)
    if f.read(len(SIGNATURE)) != SIGNATURE:
        raise RarError("это не архив RAR5")
    pos = len(SIGNATURE)
    while True:
        f.seek(pos)
        head = f.read(4 + 3)
        if len(head) < 5:
            raise RarError("архив обрывается без заголовка конца")
        size, i = read_vint(head, 4)
        f.seek(pos)
        raw = f.read(i + size)
        if len(raw) < i + size:
            raise RarError("архив обрывается посреди заголовка")
        if zlib.crc32(raw[4:]) & 0xFFFFFFFF != struct.unpack_from("<I", raw, 0)[0]:
            raise RarError(f"повреждён заголовок по смещению {pos}")
        htype, j = read_vint(raw, i)
        flags, j = read_vint(raw, j)
        data = 0
        if flags & _HFL_EXTRA:
            _, j = read_vint(raw, j)
        if flags & _HFL_DATA:
            data, j = read_vint(raw, j)
        block = {"type": htype, "offset": pos, "length": len(raw) + data}
        if htype == HEAD_CRYPT:
            raise RarError("зашифрованные архивы не поддерживаются")
        if htype == HEAD_FILE:
            fflags, k = read_vint(raw, j)
            usize, k = read_vint(raw, k)
            _, k = read_vint(raw, k)                  # атрибуты
            if fflags & _FILE_MTIME:
                k += 4
            crc = None
            if fflags & _FILE_CRC:
                crc = struct.unpack_from("<I", raw, k)[0]
                k += 4
            _, k = read_vint(raw, k)                  # сжатие
            _, k = read_vint(raw, k)                  # ОС
            nlen, k = read_vint(raw, k)
            block.update(name=raw[k:k + nlen].decode("utf-8"), size=usize, crc32=crc,
                         is_dir=bool(fflags & _FILE_DIR))
        yield block
        if htype == HEAD_END:
            return
        pos += len(raw) + data


def build_index(path):
    """Индекс архива для лаунчера: главный заголовок и место каждого файла (без папок)."""
    with open(path, "rb") as f:
        blocks = list(iter_blocks(f))
        main = next((b for b in blocks if b["type"] == HEAD_MAIN), None)
        if main is None:
            raise RarError("нет главного заголовка")
        f.seek(main["offset"])
        main_bytes = f.read(main["length"])
        f.seek(0, 2)
        total = f.tell()
    files = [{"name": b["name"], "size": b["size"], "crc32": f"{b['crc32']:08x}" if b["crc32"] is not None else "",
              "offset": b["offset"], "length": b["length"]}
             for b in blocks if b["type"] == HEAD_FILE and not b["is_dir"]]
    return {"archive_size": total, "main_header": main_bytes.hex(), "files": files}
