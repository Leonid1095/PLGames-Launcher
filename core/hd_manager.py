"""
HD Patch Manager — toggle HD model patches on/off.
Works by renaming MPQ files: patch-X.MPQ <-> patch-X.MPQ.disabled
Supports patches in Data/ and Data/ruRU/ subfolders.
"""

import os
import glob as globmod


DISABLED_SUFFIX = ".disabled"


def _resolve_folder(game_path: str, folder: str) -> str:
    """Resolve patch folder relative to game path."""
    return os.path.join(game_path, folder)


def is_patch_enabled(game_path: str, filename: str, folder: str = "Data") -> bool:
    """Check if a patch file is active (not .disabled)."""
    base = _resolve_folder(game_path, folder)
    return os.path.isfile(os.path.join(base, filename))


def is_patch_installed(game_path: str, filename: str, folder: str = "Data") -> bool:
    """Check if patch exists in either state."""
    base = _resolve_folder(game_path, folder)
    return (os.path.isfile(os.path.join(base, filename)) or
            os.path.isfile(os.path.join(base, filename + DISABLED_SUFFIX)))


def enable_patch(game_path: str, filename: str, folder: str = "Data") -> tuple[bool, str]:
    """Enable an HD patch by removing .disabled suffix."""
    base = _resolve_folder(game_path, folder)
    disabled_path = os.path.join(base, filename + DISABLED_SUFFIX)
    active_path = os.path.join(base, filename)

    if os.path.isfile(active_path):
        return True, "Уже включен"

    if not os.path.isfile(disabled_path):
        return False, f"Файл {filename} не найден в {folder}"

    try:
        os.rename(disabled_path, active_path)
        return True, "Включен"
    except Exception as e:
        return False, str(e)


def disable_patch(game_path: str, filename: str, folder: str = "Data") -> tuple[bool, str]:
    """Disable an HD patch by adding .disabled suffix."""
    base = _resolve_folder(game_path, folder)
    disabled_path = os.path.join(base, filename + DISABLED_SUFFIX)
    active_path = os.path.join(base, filename)

    if os.path.isfile(disabled_path):
        return True, "Уже выключен"

    if not os.path.isfile(active_path):
        return False, f"Файл {filename} не найден в {folder}"

    try:
        os.rename(active_path, disabled_path)
        return True, "Выключен"
    except Exception as e:
        return False, str(e)


def toggle_patch(game_path: str, filename: str, enable: bool,
                 folder: str = "Data") -> tuple[bool, str]:
    if enable:
        return enable_patch(game_path, filename, folder)
    else:
        return disable_patch(game_path, filename, folder)


def toggle_patch_group(game_path: str, files: list[str], enable: bool,
                       folder: str = "Data") -> tuple[bool, str]:
    """Toggle a group of related patch files together (e.g. F+G creatures)."""
    errors = []
    for fname in files:
        ok, msg = toggle_patch(game_path, fname, enable, folder)
        if not ok and "не найден" not in msg:
            errors.append(f"{fname}: {msg}")
    if errors:
        return False, "; ".join(errors)
    return True, "Включен" if enable else "Выключен"


def get_patch_status(game_path: str, files: list[str],
                     folder: str = "Data") -> dict:
    """Get status info for a patch group.
    Returns {installed, enabled, total_size_mb}."""
    base = _resolve_folder(game_path, folder)
    installed = False
    all_enabled = True
    total_size = 0

    for fname in files:
        active_path = os.path.join(base, fname)
        disabled_path = os.path.join(base, fname + DISABLED_SUFFIX)

        if os.path.isfile(active_path):
            installed = True
            total_size += os.path.getsize(active_path)
        elif os.path.isfile(disabled_path):
            installed = True
            all_enabled = False
            total_size += os.path.getsize(disabled_path)
        else:
            all_enabled = False

    return {
        "installed": installed,
        "enabled": all_enabled and installed,
        "total_size_mb": round(total_size / (1024 * 1024), 1),
    }


def scan_hd_patches(game_path: str) -> list[dict]:
    """Scan Data/ and Data/ruRU/ for HD patch files.
    Returns list of {filename, folder, enabled, size_mb}."""
    results = []
    seen = set()

    for subfolder in ["Data", os.path.join("Data", "ruRU")]:
        base = os.path.join(game_path, subfolder)
        if not os.path.isdir(base):
            continue

        patterns = [
            os.path.join(base, "patch-[456789].MPQ*"),
            os.path.join(base, "patch-[A-Z].MPQ*"),
            os.path.join(base, "patch-[A-Z].mpq*"),
            os.path.join(base, "Patch-*.MPQ*"),
            os.path.join(base, "Patch-*.mpq*"),
            os.path.join(base, "patch-ruRU-*.MPQ*"),
            os.path.join(base, "patch-ruRU-*.mpq*"),
        ]

        for pattern in patterns:
            for filepath in globmod.glob(pattern, recursive=False):
                basename = os.path.basename(filepath)
                clean_name = basename.replace(DISABLED_SUFFIX, "")
                key = f"{subfolder}/{clean_name}"
                if key in seen:
                    continue
                seen.add(key)

                enabled = not basename.endswith(DISABLED_SUFFIX)
                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                results.append({
                    "filename": clean_name,
                    "folder": subfolder,
                    "enabled": enabled,
                    "size_mb": round(size_mb, 1),
                })

    results.sort(key=lambda x: (x["folder"], x["filename"]))
    return results
