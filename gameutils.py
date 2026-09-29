"""Утилиты для папки клиента WoW 3.3.5a: безопасные пути, Config.wtf, MPQ-патчи,
проверка запущенной игры. Без UI — общие для app.py, content.py и тестов."""

import os
import re
import subprocess

NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: не мигать консолью из GUI-процесса

_SET_RE = re.compile(r'^SET\s+(\S+)\s+"?([^"]*)"?\s*$')
_SET_KEY_RE = re.compile(r'^SET\s+(\S+)\s+')


def safe_join(base, rel):
    """Join rel onto base, refusing absolute paths or ones that escape base.
    Защищает от путей из манифеста/сервера вида '..\\..\\' или 'C:/Windows/...'."""
    if not rel:
        return None
    full = os.path.abspath(os.path.normpath(os.path.join(base, rel)))
    base_abs = os.path.abspath(os.path.normpath(base))
    try:
        if os.path.commonpath([base_abs, full]) != base_abs:
            return None
    except ValueError:
        return None  # разные диски
    return full


def _config_path(gp):
    return os.path.join(gp, "WTF", "Config.wtf")


def read_config_wtf(gp):
    cfg = {}
    p = _config_path(gp)
    if not os.path.isfile(p):
        return cfg
    try:
        with open(p, "r", encoding="utf-8", errors="surrogateescape") as f:
            for line in f:
                m = _SET_RE.match(line.strip())
                if m:
                    cfg[m.group(1)] = m.group(2)
    except OSError:
        pass
    return cfg


def write_config_wtf(gp, settings):
    """Пишет SET-строки в WTF/Config.wtf, сохраняя остальные строки байт-в-байт.
    Значение None удаляет ключ. True — если файл записан.
    Ключи сравниваются без учёта регистра: так их читает WoW."""
    p = _config_path(gp)
    by_lower = {k.lower(): k for k in settings}
    lines, written = [], set()
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8", errors="surrogateescape") as f:
                for line in f:
                    m = _SET_KEY_RE.match(line.strip())
                    if m and m.group(1).lower() in by_lower:
                        key = by_lower[m.group(1).lower()]
                        if key in written:
                            continue
                        written.add(key)
                        if settings[key] is not None:
                            lines.append(f'SET {key} "{settings[key]}"\n')
                    else:
                        lines.append(line if line.endswith("\n") else line + "\n")
        except OSError:
            return False
    for key, value in settings.items():
        if key not in written and value is not None:
            lines.append(f'SET {key} "{value}"\n')
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", errors="surrogateescape") as f:
            f.writelines(lines)
        return True
    except OSError:
        return False


def _mpq_paths(gp, fname, folder):
    if not fname or os.path.basename(fname) != fname or "/" in fname:
        return None, None
    base = safe_join(gp, folder)
    if not base:
        return None, None
    active = os.path.join(base, fname)
    return active, active + ".disabled"


def mpq_status(gp, fname, folder):
    """(установлен, включён, размер МБ). Выключенный патч лежит как <имя>.disabled."""
    active, disabled = _mpq_paths(gp, fname, folder)
    if active and os.path.isfile(active):
        return True, True, round(os.path.getsize(active) / 1048576, 1)
    if disabled and os.path.isfile(disabled):
        return True, False, round(os.path.getsize(disabled) / 1048576, 1)
    return False, False, 0


def toggle_mpq(gp, fname, folder, enable):
    active, disabled = _mpq_paths(gp, fname, folder)
    if not active:
        return False
    try:
        if enable and os.path.isfile(disabled):
            os.rename(disabled, active)
        elif not enable and os.path.isfile(active):
            os.rename(active, disabled)
        return True
    except OSError:
        return False


def is_process_running(image_name):
    """True, если процесс с таким именем exe запущен (tasklist, без консоли)."""
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/NH", "/FO", "CSV"],
                             capture_output=True, timeout=10, creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return False
    text = out.stdout.decode("cp866", errors="replace").lower()
    return f'"{image_name.lower()}"' in text


_job_handle = None


def _job():
    """Один Job Object на процесс лаунчера с JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE:
    когда лаунчер завершается (даже аварийно), Windows убивает все процессы в нём."""
    global _job_handle
    if _job_handle:
        return _job_handle
    import ctypes
    from ctypes import wintypes

    class BasicLimit(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ("Read", "Write", "Other", "ReadBytes", "WriteBytes", "OtherBytes")]

    class ExtendedLimit(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BasicLimit), ("IoInfo", IoCounters),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k32 = ctypes.WinDLL("kernel32")
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
    k32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
    handle = k32.CreateJobObjectW(None, None)
    if not handle:
        raise OSError("CreateJobObject failed")
    info = ExtendedLimit()
    info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k32.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):  # ExtendedLimitInformation
        raise OSError("SetInformationJobObject failed")
    _job_handle = handle
    return handle


def kill_on_close(popen):
    """Привязать дочерний процесс к жизни лаунчера (best-effort: без Job Object просто работает как раньше)."""
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32")
        k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        return bool(k32.AssignProcessToJobObject(_job(), wintypes.HANDLE(int(popen._handle))))
    except (OSError, AttributeError, ValueError):
        return False


def pid_alive(pid):
    """True, если процесс с таким PID ещё работает."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32")
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        return bool(k32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
    finally:
        k32.CloseHandle(handle)


def _process_image_paths():
    """Полные пути exe всех процессов, которые удалось опросить (WinAPI через ctypes)."""
    import ctypes
    from ctypes import wintypes
    psapi, k32 = ctypes.WinDLL("psapi"), ctypes.WinDLL("kernel32")
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    k32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                               ctypes.POINTER(wintypes.DWORD))
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    pids = (wintypes.DWORD * 8192)()
    needed = wintypes.DWORD()
    if not psapi.EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(needed)):
        raise OSError("EnumProcesses failed")
    buf = ctypes.create_unicode_buffer(32768)
    paths = []
    for pid in pids[:needed.value // ctypes.sizeof(wintypes.DWORD)]:
        handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            continue
        try:
            size = wintypes.DWORD(len(buf))
            if k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                paths.append(buf.value)
        finally:
            k32.CloseHandle(handle)
    return paths


def is_game_running(game_dir, exe_names=("wow.exe",)):
    """True, если запущена игра именно из этой папки. Другой клиент (другая папка)
    не мешает. Если путь процесса прочитать не удалось, а процесс с таким именем
    есть — осторожно считаем, что запущена."""
    names = {n.lower() for n in exe_names}
    try:
        paths = _process_image_paths()
    except (OSError, AttributeError):
        return any(is_process_running(n) for n in exe_names)
    target = os.path.normcase(os.path.abspath(game_dir))
    ours = [p for p in paths if os.path.basename(p).lower() in names]
    if any(os.path.normcase(os.path.dirname(p)) == target for p in ours):
        return True
    return not ours and any(is_process_running(n) for n in exe_names)
