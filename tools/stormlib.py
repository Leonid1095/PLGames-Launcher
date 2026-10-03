"""Минимальная обёртка над StormLib (MIT, tools/bin/StormLib.dll, x64) для сборки MPQ.

Нужна только инструментам публикации контента, в лаунчер не входит."""

import ctypes as C
import os

DLL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin", "StormLib.dll")

_H, _U = C.c_void_p, C.c_uint32
_lib = None

MPQ_CREATE_LISTFILE = 0x00100000
MPQ_CREATE_ATTRIBUTES = 0x00200000
MPQ_FILE_COMPRESS = 0x00000200
MPQ_FILE_REPLACEEXISTING = 0x80000000
MPQ_COMPRESSION_ZLIB = 0x02
STREAM_FLAG_READ_ONLY = 0x00000100


def _bind():
    global _lib
    if _lib is not None:
        return _lib
    lib = C.WinDLL(DLL)

    def fn(name, args, res=C.c_bool):
        f = getattr(lib, name)
        f.argtypes, f.restype = args, res
        return f

    lib.open_archive = fn("SFileOpenArchive", [C.c_wchar_p, _U, _U, C.POINTER(_H)])
    lib.create_archive = fn("SFileCreateArchive", [C.c_wchar_p, _U, _U, C.POINTER(_H)])
    lib.close_archive = fn("SFileCloseArchive", [_H])
    lib.open_file = fn("SFileOpenFileEx", [_H, C.c_char_p, _U, C.POINTER(_H)])
    lib.file_size = fn("SFileGetFileSize", [_H, C.POINTER(_U)], _U)
    lib.read_file = fn("SFileReadFile", [_H, C.c_void_p, _U, C.POINTER(_U), _H])
    lib.close_file = fn("SFileCloseFile", [_H])
    lib.has_file = fn("SFileHasFile", [_H, C.c_char_p])
    lib.create_file = fn("SFileCreateFile", [_H, C.c_char_p, C.c_uint64, _U, _U, _U, C.POINTER(_H)])
    lib.write_file = fn("SFileWriteFile", [_H, C.c_void_p, _U, _U])
    lib.finish_file = fn("SFileFinishFile", [_H])
    _lib = lib
    return lib


class Archive:
    """Чтение (по умолчанию) или создание MPQ v1 с (listfile)."""

    def __init__(self, path, create=False, max_files=4096):
        lib = _bind()
        self.path, self.handle = path, _H()
        if create:
            if os.path.exists(path):
                raise FileExistsError(path)
            cap = 16
            while cap < max_files + 4:
                cap *= 2
            ok = lib.create_archive(path, MPQ_CREATE_LISTFILE | MPQ_CREATE_ATTRIBUTES, cap, C.byref(self.handle))
        else:
            ok = lib.open_archive(path, 0, STREAM_FLAG_READ_ONLY, C.byref(self.handle))
        if not ok:
            raise OSError(f"Не удалось открыть MPQ: {path} (GetLastError={C.GetLastError()})")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        if self.handle:
            if not _bind().close_archive(self.handle):
                raise OSError(f"Не удалось закрыть MPQ: {self.path}")
            self.handle = _H()

    def has(self, name):
        return bool(_bind().has_file(self.handle, name.encode("utf-8")))

    def read(self, name):
        lib, fh = _bind(), _H()
        if not lib.open_file(self.handle, name.encode("utf-8"), 0, C.byref(fh)):
            raise FileNotFoundError(f"{self.path}: {name}")
        try:
            size = lib.file_size(fh, None)
            if size == 0xFFFFFFFF:
                raise OSError(f"Размер не прочитан: {name}")
            buf, got = C.create_string_buffer(size), _U()
            if size and (not lib.read_file(fh, buf, size, C.byref(got), None) or got.value != size):
                raise OSError(f"Не удалось прочитать {name}")
            return buf.raw[:size]
        finally:
            lib.close_file(fh)

    def names(self):
        """Имена из (listfile); у архива без списка — пусто."""
        try:
            data = self.read("(listfile)")
        except FileNotFoundError:
            return []
        out = []
        for line in data.decode("utf-8", errors="replace").splitlines():
            line = line.strip().split(";")[0]
            if line:
                out.append(line)
        return out

    def add(self, name, data):
        lib, fh = _bind(), _H()
        if not lib.create_file(self.handle, name.encode("utf-8"), 0, len(data), 0,
                               MPQ_FILE_COMPRESS | MPQ_FILE_REPLACEEXISTING, C.byref(fh)):
            raise OSError(f"Не удалось добавить {name} (GetLastError={C.GetLastError()})")
        ok = True
        if data:
            buf = C.create_string_buffer(data, len(data))
            ok = lib.write_file(fh, buf, len(data), MPQ_COMPRESSION_ZLIB)
        if not lib.finish_file(fh) or not ok:
            raise OSError(f"Не удалось записать {name}")
