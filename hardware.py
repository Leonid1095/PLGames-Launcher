"""Видеокарта игрока и рекомендация графического издания под его ПК."""

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


def is_integrated(name):
    n = name.lower()
    return any(marker in n for marker in _INTEGRATED_MARKERS)


def recommend_edition(gpus):
    """Нет данных → remaster; только встроенная графика → classic;
    дискретная от 4 ГБ → ultra; иначе remaster."""
    if not gpus:
        return "remaster"
    discrete = [g for g in gpus if not is_integrated(g["name"])]
    if not discrete:
        return "classic"
    if max(g["vram_mb"] for g in discrete) >= _ULTRA_VRAM_MB:
        return "ultra"
    return "remaster"
