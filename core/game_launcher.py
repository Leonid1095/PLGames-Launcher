"""
Game launching, realmlist management, and Config.wtf editing.
"""

import os
import re
import subprocess


def set_realmlist(game_path: str, realmlist_value: str, realmlist_paths: list[str]) -> bool:
    """Write realmlist to the first found (or creatable) realmlist.wtf."""
    target = None
    for rel in realmlist_paths:
        full = os.path.join(game_path, rel)
        if os.path.exists(full):
            target = full
            break

    if not target:
        # Create in first path whose parent dir exists
        for rel in realmlist_paths:
            full = os.path.join(game_path, rel)
            parent = os.path.dirname(full)
            if os.path.isdir(parent):
                target = full
                break

    if not target:
        target = os.path.join(game_path, "realmlist.wtf")

    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(realmlist_value + "\n")
        return True
    except Exception as e:
        print(f"[Realmlist] Failed to write {target}: {e}")
        return False


def launch_game(game_path: str, exe_name: str) -> tuple[bool, str]:
    """Launch the game executable. Returns (success, error_message)."""
    exe_path = os.path.join(game_path, exe_name)
    if not os.path.isfile(exe_path):
        return False, f"Файл {exe_name} не найден в {game_path}"
    try:
        subprocess.Popen([exe_path], cwd=game_path)
        return True, ""
    except Exception as e:
        return False, str(e)


def read_config_wtf(game_path: str) -> dict[str, str]:
    """Read WoW Config.wtf into a dict of SET key value pairs."""
    config_path = os.path.join(game_path, "WTF", "Config.wtf")
    result = {}
    if not os.path.isfile(config_path):
        return result
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                m = re.match(r'^SET\s+(\S+)\s+"?([^"]*)"?\s*$', line)
                if m:
                    result[m.group(1)] = m.group(2)
    except Exception:
        pass
    return result


def write_config_wtf(game_path: str, settings: dict[str, str]):
    """Write settings back to Config.wtf, preserving unknown lines."""
    config_path = os.path.join(game_path, "WTF", "Config.wtf")
    lines = []
    written_keys = set()

    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    m = re.match(r'^SET\s+(\S+)\s+', stripped)
                    if m and m.group(1) in settings:
                        key = m.group(1)
                        val = settings[key]
                        lines.append(f'SET {key} "{val}"\n')
                        written_keys.add(key)
                    else:
                        lines.append(line if line.endswith("\n") else line + "\n")
        except Exception:
            pass

    # Append new keys
    for key, val in settings.items():
        if key not in written_keys:
            lines.append(f'SET {key} "{val}"\n')

    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception as e:
        print(f"[Config.wtf] Write failed: {e}")


def detect_game_path() -> str | None:
    """Try to auto-detect WoW installation by looking near the launcher exe."""
    import sys
    if getattr(sys, 'frozen', False):
        launcher_dir = os.path.dirname(sys.executable)
    else:
        launcher_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Check parent directories up to 3 levels
    check = launcher_dir
    for _ in range(4):
        wow_exe = os.path.join(check, "wow.exe")
        wow_exe2 = os.path.join(check, "Wow.exe")
        if os.path.isfile(wow_exe) or os.path.isfile(wow_exe2):
            return check
        check = os.path.dirname(check)
    return None
