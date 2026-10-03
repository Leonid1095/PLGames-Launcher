"""Видеокарта игрока, её возможности (Vulkan) и рекомендация графического издания под его ПК."""

import ctypes
import json
import subprocess

from gameutils import NO_WINDOW

# Встроенная графика: для HD-паков и тяжёлого пост-процесса её обычно мало.
_INTEGRATED_MARKERS = ("intel(r) uhd", "intel(r) hd", "intel(r) iris", "intel(r) graphics",
                       "microsoft basic", "radeon(tm) graphics", "radeon vega", "amd radeon graphics")
_ULTRA_VRAM_MB = 3900  # AdapterRAM — uint32, для карт от 4 ГБ Windows отдаёт ~4095 МБ


def detect_gpus(timeout=15):
    """[{"name", "vram_mb"}] через Win32_VideoController; [] если не удалось."""
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
           "Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM | ConvertTo-Json -Compress"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=NO_WINDOW)
        data = json.loads(r.stdout.decode("utf-8", errors="replace") or "[]")
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    if isinstance(data, dict):
        data = [data]
    gpus = []
    for g in data if isinstance(data, list) else []:
        if isinstance(g, dict) and g.get("Name"):
            ram = g.get("AdapterRAM")
            gpus.append({"name": str(g["Name"]), "vram_mb": ram // 2**20 if isinstance(ram, int) else 0})
    return gpus


class _VkApplicationInfo(ctypes.Structure):
    _fields_ = [("sType", ctypes.c_uint32), ("pNext", ctypes.c_void_p), ("pApplicationName", ctypes.c_char_p),
                ("applicationVersion", ctypes.c_uint32), ("pEngineName", ctypes.c_char_p),
                ("engineVersion", ctypes.c_uint32), ("apiVersion", ctypes.c_uint32)]


class _VkInstanceCreateInfo(ctypes.Structure):
    _fields_ = [("sType", ctypes.c_uint32), ("pNext", ctypes.c_void_p), ("flags", ctypes.c_uint32),
                ("pApplicationInfo", ctypes.POINTER(_VkApplicationInfo)),
                ("enabledLayerCount", ctypes.c_uint32), ("ppEnabledLayerNames", ctypes.c_void_p),
                ("enabledExtensionCount", ctypes.c_uint32), ("ppEnabledExtensionNames", ctypes.c_void_p)]


_VK_DEVICE_TYPE_CPU = 4  # программный рендер (llvmpipe, SwiftShader) — для игры не считается


def vulkan_version():
    """Наибольшая версия Vulkan (major, minor) среди видеокарт по ответу драйвера; None — Vulkan нет.
    Тот же запрос делает любая игра на Vulkan: создать instance, перечислить устройства, прочитать
    apiVersion (первое поле VkPhysicalDeviceProperties, тип устройства — пятое)."""
    try:
        vk = ctypes.WinDLL("vulkan-1.dll")
    except (OSError, AttributeError):
        return None
    app = _VkApplicationInfo(0, None, b"PLGamesLauncher", 1, None, 0, 1 << 22)  # запрос Vulkan 1.0
    info = _VkInstanceCreateInfo(1, None, 0, ctypes.pointer(app), 0, None, 0, None)
    instance = ctypes.c_void_p()
    if vk.vkCreateInstance(ctypes.byref(info), None, ctypes.byref(instance)) != 0:
        return None
    try:
        count = ctypes.c_uint32(0)
        vk.vkEnumeratePhysicalDevices(instance, ctypes.byref(count), None)
        devices = (ctypes.c_void_p * count.value)()
        if count.value == 0 or vk.vkEnumeratePhysicalDevices(instance, ctypes.byref(count), devices) not in (0, 5):
            return None
        best = None
        for dev in devices[:count.value]:
            props = (ctypes.c_uint32 * 512)()  # VkPhysicalDeviceProperties ≈ 824 байта
            vk.vkGetPhysicalDeviceProperties(ctypes.c_void_p(dev), props)
            if props[4] == _VK_DEVICE_TYPE_CPU:
                continue
            version = ((props[0] >> 22) & 0x7F, (props[0] >> 12) & 0x3FF)
            best = version if best is None or version > best else best
        return best
    finally:
        vk.vkDestroyInstance(instance, None)


def detect_capabilities(probe=vulkan_version):
    """Возможности ПК для полей requires в манифесте изданий (content.CAPABILITIES)."""
    try:
        version = probe()
    except Exception:
        return frozenset()
    return frozenset({"vulkan13"}) if version is not None and tuple(version) >= (1, 3) else frozenset()


def is_integrated(name):
    n = name.lower()
    return any(marker in n for marker in _INTEGRATED_MARKERS)


def recommend_edition(gpus):
    """Нет данных → remaster; только встроенная графика → classic;
    дискретная от 4 ГБ → forever; иначе remaster."""
    if not gpus:
        return "remaster"
    discrete = [g for g in gpus if not is_integrated(g["name"])]
    if not discrete:
        return "classic"
    if max(g["vram_mb"] for g in discrete) >= _ULTRA_VRAM_MB:
        return "forever"
    return "remaster"
