"""
PLGames Launcher — Configuration
All game definitions, server URLs, and default settings.
"""

import os
import sys
import json

# --- Branding ---
LAUNCHER_TITLE = "PLGames Launcher"
LAUNCHER_VERSION = "2.0.0"

# --- API Endpoints ---
API_BASE_URL = "https://lkds-room.online"
NEWS_API_URL = f"{API_BASE_URL}/api/launcher/news"
STATUS_API_URL = f"{API_BASE_URL}/api/launcher/status"
UPDATE_MANIFEST_URL = f"{API_BASE_URL}/api/launcher/manifest"
LAUNCHER_UPDATE_URL = f"{API_BASE_URL}/api/launcher/version"

# --- Colors (Dark WoW theme) ---
COLOR_BG = "#0a0a0f"
COLOR_BG_SECONDARY = "#12121a"
COLOR_BG_CARD = "#1a1a2e"
COLOR_ACCENT = "#fca311"
COLOR_ACCENT_HOVER = "#e8940f"
COLOR_TEXT = "#e0e0e0"
COLOR_TEXT_DIM = "#888888"
COLOR_TEXT_MUTED = "#555555"
COLOR_SUCCESS = "#4ade80"
COLOR_ERROR = "#ef4444"
COLOR_WARNING = "#f59e0b"
COLOR_BORDER = "#2a2a3e"

# --- Font Sizes ---
FONT_TITLE = ("Segoe UI", 22, "bold")
FONT_HEADING = ("Segoe UI", 16, "bold")
FONT_SUBHEADING = ("Segoe UI", 13, "bold")
FONT_BODY = ("Segoe UI", 11)
FONT_SMALL = ("Segoe UI", 9)
FONT_BUTTON = ("Segoe UI", 14, "bold")

# --- Window ---
WINDOW_WIDTH = 960
WINDOW_HEIGHT = 640
WINDOW_MIN_WIDTH = 800
WINDOW_MIN_HEIGHT = 550

# --- Game Definitions ---
# Each game is a dict with all its settings.
# To add a new game/server, just add another entry here.

GAMES = {
    "chronos": {
        "id": "chronos",
        "name": "PLGames: Chronos",
        "subtitle": "WoW 3.3.5a WotLK",
        "description": "Living World сервер с динамическими событиями, караванами и системой поселений.",
        "realmlist": "set realmlist lkds-room.online",
        "exe_name": "wow.exe",  # relative to game_path
        "realmlist_paths": [
            "Data/ruRU/realmlist.wtf",
            "Data/enUS/realmlist.wtf",
            "realmlist.wtf",
        ],
        "default_locale": "ruRU",
        # HD patches — Gaame graphics pack
        # folder = "Data" or "Data/ruRU", filename = MPQ name
        "hd_patches": {
            # --- Data/ folder patches ---
            "hunter_traps": {
                "name": "HD Ловушки охотника",
                "description": "Обновленные ловушки с точным радиусом срабатывания",
                "folder": "Data", "files": ["patch-H.MPQ"],
                "category": "Модели оружия",
            },
            "weapon_m": {
                "name": "Серебряная длань",
                "description": "Замена 'Разрушитель из титановой стали'",
                "folder": "Data", "files": ["patch-M.mpq"],
                "category": "Модели оружия",
            },
            "weapon_l": {
                "name": "Закаленный молот рока",
                "description": "Замена 'Буздыхан разгневанного гладиатора'",
                "folder": "Data", "files": ["patch-L.mpq"],
                "category": "Модели оружия",
            },
            "weapon_p": {
                "name": "Артефакт паладина",
                "description": "Замена молота за очки чести",
                "folder": "Data", "files": ["patch-P.MPQ"],
                "category": "Модели оружия",
            },
            "weapon_k": {
                "name": "Оружие Логова Ониксии",
                "description": "Замена оружия из Логова Ониксии",
                "folder": "Data", "files": ["patch-K.MPQ"],
                "category": "Модели оружия",
            },
            "weapon_t": {
                "name": "Громовая Ярость (Легион)",
                "description": "Вариант клинка из Легиона",
                "folder": "Data", "files": ["patch-T.mpq"],
                "category": "Модели оружия",
            },
            "weapon_x": {
                "name": "Легендарка варлока (Легион)",
                "description": "Замена 'Пиритовый посох'",
                "folder": "Data", "files": ["patch-X.mpq"],
                "category": "Модели оружия",
            },
            "weapon_j": {
                "name": "Ултхалеш, жнец мертвого ветра",
                "description": "Замена 'Жар-Дуум, Великий посох Пожирателя'",
                "folder": "Data", "files": ["patch-J.mpq"],
                "category": "Модели оружия",
            },
            "equip_o": {
                "name": "Экипировка жреца/друида",
                "description": "Экипировка + Оскверненный испепелитель",
                "folder": "Data", "files": ["patch-O.mpq"],
                "category": "Модели оружия",
            },
            "weapon_w": {
                "name": "Доп. модели оружия (W)",
                "description": "Дополнительные модели оружия",
                "folder": "Data", "files": ["patch-W.MPQ"],
                "category": "Модели оружия",
            },
            # --- Data/ruRU/ patches ---
            "hd_textures_wotlk": {
                "name": "HD Текстуры WotLK",
                "description": "Улучшенные элементы и текстуры WotLK",
                "folder": "Data/ruRU", "files": ["patch-ruRU-4.MPQ"],
                "category": "HD Текстуры",
            },
            "hd_textures_classic": {
                "name": "HD Текстуры Classic/TBC",
                "description": "Улучшенные элементы и текстуры Classic и TBC",
                "folder": "Data/ruRU", "files": ["patch-ruRU-5.MPQ"],
                "category": "HD Текстуры",
            },
            "hd_dungeon_maps": {
                "name": "Карты Classic подземелий",
                "description": "Обновленные карты Classic подземелий",
                "folder": "Data/ruRU", "files": ["patch-ruRU-m.MPQ"],
                "category": "HD Текстуры",
            },
            "hd_models": {
                "name": "HD Модели персонажей и NPC",
                "description": "HD модели всех персонажей и NPC (~2 ГБ)",
                "folder": "Data/ruRU", "files": ["patch-ruRU-A.MPQ"],
                "category": "HD Модели",
            },
            "hd_creatures": {
                "name": "HD Модели существ и маунтов",
                "description": "HD модели существ и маунтов (оба файла связаны)",
                "folder": "Data/ruRU", "files": ["Patch-ruRU-F.MPQ", "Patch-ruRU-G.MPQ"],
                "category": "HD Модели",
            },
            "hd_armor": {
                "name": "Новые комплекты брони и оружия",
                "description": "Новые комплекты брони и оружия",
                "folder": "Data/ruRU", "files": ["patch-ruRU-O.mpq"],
                "category": "HD Модели",
            },
            "hd_animations": {
                "name": "HD Анимации способностей",
                "description": "Щит от Тотема каменного когтя, Молния, Экзорцизм, Танец теней",
                "folder": "Data/ruRU", "files": ["Patch-ruRU-P.mpq"],
                "category": "HD Эффекты",
            },
            "hd_water": {
                "name": "HD Текстура воды",
                "description": "Новая текстура воды",
                "folder": "Data/ruRU", "files": ["Patch-ruRU-V.mpq"],
                "category": "HD Эффекты",
            },
        },
        # Config.wtf graphic settings mapping
        "graphic_settings": {
            "gxResolution": {"label": "Разрешение", "type": "resolution"},
            "gxWindow": {"label": "Оконный режим", "type": "bool"},
            "gxVSync": {"label": "Вертикальная синхронизация", "type": "bool"},
            "gxMultisample": {"label": "Сглаживание (MSAA)", "type": "choice",
                              "options": ["1", "2", "4", "8"]},
            "groundEffectDensity": {"label": "Плотность травы", "type": "choice",
                                    "options": ["16", "64", "128", "256"]},
            "farclip": {"label": "Дальность прорисовки", "type": "choice",
                        "options": ["177", "357", "537", "777", "1277"]},
            "spellEffectLevel": {"label": "Эффекты заклинаний", "type": "choice",
                                 "options": ["0", "1", "2", "3", "4", "5", "6"]},
        },
        "torrent_url": "",  # set when torrent is ready
        "download_url": "",  # direct download fallback
    },
    # Example: add another game later
    # "survival": {
    #     "id": "survival",
    #     "name": "PLGames: Survival",
    #     ...
    # },
}

DEFAULT_GAME = "chronos"

# --- Local Settings ---
SETTINGS_FILE = "plgames_launcher_settings.json"


def get_app_dir():
    """Get the directory where the launcher exe (or script) lives.
    Works correctly for both PyInstaller frozen and normal Python."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_settings_path():
    """Settings file next to launcher exe."""
    return os.path.join(get_app_dir(), SETTINGS_FILE)


def load_settings():
    path = get_settings_path()
    defaults = {
        "game_paths": {},  # game_id -> path to game folder
        "active_game": DEFAULT_GAME,
        "hd_settings": {},  # game_id -> {patch_key: enabled}
    }
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)
                defaults.update(saved)
        except Exception:
            pass
    return defaults


def save_settings(settings: dict):
    path = get_settings_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Settings] Save failed: {e}")
