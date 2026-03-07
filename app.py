"""
PLGames Launcher v2.0 — Battle.net style
pywebview + HTML/CSS/JS backend
"""

import webview
import json
import os
import sys
import re
import subprocess
import uuid
import threading
import webbrowser

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

LAUNCHER_VERSION = "2.1.0"
API_BASE = "https://lkds-room.online"
API_AUTH = "https://lkds-room.online"  # port 3000 closed externally, proxied via main domain
MANIFEST_URL = f"{API_BASE}/api/launcher/manifest"
SETTINGS_FILE = "plgames_settings.json"

PROJECTS = [
    {
        "id": "wow_chronos",
        "name": "Chronos",
        "full_name": "Realm Chronos",
        "subtitle": "WotLK 3.3.5a",
        "type": "WoW Private Server",
        "description": {"ru": "Living World сервер с динамическими событиями, караванами, системой поселений.", "en": "Living World server with dynamic events, caravans, and settlement system."},
        "bg_images": [
            "https://wow.zamimg.com/uploads/screenshots/normal/522757-the-lich-king.jpg",
            "https://wow.zamimg.com/uploads/screenshots/normal/522115-icecrown-citadel.jpg",
            "https://wow.zamimg.com/uploads/screenshots/normal/323283-dalaran.jpg",
        ],
        "realmlist": "set realmlist lkds-room.online",
        "exe": "wow.exe",
        "realmlist_paths": ["Data/ruRU/realmlist.wtf", "Data/enUS/realmlist.wtf", "realmlist.wtf"],
        "news_url": f"{API_BASE}/api/content/phases",
        "status_url": f"{API_BASE}/api/status",
        "sso_start_url": f"{API_AUTH}/api/auth/sso/start",
        "sso_poll_url": f"{API_AUTH}/api/auth/sso/poll",
        "credentials_url": f"{API_AUTH}/api/auth/credentials",
        "reset_password_url": f"{API_AUTH}/api/auth/reset-password",
        "profile_url": f"{API_AUTH}/api/auth/profile",
        "news_feed_url": f"{API_BASE}/api/launcher/news",
        "hd_patches": {
            "patch-H.MPQ":  {"name": "HD Ловушки охотника", "cat": "weapon", "folder": "Data"},
            "patch-M.mpq":  {"name": "Серебряная длань", "cat": "weapon", "folder": "Data"},
            "patch-L.mpq":  {"name": "Закаленный молот рока", "cat": "weapon", "folder": "Data"},
            "patch-P.MPQ":  {"name": "Артефакт паладина", "cat": "weapon", "folder": "Data"},
            "patch-K.MPQ":  {"name": "Оружие Логова Ониксии", "cat": "weapon", "folder": "Data"},
            "patch-T.mpq":  {"name": "Громовая Ярость (Легион)", "cat": "weapon", "folder": "Data"},
            "patch-X.mpq":  {"name": "Легендарка варлока", "cat": "weapon", "folder": "Data"},
            "patch-J.mpq":  {"name": "Ултхалеш, жнец мертвого ветра", "cat": "weapon", "folder": "Data"},
            "patch-O.mpq":  {"name": "Экипировка жреца/друида", "cat": "weapon", "folder": "Data"},
            "patch-W.MPQ":  {"name": "Доп. модели оружия", "cat": "weapon", "folder": "Data"},
            "patch-ruRU-4.MPQ": {"name": "HD Текстуры WotLK", "cat": "texture", "folder": "Data/ruRU"},
            "patch-ruRU-5.MPQ": {"name": "HD Текстуры Classic/TBC", "cat": "texture", "folder": "Data/ruRU"},
            "patch-ruRU-m.MPQ": {"name": "Карты подземелий Classic", "cat": "texture", "folder": "Data/ruRU"},
            "patch-ruRU-A.MPQ": {"name": "HD Модели персонажей и NPC", "cat": "model", "folder": "Data/ruRU"},
            "Patch-ruRU-F.MPQ": {"name": "HD Существа и маунты (1/2)", "cat": "model", "folder": "Data/ruRU"},
            "Patch-ruRU-G.MPQ": {"name": "HD Существа и маунты (2/2)", "cat": "model", "folder": "Data/ruRU"},
            "patch-ruRU-O.mpq": {"name": "Новые комплекты брони", "cat": "model", "folder": "Data/ruRU"},
            "Patch-ruRU-P.mpq": {"name": "HD Анимации способностей", "cat": "fx", "folder": "Data/ruRU"},
            "Patch-ruRU-V.mpq": {"name": "HD Текстура воды", "cat": "fx", "folder": "Data/ruRU"},
        },
        "graphic_settings": {
            "gxResolution":       {"label": "Разрешение", "type": "res"},
            "gxWindow":           {"label": "Оконный режим", "type": "bool"},
            "gxVSync":            {"label": "V-Sync", "type": "bool"},
            "gxMultisample":      {"label": "Сглаживание", "type": "select", "opts": ["1","2","4","8"]},
            "groundEffectDensity":{"label": "Плотность травы", "type": "select", "opts": ["16","64","128","256"]},
            "farclip":            {"label": "Дальность прорисовки", "type": "select", "opts": ["177","357","537","777","1277"]},
            "spellEffectLevel":   {"label": "Эффекты заклинаний", "type": "select", "opts": ["0","1","2","3","4","5","6"]},
        },
    },
    {
        "id": "coming_soon",
        "name": "Новый проект",
        "full_name": "Скоро...",
        "subtitle": "В разработке",
        "type": "Coming Soon",
        "description": "Новый игровой проект PLGames. Следите за новостями!",
        "realmlist": "", "exe": "", "realmlist_paths": [],
        "news_url": "", "status_url": "",
        "hd_patches": {}, "graphic_settings": {},
    },
]

RESOLUTIONS = ["800x600","1024x768","1280x720","1280x1024","1366x768","1600x900","1920x1080","2560x1440","3840x2160"]

# ---------------------------------------------------------------------------
# MANIFEST (server-driven project list)
# ---------------------------------------------------------------------------

def fetch_manifest():
    """Fetch project manifest from server. Merges with local PROJECTS.
    Server provides: id, name, full_name, subtitle, type, description,
                     realmlist, exe, realmlist_paths, status_url, news_feed_url,
                     sso_start_url, sso_poll_url, credentials_url, reset_password_url,
                     profile_url, banners, news
    Local provides:  hd_patches, graphic_settings (client-side only)
    """
    try:
        import requests
        r = requests.get(MANIFEST_URL, timeout=5)
        if r.status_code == 200:
            data = r.json()
            server_projects = data.get("projects", [])
            if not server_projects:
                return PROJECTS

            # Build lookup of local projects for merging client-only fields
            local_map = {p["id"]: p for p in PROJECTS}
            merged = []
            for sp in server_projects:
                pid = sp.get("id", "")
                local = local_map.get(pid, {})
                proj = {
                    # Server fields (server wins)
                    "id": pid,
                    "name": sp.get("name", local.get("name", pid)),
                    "full_name": sp.get("full_name", local.get("full_name", "")),
                    "subtitle": sp.get("subtitle", local.get("subtitle", "")),
                    "type": sp.get("type", local.get("type", "")),
                    "description": sp.get("description", local.get("description", "")),
                    "bg_images": sp.get("bg_images", local.get("bg_images", [])),
                    "realmlist": sp.get("realmlist", local.get("realmlist", "")),
                    "exe": sp.get("exe", local.get("exe", "")),
                    "realmlist_paths": sp.get("realmlist_paths", local.get("realmlist_paths", [])),
                    "status_url": sp.get("status_url", local.get("status_url", "")),
                    "news_url": sp.get("news_url", local.get("news_url", "")),
                    "news_feed_url": sp.get("news_feed_url", local.get("news_feed_url", "")),
                    "sso_start_url": sp.get("sso_start_url", local.get("sso_start_url", "")),
                    "sso_poll_url": sp.get("sso_poll_url", local.get("sso_poll_url", "")),
                    "credentials_url": sp.get("credentials_url", local.get("credentials_url", "")),
                    "reset_password_url": sp.get("reset_password_url", local.get("reset_password_url", "")),
                    "profile_url": sp.get("profile_url", local.get("profile_url", "")),
                    # Server-only dynamic content
                    "banners": sp.get("banners", []),
                    "news": sp.get("news", []),
                    # Client-only fields (local wins)
                    "hd_patches": local.get("hd_patches", sp.get("hd_patches", {})),
                    "graphic_settings": local.get("graphic_settings", sp.get("graphic_settings", {})),
                }
                merged.append(proj)
            return merged
    except Exception:
        pass
    return PROJECTS

# ---------------------------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------------------------

def _settings_path():
    d = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(d, SETTINGS_FILE)

def load_settings():
    p = _settings_path()
    defaults = {"game_paths": {}, "active_project": "wow_chronos", "auth": {}}
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                defaults.update(json.load(f))
        except Exception:
            pass
    return defaults

def save_settings(s):
    try:
        with open(_settings_path(), "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# GAME UTILS
# ---------------------------------------------------------------------------

def set_realmlist(gp, val, paths):
    for rel in paths:
        full = os.path.join(gp, rel)
        if os.path.exists(full):
            try:
                with open(full, "w", encoding="utf-8") as f:
                    f.write(val + "\n")
                return
            except Exception:
                pass
    for rel in paths:
        full = os.path.join(gp, rel)
        d = os.path.dirname(full)
        if os.path.isdir(d):
            try:
                with open(full, "w", encoding="utf-8") as f:
                    f.write(val + "\n")
                return
            except Exception:
                pass

def read_config_wtf(gp):
    cfg = {}
    p = os.path.join(gp, "WTF", "Config.wtf")
    if not os.path.isfile(p): return cfg
    try:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                m = re.match(r'^SET\s+(\S+)\s+"?([^"]*)"?\s*$', line.strip())
                if m: cfg[m.group(1)] = m.group(2)
    except Exception:
        pass
    return cfg

def write_config_wtf(gp, settings):
    p = os.path.join(gp, "WTF", "Config.wtf")
    lines, written = [], set()
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    m = re.match(r'^SET\s+(\S+)\s+', line.strip())
                    if m and m.group(1) in settings:
                        k = m.group(1)
                        lines.append(f'SET {k} "{settings[k]}"\n')
                        written.add(k)
                    else:
                        lines.append(line if line.endswith("\n") else line + "\n")
        except Exception:
            pass
    for k, v in settings.items():
        if k not in written:
            lines.append(f'SET {k} "{v}"\n')
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception:
        pass

def detect_game_path():
    d = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):
        if os.path.isfile(os.path.join(d, "wow.exe")) or os.path.isfile(os.path.join(d, "Wow.exe")):
            return d
        d = os.path.dirname(d)
    return None

def mpq_status(gp, fname, folder):
    base = os.path.join(gp, folder)
    active = os.path.join(base, fname)
    disabled = active + ".disabled"
    if os.path.isfile(active):
        return True, True, round(os.path.getsize(active)/1048576, 1)
    if os.path.isfile(disabled):
        return True, False, round(os.path.getsize(disabled)/1048576, 1)
    return False, False, 0

def toggle_mpq(gp, fname, folder, enable):
    base = os.path.join(gp, folder)
    active = os.path.join(base, fname)
    disabled = active + ".disabled"
    try:
        if enable and os.path.isfile(disabled):
            os.rename(disabled, active)
        elif not enable and os.path.isfile(active):
            os.rename(active, disabled)
        return True
    except Exception:
        return False

# ---------------------------------------------------------------------------
# JS API (exposed to webview)
# ---------------------------------------------------------------------------

class Api:
    def __init__(self):
        self.settings = load_settings()
        self.window = None
        self.projects = fetch_manifest()

    def get_projects(self):
        return json.dumps([{
            "id": p["id"], "name": p["name"], "full_name": p["full_name"],
            "subtitle": p["subtitle"], "type": p["type"], "description": p["description"],
            "has_exe": bool(p.get("exe")),
        } for p in self.projects])

    def refresh_manifest(self):
        """Re-fetch manifest from server (called from JS to refresh)."""
        self.projects = fetch_manifest()
        return self.get_projects()

    def get_active_project(self):
        return self.settings.get("active_project", "wow_chronos")

    def set_active_project(self, pid):
        self.settings["active_project"] = pid
        save_settings(self.settings)

    def get_game_path(self, pid):
        p = self.settings.get("game_paths", {}).get(pid, "")
        if not p:
            detected = detect_game_path()
            if detected:
                self.settings.setdefault("game_paths", {})[pid] = detected
                save_settings(self.settings)
                return detected
        return p

    def browse_game_path(self, pid):
        result = self.window.create_file_dialog(webview.FOLDER_DIALOG)
        if result and len(result) > 0:
            path = result[0]
            self.settings.setdefault("game_paths", {})[pid] = path
            save_settings(self.settings)
            return path
        return ""

    def launch_game(self, pid):
        proj = next((p for p in self.projects if p["id"] == pid), None)
        if not proj or not proj.get("exe"):
            return json.dumps({"ok": False, "msg": "Нет исполняемого файла"})

        gp = self.settings.get("game_paths", {}).get(pid, "")
        if not gp or not os.path.isdir(gp):
            return json.dumps({"ok": False, "msg": "Укажите папку с игрой"})

        if proj.get("realmlist"):
            set_realmlist(gp, proj["realmlist"], proj["realmlist_paths"])

        exe = os.path.join(gp, proj["exe"])
        if not os.path.isfile(exe):
            exe2 = os.path.join(gp, proj["exe"].capitalize())
            if os.path.isfile(exe2):
                exe = exe2
            else:
                return json.dumps({"ok": False, "msg": f"{proj['exe']} не найден"})

        try:
            subprocess.Popen([exe], cwd=gp)
            return json.dumps({"ok": True, "msg": "Игра запущена!"})
        except Exception as e:
            return json.dumps({"ok": False, "msg": str(e)})

    def get_server_status(self, pid):
        proj = next((p for p in self.projects if p["id"] == pid), None)
        if not proj or not proj.get("status_url"):
            return json.dumps({"online": None, "players": 0, "accounts": 0})
        try:
            import requests
            r = requests.get(proj["status_url"], timeout=5)
            if r.status_code == 200:
                data = r.json()
                # /api/status returns {"online": <count>, "accounts": <count>}
                return json.dumps({
                    "online": True,
                    "players": data.get("online", 0),
                    "accounts": data.get("accounts", 0),
                })
        except Exception:
            pass
        return json.dumps({"online": None, "players": 0, "accounts": 0})

    def get_news(self, pid):
        proj = next((p for p in self.projects if p["id"] == pid), None)
        if proj and proj.get("news_url"):
            try:
                import requests
                r = requests.get(proj["news_url"], timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    # Convert phases to news-like items
                    news = []
                    news.append({
                        "tag": "Анонс",
                        "title": f"Realm Chronos — День {data.get('server_day', '?')}",
                        "text": f"Фаза {data.get('current_phase', 1)} из {data.get('total_phases', 6)}. Запуск: {data.get('launch_date', '?')}",
                        "date": data.get("launch_date", ""),
                    })
                    for phase in data.get("phases", []):
                        status = "Открыто" if phase.get("unlocked") else f"Через {phase.get('days_remaining', '?')} дн."
                        zones = ", ".join(z["name"] if isinstance(z, dict) else str(z) for z in phase.get("zones", [])) or "—"
                        dungeons = ", ".join(d["name"] if isinstance(d, dict) else str(d) for d in phase.get("dungeons", [])) or "—"
                        raids = ", ".join(r["name"] if isinstance(r, dict) else str(r) for r in phase.get("raids", [])) or "—"
                        tag = "Событие" if phase.get("unlocked") else "Обновление"
                        news.append({
                            "tag": tag,
                            "title": f"Фаза {phase.get('phase', '?')} — {status}",
                            "text": f"Зоны: {zones}. Подземелья: {dungeons}. Рейды: {raids}. Дата: {phase.get('unlock_date', '?')}",
                            "date": phase.get("unlock_date", ""),
                        })
                    return json.dumps({"news": news})
            except Exception:
                pass
        # Fallback
        return json.dumps({"news": [
            {"tag": "Анонс", "title": "Realm Chronos", "text": "THE FROZEN THRONE AWAITS", "date": "2026-03-07"},
        ]})

    def get_news_feed(self, pid):
        """Fetch dynamic news feed: banners + news.
        Priority: 1) manifest data  2) news_feed_url  3) phases fallback"""
        proj = next((p for p in self.projects if p["id"] == pid), None)
        if not proj:
            return json.dumps({"banners": [], "news": []})

        # 1) If manifest already loaded banners/news, use them
        if proj.get("banners") or proj.get("news"):
            banners = proj.get("banners", [])
            news = proj.get("news", [])
            # Supplement banners from bg_images if manifest had none
            if not banners:
                banners = [{"image": img} for img in proj.get("bg_images", [])]
            return json.dumps({"banners": banners, "news": news})

        # 2) Try dedicated news feed endpoint
        feed_url = proj.get("news_feed_url", "")
        if feed_url:
            try:
                import requests
                r = requests.get(feed_url, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    return json.dumps({
                        "banners": data.get("banners", []),
                        "news": data.get("news", []),
                    })
            except Exception:
                pass

        # 3) Fallback: build from phases + static banners
        banners = [{"image": img} for img in proj.get("bg_images", [])]
        news_data = json.loads(self.get_news(pid))
        return json.dumps({
            "banners": banners,
            "news": news_data.get("news", []),
        })

    def get_hd_patches(self, pid):
        proj = next((p for p in self.projects if p["id"] == pid), None)
        gp = self.settings.get("game_paths", {}).get(pid, "")
        if not proj or not gp or not os.path.isdir(gp):
            return json.dumps([])
        result = []
        cats = {"weapon": "Модели оружия", "texture": "HD Текстуры", "model": "HD Модели", "fx": "HD Эффекты"}
        for fname, info in proj.get("hd_patches", {}).items():
            installed, enabled, size = mpq_status(gp, fname, info["folder"])
            result.append({
                "file": fname, "name": info["name"],
                "cat": cats.get(info["cat"], info["cat"]),
                "folder": info["folder"],
                "installed": installed, "enabled": enabled, "size": size,
            })
        return json.dumps(result)

    def toggle_hd_patch(self, pid, fname, folder, enable):
        gp = self.settings.get("game_paths", {}).get(pid, "")
        if not gp: return json.dumps(False)
        return json.dumps(toggle_mpq(gp, fname, folder, enable))

    def get_graphic_settings(self, pid):
        proj = next((p for p in self.projects if p["id"] == pid), None)
        gp = self.settings.get("game_paths", {}).get(pid, "")
        if not proj or not gp: return json.dumps({"defs": {}, "current": {}})
        return json.dumps({"defs": proj.get("graphic_settings", {}), "current": read_config_wtf(gp)})

    def save_graphic_settings(self, pid, settings_json):
        gp = self.settings.get("game_paths", {}).get(pid, "")
        if not gp: return
        settings = json.loads(settings_json)
        write_config_wtf(gp, settings)

    # ---- AUTH (Telegram SSO) ----

    def get_auth_state(self):
        """Return saved auth info, validating token with server if available."""
        auth = self.settings.get("auth", {})
        token = auth.get("token", "")
        if token:
            # Validate token against server
            proj = next((p for p in self.projects if p["id"] == self.settings.get("active_project")), None)
            if proj:
                try:
                    import requests
                    r = requests.get(proj["profile_url"], headers={
                        "Authorization": f"Bearer {token}"
                    }, timeout=5)
                    if r.status_code == 200:
                        data = r.json()
                        # Update stored auth with fresh server data
                        auth["username"] = data.get("username", auth.get("username", ""))
                        auth["account_id"] = data.get("accountId", auth.get("account_id"))
                        auth["first_name"] = data.get("firstName", auth.get("first_name", ""))
                        self.settings["auth"] = auth
                        save_settings(self.settings)
                        return json.dumps({
                            "logged_in": True,
                            "username": auth["username"],
                            "account_id": auth.get("account_id"),
                            "first_name": auth.get("first_name", ""),
                        })
                    elif r.status_code == 401:
                        # Token expired/invalid — clear auth
                        self.settings["auth"] = {}
                        save_settings(self.settings)
                        return json.dumps({"logged_in": False})
                except Exception:
                    # Network error — trust local data
                    pass
            # Fallback: return local data if network failed
            if auth.get("username"):
                return json.dumps({
                    "logged_in": True,
                    "username": auth["username"],
                    "account_id": auth.get("account_id"),
                    "first_name": auth.get("first_name", ""),
                })
        return json.dumps({"logged_in": False})

    def sso_start(self):
        """Start Telegram SSO — returns botLink to open."""
        proj = next((p for p in self.projects if p["id"] == self.settings.get("active_project")), None)
        if not proj:
            return json.dumps({"ok": False, "msg": "No project"})
        try:
            import requests
            r = requests.post(proj["sso_start_url"], timeout=10)
            if r.status_code == 200:
                data = r.json()
                self._sso_session_id = data.get("sessionId")
                bot_link = data.get("botLink", "")
                if bot_link:
                    webbrowser.open(bot_link)
                return json.dumps({"ok": True, "sessionId": self._sso_session_id})
        except Exception as e:
            return json.dumps({"ok": False, "msg": f"SSO сервис недоступен: {e}"})
        return json.dumps({"ok": False, "msg": "Не удалось начать авторизацию"})

    def sso_poll(self):
        """Poll SSO status. Returns status + user data on completion."""
        if not getattr(self, '_sso_session_id', None):
            return json.dumps({"status": "error", "msg": "No session"})
        proj = next((p for p in self.projects if p["id"] == self.settings.get("active_project")), None)
        if not proj:
            return json.dumps({"status": "error", "msg": "No project"})
        try:
            import requests
            url = f"{proj['sso_poll_url']}/{self._sso_session_id}"
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "completed" and data.get("success"):
                    # Save auth — token field per final spec
                    auth = {
                        "username": data.get("username", ""),
                        "account_id": data.get("account_id"),
                        "token": data.get("token", ""),
                        "first_name": data.get("first_name", ""),
                    }
                    if data.get("is_new") and data.get("password"):
                        auth["password"] = data["password"]
                    self.settings["auth"] = auth
                    save_settings(self.settings)
                    self._sso_session_id = None
                    return json.dumps({
                        "status": "completed",
                        "username": auth["username"],
                        "account_id": auth["account_id"],
                        "first_name": auth["first_name"],
                        "is_new": data.get("is_new", False),
                        "password": data.get("password", ""),
                    })
                return json.dumps({"status": data.get("status", "pending")})
        except Exception as e:
            return json.dumps({"status": "error", "msg": str(e)})
        return json.dumps({"status": "error", "msg": "Poll failed"})

    def fetch_credentials(self):
        """Fetch realmlist + account info and auto-write realmlist."""
        auth = self.settings.get("auth", {})
        if not auth.get("username"):
            return json.dumps({"ok": False, "msg": "Not logged in"})
        proj = next((p for p in self.projects if p["id"] == self.settings.get("active_project")), None)
        if not proj:
            return json.dumps({"ok": False})
        try:
            import requests
            r = requests.get(proj["credentials_url"], params={
                "username": auth["username"],
                "account_id": auth["account_id"],
            }, timeout=5)
            if r.status_code == 200:
                data = r.json()
                realmlist_val = data.get("realmlist", proj.get("realmlist", ""))
                # Auto-write realmlist if game path is set
                gp = self.settings.get("game_paths", {}).get(proj["id"], "")
                if gp and os.path.isdir(gp):
                    set_realmlist(gp, realmlist_val, proj["realmlist_paths"])
                return json.dumps({"ok": True, "realmlist": realmlist_val})
        except Exception:
            pass
        return json.dumps({"ok": False})

    def logout(self):
        """Clear saved auth."""
        self.settings["auth"] = {}
        save_settings(self.settings)
        return json.dumps({"ok": True})

    def reset_password(self):
        """Request password reset via Bearer token."""
        auth = self.settings.get("auth", {})
        token = auth.get("token", "")
        if not token:
            return json.dumps({"ok": False, "msg": "Нет токена. Войдите снова."})
        proj = next((p for p in self.projects if p["id"] == self.settings.get("active_project")), None)
        if not proj:
            return json.dumps({"ok": False, "msg": "No project"})
        try:
            import requests
            r = requests.post(proj["reset_password_url"], headers={
                "Authorization": f"Bearer {token}"
            }, timeout=10)
            if r.status_code == 200:
                return json.dumps({"ok": True, "msg": "Пароль сброшен. Проверьте Telegram."})
            elif r.status_code == 401:
                self.settings["auth"] = {}
                save_settings(self.settings)
                return json.dumps({"ok": False, "msg": "Токен истёк. Войдите снова."})
        except Exception as e:
            return json.dumps({"ok": False, "msg": str(e)})
        return json.dumps({"ok": False, "msg": "Ошибка сброса пароля"})

    def get_version(self):
        return LAUNCHER_VERSION

    def minimize_window(self):
        self.window.minimize()

    def maximize_window(self):
        if self.window.maximized:
            self.window.restore()
        else:
            self.window.maximize()

    def close_window(self):
        self.window.destroy()

# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;500;600;700;800;900&family=Inter:wght@300;400;500;600;700;800;900&display=swap');

*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#1a1c23; --bg-dark:#15171e; --bg-darker:#101218;
  --topbar:#1e2028; --topbar-border:#2a2d38;
  --card:rgba(30,33,42,0.9); --card-hover:rgba(38,42,54,0.95);
  --accent:#00aeff; --accent-dark:#0088cc; --accent-glow:rgba(0,174,255,0.15);
  --blue-btn:#148eff; --blue-btn-h:#1e9bff;
  --text:#e8eaed; --text-sec:#8b8d94; --text-dim:#55575e;
  --green:#4ade80; --red:#ef4444; --orange:#f59e0b;
  --border:rgba(255,255,255,0.06); --border-l:rgba(255,255,255,0.1);
  --shadow:0 2px 16px rgba(0,0,0,0.4);
}
html,body{height:100%;overflow:hidden;font-family:'Inter',system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);-webkit-font-smoothing:antialiased;user-select:none}

/* ===== TOPBAR (combined titlebar + nav — DRAGGABLE) ===== */
.topbar{
  display:flex;align-items:center;height:48px;background:var(--topbar);
  border-bottom:1px solid var(--topbar-border);padding:0 0 0 16px;
  z-index:200;position:relative;
}
.topbar-logo{
  display:flex;align-items:center;gap:8px;margin-right:24px;cursor:default;
}
.topbar-logo svg{width:26px;height:26px;fill:var(--accent)}
.topbar-logo span{font-size:15px;font-weight:800;color:var(--text);letter-spacing:2px;font-family:'Cinzel',serif}
.topbar-nav{display:flex;gap:2px}
.topbar-nav-btn{
  padding:14px 18px;border:none;background:transparent;color:var(--text-sec);
  font-size:13px;font-weight:600;cursor:pointer;font-family:inherit;
  transition:all .2s;position:relative;letter-spacing:0.3px;
}
.topbar-nav-btn:hover{color:var(--text)}
.topbar-nav-btn.active{color:#fff}
.topbar-nav-btn.active::after{
  content:'';position:absolute;bottom:0;left:12px;right:12px;height:2px;
  background:var(--accent);border-radius:1px;
}
.topbar-right{display:flex;align-items:center;gap:4px}
.topbar-icon-btn{
  width:36px;height:36px;border:none;background:transparent;color:var(--text-sec);
  border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;
  transition:all .15s;
}
.topbar-icon-btn:hover{background:rgba(255,255,255,0.08);color:var(--text)}
.topbar-btns{display:flex}
.topbar-wbtn{
  width:46px;height:48px;border:none;background:transparent;color:var(--text-sec);
  cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .15s;
}
.topbar-wbtn:hover{background:rgba(255,255,255,0.08);color:var(--text)}
.topbar-wbtn.close:hover{background:#c42b1c;color:#fff}

/* ===== GAME ICON BAR ===== */
.game-bar{
  display:flex;align-items:center;height:52px;background:var(--bg-dark);
  border-bottom:1px solid var(--border);padding:0 16px;gap:2px;
  overflow-x:auto;flex-shrink:0;
}
.game-bar::-webkit-scrollbar{display:none}
.game-bar-btn{
  width:44px;height:44px;border:none;background:transparent;border-radius:8px;
  cursor:pointer;display:flex;align-items:center;justify-content:center;
  transition:all .2s;position:relative;flex-shrink:0;
}
.game-bar-btn:hover{background:rgba(255,255,255,0.06)}
.game-bar-btn.active{background:rgba(0,174,255,0.1)}
.game-bar-btn.active::after{
  content:'';position:absolute;bottom:2px;left:10px;right:10px;height:2px;
  background:var(--accent);border-radius:1px;
}
.game-bar-icon{
  width:32px;height:32px;border-radius:6px;display:flex;align-items:center;justify-content:center;
  font-size:14px;font-weight:800;color:#fff;
  background:linear-gradient(135deg,#1e3a5f,#2d5a87);
  text-shadow:0 1px 2px rgba(0,0,0,0.5);
}
.game-bar-icon.soon{background:linear-gradient(135deg,#333,#555);color:#999}

/* ===== MAIN LAYOUT ===== */
.main-wrap{display:flex;height:calc(100vh - 48px - 52px);overflow:hidden}

/* ===== LEFT: GAME PAGE ===== */
.game-left{
  display:flex;flex-direction:column;flex:1;overflow:hidden;position:relative;
  min-width:0;
}

/* ===== HERO BANNER ===== */
.hero-area{
  flex:1;position:relative;overflow:hidden;
  background:var(--bg-dark);min-height:0;
}
.hero-bg{
  position:absolute;inset:0;background-size:cover;background-position:center top;
  transition:opacity 0.8s ease;z-index:1;
}
.hero-overlay{
  position:absolute;inset:0;z-index:2;
  background:linear-gradient(to right,rgba(20,22,28,0.92) 0%,rgba(20,22,28,0.5) 35%,rgba(20,22,28,0.05) 55%,rgba(20,22,28,0.4) 100%);
}
.hero-overlay-bottom{
  position:absolute;left:0;right:0;bottom:0;height:80px;z-index:2;
  background:linear-gradient(to top,var(--bg-dark),transparent);
}

/* Left side content over hero */
.hero-left{
  position:absolute;left:0;top:0;bottom:0;width:260px;z-index:10;
  display:flex;flex-direction:column;padding:28px 24px 20px;
}
.game-logo-title{
  font-size:20px;font-weight:900;color:#fff;line-height:1.15;
  text-shadow:0 2px 12px rgba(0,0,0,0.7);margin-bottom:4px;font-family:'Cinzel',serif;
}
.game-logo-sub{font-size:11px;color:rgba(255,255,255,0.6);font-weight:600;margin-bottom:16px}
.hero-sidebar-btn{
  display:flex;align-items:center;gap:10px;padding:8px 10px;border:none;
  background:transparent;color:rgba(255,255,255,0.6);font-size:12px;font-weight:500;
  border-radius:5px;cursor:pointer;font-family:inherit;transition:all .15s;text-align:left;
  margin-bottom:1px;
}
.hero-sidebar-btn:hover{background:rgba(255,255,255,0.08);color:#fff}
.hero-sidebar-btn svg{width:15px;height:15px;opacity:0.5;flex-shrink:0}

/* Right side content over hero */
.hero-right{
  position:absolute;right:24px;top:50%;transform:translateY(-50%);
  max-width:340px;z-index:10;
}
.hero-badge{
  display:inline-flex;align-items:center;gap:6px;
  font-size:10px;font-weight:700;color:var(--accent);letter-spacing:1px;
  text-transform:uppercase;margin-bottom:10px;
}
.hero-badge svg{width:14px;height:14px;fill:var(--accent)}
.hero-title{font-size:22px;font-weight:800;color:#fff;line-height:1.25;margin-bottom:10px;
  text-shadow:0 2px 8px rgba(0,0,0,0.5);font-family:'Cinzel',serif}
.hero-text{font-size:12.5px;color:rgba(255,255,255,0.7);line-height:1.6}

/* Hero slide indicators */
.hero-indicators{
  position:absolute;bottom:16px;left:50%;transform:translateX(-50%);
  display:flex;gap:6px;z-index:10;
}
.hero-ind{
  width:40px;height:3px;border-radius:2px;background:rgba(255,255,255,0.2);
  cursor:pointer;transition:all .3s;overflow:hidden;position:relative;
}
.hero-ind.active{background:rgba(255,255,255,0.35)}
.hero-ind.active .hero-ind-fill{
  position:absolute;left:0;top:0;bottom:0;background:var(--accent);
  animation:indFill 6s linear forwards;
}
@keyframes indFill{from{width:0}to{width:100%}}

/* ===== NEWS CARDS ROW ===== */
.news-row{
  display:flex;gap:10px;padding:12px 16px;background:var(--bg-dark);
  border-top:1px solid var(--border);flex-shrink:0;overflow-x:auto;
  min-height:140px;
}
.news-row::-webkit-scrollbar{display:none}
.news-row:empty{min-height:0;padding:0;border:none}
.news-card-mini{
  flex:1;min-width:180px;max-width:260px;border-radius:8px;overflow:hidden;
  background:var(--card);cursor:pointer;transition:all .2s;border:1px solid var(--border);
}
.news-card-mini:hover{border-color:var(--border-l);transform:translateY(-2px)}
.news-card-img{
  height:80px;background-size:cover;background-position:center;
  background-color:rgba(255,255,255,0.03);
}
.news-card-body{padding:8px 10px}
.news-card-tag{font-size:8px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:3px}
.news-card-title{font-size:11px;font-weight:700;color:var(--text);line-height:1.3}

/* ===== PLAY BAR (bottom) ===== */
.play-bar{
  display:flex;align-items:center;height:72px;padding:0 20px;
  background:var(--bg-darker);border-top:1px solid var(--border);
  flex-shrink:0;gap:16px;
}
.play-version{display:flex;flex-direction:column;gap:2px}
.play-version-label{font-size:8px;font-weight:600;color:var(--text-dim);text-transform:uppercase;letter-spacing:1px}
.play-version-select{
  appearance:none;background:var(--bg);border:1px solid var(--border);color:var(--text-sec);
  padding:5px 26px 5px 10px;border-radius:4px;font-size:11px;font-family:inherit;font-weight:500;
  cursor:pointer;outline:none;transition:border-color .2s;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='5'%3E%3Cpath d='M0 0l4 5 4-5z' fill='%2355575e'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 8px center;
}
.play-version-select:hover{border-color:var(--border-l)}
.play-msg{flex:1;font-size:11px;color:var(--text-sec);text-align:right;padding-right:8px}
.play-settings-btn{
  width:40px;height:40px;border:1px solid var(--border);background:var(--bg);
  border-radius:6px;color:var(--text-sec);cursor:pointer;
  display:flex;align-items:center;justify-content:center;transition:all .15s;flex-shrink:0;
}
.play-settings-btn:hover{background:rgba(255,255,255,0.05);color:var(--text);border-color:var(--border-l)}
.btn-play{
  padding:0 44px;height:44px;font-size:15px;font-weight:800;
  border-radius:6px;border:none;cursor:pointer;
  background:var(--blue-btn);color:#fff;
  letter-spacing:2px;text-transform:uppercase;font-family:inherit;
  transition:all .2s;position:relative;overflow:hidden;flex-shrink:0;
}
.btn-play::before{
  content:'';position:absolute;inset:0;
  background:linear-gradient(135deg,transparent 30%,rgba(255,255,255,0.1) 50%,transparent 70%);
  background-size:200% 100%;animation:btnShine 3s ease infinite;
}
@keyframes btnShine{0%{background-position:200% 0}100%{background-position:-200% 0}}
.btn-play:hover{background:var(--blue-btn-h);transform:translateY(-1px);box-shadow:0 4px 20px rgba(20,142,255,0.3)}
.btn-play:active{transform:translateY(0)}
.btn-play:disabled{opacity:0.4;cursor:default;transform:none;box-shadow:none}
.btn-play:disabled::before{display:none}
.btn-play.coming{background:#2a2d38;color:var(--text-dim);letter-spacing:3px}
.btn-play.coming::before{display:none}

/* ===== RIGHT PANEL (server info / social) ===== */
.right-panel{
  width:250px;min-width:250px;background:var(--bg-dark);
  border-left:1px solid var(--border);display:flex;flex-direction:column;
  overflow-y:auto;flex-shrink:0;
}
.right-panel::-webkit-scrollbar{width:4px}
.right-panel::-webkit-scrollbar-track{background:transparent}
.right-panel::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.08);border-radius:2px}
.rp-section{padding:16px;border-bottom:1px solid var(--border)}
.rp-section:last-child{border-bottom:none}
.rp-header{
  display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;
}
.rp-title{font-size:10px;font-weight:700;color:var(--text-sec);text-transform:uppercase;letter-spacing:0.5px}

/* Server status card */
.server-card{
  background:var(--card);border:1px solid var(--border);border-radius:8px;
  padding:12px;
}
.server-row{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.server-row:last-child{margin-bottom:0}
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;transition:all .3s}
.dot-check{background:var(--text-dim)}
.dot-on{background:var(--green);box-shadow:0 0 8px var(--green);animation:pulse 2s ease-in-out infinite}
.dot-off{background:var(--red);box-shadow:0 0 6px var(--red)}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.7;transform:scale(1.3)}}
.server-name{font-size:12px;font-weight:600;color:var(--text)}
.server-info{font-size:10px;color:var(--text-dim);margin-left:auto}
.server-detail{font-size:11px;color:var(--text-sec);display:flex;align-items:center;gap:6px}
.server-detail svg{width:12px;height:12px;opacity:0.5}

/* Path card */
.path-card{
  background:var(--card);border:1px solid var(--border);border-radius:8px;
  padding:10px;
}
.path-val{font-size:11px;color:var(--text-sec);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-bottom:8px}
.path-browse{
  width:100%;padding:6px;border:1px solid var(--border);background:transparent;
  color:var(--text-sec);border-radius:4px;font-size:11px;font-weight:600;
  cursor:pointer;font-family:inherit;transition:all .15s;
}
.path-browse:hover{background:rgba(255,255,255,0.04);border-color:var(--border-l);color:var(--text)}

/* ===== FULL-PAGE VIEWS (news, settings) ===== */
.page-view{display:none;flex-direction:column;height:100%;overflow-y:auto}
.page-view.active{display:flex}
.page-view::-webkit-scrollbar{width:5px}
.page-view::-webkit-scrollbar-track{background:transparent}
.page-view::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.08);border-radius:3px}

.main-view{display:flex;flex-direction:column;height:100%}
.main-view.hidden{display:none}

/* News full page */
.news-full{padding:24px 28px}
.news-full-title{font-size:20px;font-weight:800;color:#fff;margin-bottom:16px}
.news-grid{display:flex;flex-direction:column;gap:10px}
.news-card-full{
  background:var(--card);border:1px solid var(--border);border-radius:10px;
  overflow:hidden;transition:all .2s;cursor:default;
}
.news-card-full-img{
  width:100%;height:140px;background-size:cover;background-position:center;
}
.news-card-full .news-top,.news-card-full h3,.news-card-full p{padding:0 20px}
.news-card-full .news-top{padding-top:16px}
.news-card-full p{padding-bottom:16px}
.news-card-full:hover{border-color:var(--border-l);transform:translateY(-1px)}
.news-top{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.news-tag{font-size:9px;font-weight:700;padding:3px 10px;border-radius:4px;text-transform:uppercase;letter-spacing:0.5px}
.tag-announce{background:rgba(255,165,0,0.15);color:#ffa500}
.tag-update{background:rgba(74,222,128,0.15);color:var(--green)}
.tag-fix{background:rgba(239,68,68,0.15);color:var(--red)}
.tag-event{background:rgba(0,174,255,0.15);color:var(--accent)}
.news-date{font-size:10px;color:var(--text-dim);margin-left:auto}
.news-card-full h3{font-size:14px;font-weight:700;color:var(--text);margin-bottom:4px}
.news-card-full p{font-size:12px;color:var(--text-sec);line-height:1.6}

/* Settings full page */
.settings-full{padding:24px 28px}
.settings-full-title{font-size:20px;font-weight:800;color:#fff;margin-bottom:16px}
.settings-section{
  background:var(--card);border:1px solid var(--border);border-radius:10px;
  padding:16px 20px;margin-bottom:10px;
}
.settings-section h3{
  font-size:12px;font-weight:700;color:var(--accent);margin-bottom:10px;
  padding-bottom:8px;border-bottom:1px solid var(--border);letter-spacing:0.3px;
}
.setting-row{
  display:flex;align-items:center;justify-content:space-between;
  padding:7px 0;border-bottom:1px solid rgba(255,255,255,0.03);transition:background .15s;
}
.setting-row:last-child{border-bottom:none}
.setting-row:hover{background:rgba(255,255,255,0.02)}
.setting-label{font-size:12px;color:var(--text);font-weight:500}
.setting-info{font-size:10px;color:var(--text-dim);font-weight:500}
.setting-right{display:flex;align-items:center;gap:10px}

.toggle{position:relative;width:40px;height:22px;cursor:pointer}
.toggle input{display:none}
.toggle .slider{
  position:absolute;inset:0;background:var(--text-dim);border-radius:11px;transition:all .3s;
}
.toggle .slider:before{
  content:'';position:absolute;width:16px;height:16px;border-radius:50%;
  background:#fff;left:3px;top:3px;transition:all .3s;box-shadow:0 1px 3px rgba(0,0,0,0.3);
}
.toggle input:checked+.slider{background:var(--blue-btn)}
.toggle input:checked+.slider:before{transform:translateX(18px)}

.setting-select{
  appearance:none;background:var(--bg);border:1px solid var(--border);color:var(--text);
  padding:6px 24px 6px 10px;border-radius:4px;font-size:11px;font-family:inherit;font-weight:500;
  outline:none;cursor:pointer;transition:all .2s;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='5'%3E%3Cpath d='M0 0l4 5 4-5z' fill='%2355575e'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 8px center;
}
.setting-select:hover{border-color:var(--border-l)}
.setting-select option{background:var(--bg);color:var(--text)}

.btn-save{
  margin-top:12px;padding:8px 22px;font-size:12px;font-weight:700;
  background:var(--blue-btn);color:#fff;border:none;border-radius:6px;
  cursor:pointer;transition:all .2s;letter-spacing:0.3px;
}
.btn-save:hover{background:var(--blue-btn-h);transform:translateY(-1px)}

/* Auth section */
.btn-auth{
  width:100%;padding:10px 14px;border:1px solid rgba(0,174,255,0.3);background:rgba(0,174,255,0.08);
  color:var(--accent);border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;
  font-family:inherit;transition:all .2s;display:flex;align-items:center;gap:8px;justify-content:center;
}
.btn-auth:hover{background:rgba(0,174,255,0.15);border-color:rgba(0,174,255,0.5)}
.auth-user-card{
  background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px;
}
.auth-user-name{font-size:14px;font-weight:700;color:#fff;margin-bottom:2px}
.auth-user-id{font-size:10px;color:var(--text-dim);margin-bottom:8px}
.auth-user-actions{display:flex;gap:6px}
.auth-action-btn{
  flex:1;padding:6px 8px;border:1px solid var(--border);background:transparent;
  color:var(--text-sec);border-radius:4px;font-size:10px;font-weight:600;
  cursor:pointer;font-family:inherit;transition:all .15s;
}
.auth-action-btn:hover{background:rgba(255,255,255,0.04);border-color:var(--border-l);color:var(--text)}
.auth-action-btn.logout{color:var(--red);border-color:rgba(239,68,68,0.2)}
.auth-action-btn.logout:hover{background:rgba(239,68,68,0.08);border-color:rgba(239,68,68,0.4)}
.auth-polling-card{
  background:var(--card);border:1px solid var(--border);border-radius:8px;
  padding:16px;text-align:center;
}
.auth-polling-spinner{
  width:24px;height:24px;border:3px solid var(--border);border-top-color:var(--accent);
  border-radius:50%;animation:spin 1s linear infinite;margin:0 auto 8px;
}
@keyframes spin{to{transform:rotate(360deg)}}
.auth-polling-text{font-size:11px;color:var(--text-sec);margin-bottom:10px}
.auth-new-card{
  background:rgba(74,222,128,0.06);border:1px solid rgba(74,222,128,0.2);
  border-radius:8px;padding:12px;
}
.auth-new-title{font-size:12px;font-weight:700;color:var(--green);margin-bottom:6px}
.auth-new-info{font-size:12px;color:var(--text);margin-bottom:2px}
.auth-new-info b{color:#fff;user-select:text}
.auth-new-hint{font-size:10px;color:var(--orange);margin:6px 0 8px}

/* Animations */
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
.fade-in{animation:fadeIn .3s ease}
</style>
</head>
<body>

<!-- TOPBAR (combined: drag area + nav + window buttons) -->
<div class="topbar">
  <div class="topbar-logo">
    <span style="font-size:22px">&#9876;</span>
    <span>REALM CHRONOS</span>
  </div>
  <div class="topbar-nav pywebview-no-drag">
    <button class="topbar-nav-btn active" data-page="games" onclick="showPage('games')">ИГРАТЬ</button>
    <button class="topbar-nav-btn" data-page="news" onclick="showPage('news')">НОВОСТИ</button>
    <button class="topbar-nav-btn" data-page="settings" onclick="showPage('settings')">НАСТРОЙКИ</button>
  </div>
  <div style="flex:1;min-width:40px"></div>
  <div class="topbar-right pywebview-no-drag">
    <button class="topbar-icon-btn" title="Настройки" onclick="showPage('settings')">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12.22 2h-.44a2 2 0 00-2 2v.18a2 2 0 01-1 1.73l-.43.25a2 2 0 01-2 0l-.15-.08a2 2 0 00-2.73.73l-.22.38a2 2 0 00.73 2.73l.15.1a2 2 0 011 1.72v.51a2 2 0 01-1 1.74l-.15.09a2 2 0 00-.73 2.73l.22.38a2 2 0 002.73.73l.15-.08a2 2 0 012 0l.43.25a2 2 0 011 1.73V20a2 2 0 002 2h.44a2 2 0 002-2v-.18a2 2 0 011-1.73l.43-.25a2 2 0 012 0l.15.08a2 2 0 002.73-.73l.22-.39a2 2 0 00-.73-2.73l-.15-.08a2 2 0 01-1-1.74v-.5a2 2 0 011-1.74l.15-.09a2 2 0 00.73-2.73l-.22-.38a2 2 0 00-2.73-.73l-.15.08a2 2 0 01-2 0l-.43-.25a2 2 0 01-1-1.73V4a2 2 0 00-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
    </button>
  </div>
  <div class="topbar-btns pywebview-no-drag">
    <button class="topbar-wbtn" onclick="pywebview.api.minimize_window()">
      <svg width="11" height="11" viewBox="0 0 11 11"><line x1="1" y1="5.5" x2="10" y2="5.5" stroke="currentColor" stroke-width="1"/></svg>
    </button>
    <button class="topbar-wbtn" onclick="pywebview.api.maximize_window()">
      <svg width="11" height="11" viewBox="0 0 11 11"><rect x="1.5" y="1.5" width="8" height="8" stroke="currentColor" stroke-width="1" fill="none"/></svg>
    </button>
    <button class="topbar-wbtn close" onclick="pywebview.api.close_window()">
      <svg width="11" height="11" viewBox="0 0 11 11"><line x1="2" y1="2" x2="9" y2="9" stroke="currentColor" stroke-width="1.2"/><line x1="9" y1="2" x2="2" y2="9" stroke="currentColor" stroke-width="1.2"/></svg>
    </button>
  </div>
</div>

<!-- GAME ICON BAR -->
<div class="game-bar pywebview-no-drag" id="game-bar"></div>

<!-- MAIN CONTENT -->
<div class="main-wrap pywebview-no-drag">

  <!-- === GAME PAGE (main view) === -->
  <div class="game-left" id="main-game-view">
    <div class="main-view" id="view-game">
      <!-- Hero -->
      <div class="hero-area" id="hero-area">
        <div class="hero-bg" id="hero-bg"></div>
        <div class="hero-overlay"></div>
        <div class="hero-overlay-bottom"></div>
        <!-- Left side: game title + links -->
        <div class="hero-left">
          <div class="game-logo-title" id="game-title">World of Warcraft</div>
          <div class="game-logo-sub" id="game-subtitle">WotLK 3.3.5a</div>
          <button class="hero-sidebar-btn" onclick="showPage('news')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/><path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/></svg>
            Новости
          </button>
          <button class="hero-sidebar-btn" onclick="showPage('settings')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 1v2m0 18v2M4.22 4.22l1.42 1.42m12.72 12.72l1.42 1.42M1 12h2m18 0h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
            Настройки HD
          </button>
        </div>
        <!-- Right side: project info -->
        <div class="hero-right" id="hero-content">
          <div class="hero-badge">
            <span style="font-size:14px">&#9876;</span>
            PLGAMES CORE
          </div>
          <div class="hero-title" id="hero-title">Realm Chronos</div>
          <div class="hero-text" id="hero-text"></div>
        </div>
        <!-- Slide indicators -->
        <div class="hero-indicators" id="hero-indicators"></div>
      </div>
      <!-- News row -->
      <div class="news-row" id="news-row"></div>
      <!-- Play bar -->
      <div class="play-bar">
        <div class="play-version">
          <span class="play-version-label">Версия</span>
          <select class="play-version-select" id="play-version">
            <option>WotLK 3.3.5a</option>
          </select>
        </div>
        <span class="play-msg" id="launch-msg"></span>
        <button class="play-settings-btn" onclick="showPage('settings')" title="Настройки">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12.22 2h-.44a2 2 0 00-2 2v.18a2 2 0 01-1 1.73l-.43.25a2 2 0 01-2 0l-.15-.08a2 2 0 00-2.73.73l-.22.38a2 2 0 00.73 2.73l.15.1a2 2 0 011 1.72v.51a2 2 0 01-1 1.74l-.15.09a2 2 0 00-.73 2.73l.22.38a2 2 0 002.73.73l.15-.08a2 2 0 012 0l.43.25a2 2 0 011 1.73V20a2 2 0 002 2h.44a2 2 0 002-2v-.18a2 2 0 011-1.73l.43-.25a2 2 0 012 0l.15.08a2 2 0 002.73-.73l.22-.39a2 2 0 00-.73-2.73l-.15-.08a2 2 0 01-1-1.74v-.5a2 2 0 011-1.74l.15-.09a2 2 0 00.73-2.73l-.22-.38a2 2 0 00-2.73-.73l-.15.08a2 2 0 01-2 0l-.43-.25a2 2 0 01-1-1.73V4a2 2 0 00-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
        </button>
        <button class="btn-play" id="btn-play" onclick="launchGame()">ИГРАТЬ</button>
      </div>
    </div>

    <!-- NEWS FULL PAGE -->
    <div class="page-view" id="view-news">
      <div class="news-full">
        <div class="news-full-title">Новости</div>
        <div class="news-grid" id="news-grid"></div>
      </div>
    </div>

    <!-- SETTINGS FULL PAGE -->
    <div class="page-view" id="view-settings">
      <div class="settings-full">
        <div class="settings-full-title">Настройки</div>
        <div id="settings-content"></div>
      </div>
    </div>
  </div>

  <!-- === RIGHT PANEL === -->
  <div class="right-panel">
    <!-- Auth / User -->
    <div class="rp-section">
      <div class="rp-header">
        <span class="rp-title">Аккаунт</span>
      </div>
      <div id="auth-section">
        <!-- Filled by JS -->
        <button class="btn-auth" id="btn-login" onclick="startSSO()">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1.41 16.09V18c0-.55.45-1 1-1h.82c.55 0 1 .45 1 1v.09c2.84-.48 5.08-2.72 5.56-5.56H18c-.55 0-1-.45-1-1v-.82c0-.55.45-1 1-1h.09C17.56 6.87 15.32 4.63 12.48 4.15V5c0 .55-.45 1-1 1h-.82c-.55 0-1-.45-1-1v-.85C6.84 4.63 4.6 6.87 4.12 9.71H5c.55 0 1 .45 1 1v.82c0 .55-.45 1-1 1h-.88c.48 2.84 2.72 5.08 5.56 5.56z"/></svg>
          Войти через Telegram
        </button>
        <div id="auth-user" style="display:none">
          <div class="auth-user-card">
            <div class="auth-user-name" id="auth-username"></div>
            <div class="auth-user-id" id="auth-account-id"></div>
            <div class="auth-user-actions">
              <button class="auth-action-btn" onclick="resetPassword()">Сбросить пароль</button>
              <button class="auth-action-btn logout" onclick="doLogout()">Выйти</button>
            </div>
          </div>
        </div>
        <div id="auth-polling" style="display:none">
          <div class="auth-polling-card">
            <div class="auth-polling-spinner"></div>
            <div class="auth-polling-text">Ожидание авторизации в Telegram...</div>
            <button class="auth-action-btn" onclick="cancelSSO()">Отмена</button>
          </div>
        </div>
        <div id="auth-new-account" style="display:none">
          <div class="auth-new-card">
            <div class="auth-new-title">Новый аккаунт создан!</div>
            <div class="auth-new-info">Логин: <b id="new-acc-login"></b></div>
            <div class="auth-new-info">Пароль: <b id="new-acc-pass"></b></div>
            <div class="auth-new-hint">Сохраните пароль! Он показывается один раз.</div>
            <button class="auth-action-btn" onclick="dismissNewAccount()">Понятно</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Server Status -->
    <div class="rp-section">
      <div class="rp-header">
        <span class="rp-title">Статус сервера</span>
      </div>
      <div class="server-card">
        <div class="server-row">
          <span class="dot dot-check" id="status-dot"></span>
          <span class="server-name" id="status-text">Проверка...</span>
          <span class="server-info" id="play-players"></span>
        </div>
        <div class="server-row">
          <span class="server-detail">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
            <span id="server-realm">Chronos</span>
          </span>
        </div>
      </div>
    </div>

    <!-- Game Path -->
    <div class="rp-section" id="path-section">
      <div class="rp-header">
        <span class="rp-title">Путь к игре</span>
      </div>
      <div class="path-card">
        <div class="path-val" id="play-path">Не указана</div>
        <button class="path-browse" onclick="browsePath()">Обзор...</button>
      </div>
    </div>

    <!-- About -->
    <div class="rp-section">
      <div class="rp-header">
        <span class="rp-title">О лаунчере</span>
      </div>
      <div style="font-size:11px;color:var(--text-dim);line-height:1.6">
        Realm Chronos Launcher<br>
        <span id="launcher-version"></span>
      </div>
    </div>
  </div>

</div>

<script>
let projects = [];
let activeProject = null;
let currentPage = 'games';
let heroSlideIndex = 0;
let heroTimer = null;

const RESOLUTIONS = %RESOLUTIONS%;
function esc(s){const d=document.createElement('div');d.textContent=s||'';return d.innerHTML;}
const TAG_CLASSES = {'Анонс':'tag-announce','Обновление':'tag-update','Исправление':'tag-fix','Событие':'tag-event'};

let HERO_IMAGES = [
  'https://wow.zamimg.com/uploads/screenshots/normal/522757-the-lich-king.jpg',
  'https://wow.zamimg.com/uploads/screenshots/normal/522115-icecrown-citadel.jpg',
  'https://wow.zamimg.com/uploads/screenshots/normal/323283-dalaran.jpg',
];
let cachedNewsFeed = null;

async function init() {
  projects = JSON.parse(await pywebview.api.get_projects());
  const activePid = await pywebview.api.get_active_project();
  const ver = await pywebview.api.get_version();
  document.getElementById('launcher-version').textContent = 'v' + ver;

  // Game icon bar
  const bar = document.getElementById('game-bar');
  bar.innerHTML = '';
  projects.forEach(p => {
    const btn = document.createElement('button');
    btn.className = 'game-bar-btn' + (p.id === activePid ? ' active' : '');
    btn.dataset.pid = p.id;
    btn.title = p.name;
    const icon = document.createElement('div');
    icon.className = 'game-bar-icon' + (p.has_exe ? '' : ' soon');
    icon.textContent = p.name.charAt(0).toUpperCase();
    btn.appendChild(icon);
    btn.onclick = () => selectProject(p.id);
    bar.appendChild(btn);
  });

  selectProject(activePid, false);
  startHeroSlider();
  loadAuthState();
}

async function selectProject(pid, save=true) {
  activeProject = projects.find(p => p.id === pid) || projects[0];
  if (save) await pywebview.api.set_active_project(pid);

  document.querySelectorAll('.game-bar-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.pid === activeProject.id);
  });

  loadGameView();
  loadNewsFeed();
  loadSettings();
  checkStatus();
}

function showPage(page) {
  currentPage = page;
  document.querySelectorAll('.topbar-nav-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.page === page);
  });

  const gameView = document.getElementById('view-game');
  const newsView = document.getElementById('view-news');
  const settingsView = document.getElementById('view-settings');

  gameView.className = 'main-view' + (page === 'games' ? '' : ' hidden');
  newsView.className = 'page-view' + (page === 'news' ? ' active fade-in' : '');
  settingsView.className = 'page-view' + (page === 'settings' ? ' active fade-in' : '');
}

// ==================== HERO SLIDER ====================

function startHeroSlider() {
  const bg = document.getElementById('hero-bg');
  const indicators = document.getElementById('hero-indicators');
  if (!HERO_IMAGES.length) return;

  indicators.innerHTML = '';
  HERO_IMAGES.forEach((_, i) => {
    const ind = document.createElement('div');
    ind.className = 'hero-ind' + (i === 0 ? ' active' : '');
    ind.innerHTML = '<div class="hero-ind-fill"></div>';
    ind.onclick = () => goToSlide(i);
    indicators.appendChild(ind);
  });

  bg.style.backgroundImage = `url(${HERO_IMAGES[0]})`;
  heroSlideIndex = 0;

  if (heroTimer) clearInterval(heroTimer);
  heroTimer = setInterval(() => {
    goToSlide((heroSlideIndex + 1) % HERO_IMAGES.length);
  }, 6000);
}

function goToSlide(i) {
  heroSlideIndex = i;
  const bg = document.getElementById('hero-bg');
  bg.style.opacity = '0';
  setTimeout(() => {
    bg.style.backgroundImage = `url(${HERO_IMAGES[i]})`;
    bg.style.opacity = '1';
  }, 300);

  document.querySelectorAll('.hero-ind').forEach((ind, idx) => {
    ind.className = 'hero-ind' + (idx === i ? ' active' : '');
    if (idx === i) ind.innerHTML = '<div class="hero-ind-fill"></div>';
    else ind.innerHTML = '';
  });

  if (heroTimer) clearInterval(heroTimer);
  heroTimer = setInterval(() => {
    goToSlide((heroSlideIndex + 1) % HERO_IMAGES.length);
  }, 6000);
}

// ==================== GAME VIEW ====================

async function loadGameView() {
  const p = activeProject;
  document.getElementById('game-title').textContent = p.full_name;
  document.getElementById('game-subtitle').textContent = p.subtitle;
  document.getElementById('hero-title').textContent = p.full_name;

  const descText = typeof p.description === 'object' ? (p.description.ru || p.description.en || '') : (p.description || '');
  document.getElementById('hero-text').textContent = descText;
  document.getElementById('server-realm').textContent = p.name;

  const btn = document.getElementById('btn-play');
  if (!p.has_exe) {
    btn.className = 'btn-play coming';
    btn.textContent = 'СКОРО';
    btn.disabled = true;
    document.getElementById('path-section').style.display = 'none';
  } else {
    btn.className = 'btn-play';
    btn.textContent = 'ИГРАТЬ';
    btn.disabled = false;
    document.getElementById('path-section').style.display = '';
    const gp = await pywebview.api.get_game_path(p.id);
    document.getElementById('play-path').textContent = gp || 'Не указана';
  }
  document.getElementById('launch-msg').textContent = '';
}

async function browsePath() {
  const path = await pywebview.api.browse_game_path(activeProject.id);
  if (path) document.getElementById('play-path').textContent = path;
}

async function launchGame() {
  const btn = document.getElementById('btn-play');
  const msg = document.getElementById('launch-msg');
  btn.disabled = true;
  msg.textContent = 'Запуск...';
  msg.style.color = 'var(--accent)';

  const res = JSON.parse(await pywebview.api.launch_game(activeProject.id));
  msg.textContent = res.msg;
  msg.style.color = res.ok ? 'var(--green)' : 'var(--red)';
  btn.disabled = false;
}

async function checkStatus() {
  const dot = document.getElementById('status-dot');
  const stxt = document.getElementById('status-text');
  const players = document.getElementById('play-players');

  dot.className = 'dot dot-check';
  stxt.textContent = 'Проверка...';

  try {
    const data = JSON.parse(await pywebview.api.get_server_status(activeProject.id));
    if (data.online === true) {
      dot.className = 'dot dot-on';
      stxt.textContent = 'Онлайн';
      players.textContent = (data.players || 0) + ' игр.';
    } else if (data.online === false) {
      dot.className = 'dot dot-off';
      stxt.textContent = 'Оффлайн';
      players.textContent = '';
    } else {
      stxt.textContent = 'Нет связи';
      players.textContent = '';
    }
  } catch(e) {
    stxt.textContent = 'Ошибка';
  }
}

// ==================== NEWS ====================

async function loadNewsFeed() {
  try {
    cachedNewsFeed = JSON.parse(await pywebview.api.get_news_feed(activeProject.id));
  } catch(e) {
    cachedNewsFeed = {banners: [], news: []};
  }
  // Update hero slider with banners from feed
  const banners = cachedNewsFeed.banners || [];
  if (banners.length > 0) {
    HERO_IMAGES = banners.map(b => b.image);
    startHeroSlider();
  }
  // Render news row (main page) and full news grid
  renderNewsRow();
  renderNewsGrid();
}

function renderNewsRow() {
  const row = document.getElementById('news-row');
  row.innerHTML = '';
  if (!cachedNewsFeed) return;
  const items = (cachedNewsFeed.news || []).slice(0, 3);
  const banners = cachedNewsFeed.banners || [];
  items.forEach((item, i) => {
    const img = item.image || (banners[i % banners.length] || {}).image || '';
    row.innerHTML += `
      <div class="news-card-mini" onclick="showPage('news')">
        <div class="news-card-img" style="background-image:url(${img})"></div>
        <div class="news-card-body">
          <div class="news-card-tag">${esc(item.tag || 'Новость')}</div>
          <div class="news-card-title">${esc(item.title)}</div>
        </div>
      </div>`;
  });
}

function renderNewsGrid() {
  const grid = document.getElementById('news-grid');
  if (!cachedNewsFeed) { grid.innerHTML = ''; return; }
  const items = cachedNewsFeed.news || [];
  grid.innerHTML = '';
  items.forEach(item => {
    const tagClass = TAG_CLASSES[item.tag] || 'tag-announce';
    const imgHtml = item.image ? `<div class="news-card-full-img" style="background-image:url(${item.image})"></div>` : '';
    grid.innerHTML += `
      <div class="news-card-full">
        ${imgHtml}
        <div class="news-top">
          <span class="news-tag ${tagClass}">${esc(item.tag)}</span>
          <span class="news-date">${esc(item.date)}</span>
        </div>
        <h3>${esc(item.title)}</h3>
        <p>${esc(item.text)}</p>
      </div>`;
  });
  } catch(e) {
    grid.innerHTML = '<div style="color:var(--text-sec)">Не удалось загрузить</div>';
  }
}

// ==================== SETTINGS ====================

async function loadSettings() {
  const container = document.getElementById('settings-content');
  container.innerHTML = '';
  const pid = activeProject.id;

  try {
    const patches = JSON.parse(await pywebview.api.get_hd_patches(pid));
    if (patches.length > 0) {
      const cats = {};
      patches.forEach(p => { (cats[p.cat] = cats[p.cat] || []).push(p); });
      for (const [cat, list] of Object.entries(cats)) {
        let html = `<div class="settings-section"><h3>${cat}</h3>`;
        list.forEach(p => {
          if (!p.installed) {
            html += `<div class="setting-row"><span class="setting-label" style="color:var(--text-dim)">${p.name}</span><span class="setting-info">не установлен</span></div>`;
          } else {
            html += `<div class="setting-row">
              <span class="setting-label">${p.name}</span>
              <div class="setting-right">
                <span class="setting-info">${p.size} MB</span>
                <label class="toggle">
                  <input type="checkbox" ${p.enabled?'checked':''} onchange="togglePatch('${p.file}','${p.folder}',this.checked)">
                  <span class="slider"></span>
                </label>
              </div>
            </div>`;
          }
        });
        html += '</div>';
        container.innerHTML += html;
      }
    }
  } catch(e) {}

  try {
    const gs = JSON.parse(await pywebview.api.get_graphic_settings(pid));
    if (gs.defs && Object.keys(gs.defs).length > 0) {
      let html = '<div class="settings-section"><h3>Графика (Config.wtf)</h3>';
      for (const [key, def] of Object.entries(gs.defs)) {
        const cur = gs.current[key] || '';
        html += `<div class="setting-row"><span class="setting-label">${def.label}</span><div class="setting-right">`;
        if (def.type === 'bool') {
          html += `<label class="toggle"><input type="checkbox" data-gfx="${key}" ${cur==='1'?'checked':''}><span class="slider"></span></label>`;
        } else if (def.type === 'res') {
          html += `<select class="setting-select" data-gfx="${key}">`;
          RESOLUTIONS.forEach(r => { html += `<option ${r===cur?'selected':''}>${r}</option>`; });
          html += '</select>';
        } else if (def.type === 'select') {
          html += `<select class="setting-select" data-gfx="${key}">`;
          (def.opts||[]).forEach(o => { html += `<option ${o===cur?'selected':''}>${o}</option>`; });
          html += '</select>';
        }
        html += '</div></div>';
      }
      html += '<button class="btn-save" onclick="saveGfx()">Сохранить</button></div>';
      container.innerHTML += html;
    }
  } catch(e) {}

  if (container.innerHTML === '') {
    container.innerHTML = '<div class="settings-section"><h3>Нет доступных настроек</h3><p style="color:var(--text-sec);font-size:12px">Выберите проект и укажите папку с игрой.</p></div>';
  }
}

async function togglePatch(file, folder, enable) {
  await pywebview.api.toggle_hd_patch(activeProject.id, file, folder, enable);
}

async function saveGfx() {
  const settings = {};
  document.querySelectorAll('[data-gfx]').forEach(el => {
    const key = el.dataset.gfx;
    if (el.type === 'checkbox') settings[key] = el.checked ? '1' : '0';
    else settings[key] = el.value;
  });
  await pywebview.api.save_graphic_settings(activeProject.id, JSON.stringify(settings));
  alert('Настройки сохранены!');
}

// ==================== AUTH (Telegram SSO) ====================

let ssoPolling = false;
let ssoPollTimer = null;
let ssoPollCount = 0;

async function loadAuthState() {
  try {
    const data = JSON.parse(await pywebview.api.get_auth_state());
    const btnLogin = document.getElementById('btn-login');
    const userDiv = document.getElementById('auth-user');
    const pollingDiv = document.getElementById('auth-polling');

    if (data.logged_in) {
      btnLogin.style.display = 'none';
      userDiv.style.display = '';
      pollingDiv.style.display = 'none';
      document.getElementById('auth-username').textContent = data.first_name || data.username;
      document.getElementById('auth-account-id').textContent = data.username + ' #' + data.account_id;
      // Auto-fetch credentials (writes realmlist)
      pywebview.api.fetch_credentials();
    } else {
      btnLogin.style.display = '';
      userDiv.style.display = 'none';
      pollingDiv.style.display = 'none';
    }
  } catch(e) {}
}

async function startSSO() {
  const btnLogin = document.getElementById('btn-login');
  const pollingDiv = document.getElementById('auth-polling');
  btnLogin.style.display = 'none';
  pollingDiv.style.display = '';

  try {
    const res = JSON.parse(await pywebview.api.sso_start());
    if (!res.ok) {
      alert(res.msg || 'Ошибка SSO');
      pollingDiv.style.display = 'none';
      btnLogin.style.display = '';
      return;
    }
    // Start polling
    ssoPolling = true;
    ssoPollCount = 0;
    pollSSO();
  } catch(e) {
    alert('SSO сервис недоступен');
    pollingDiv.style.display = 'none';
    btnLogin.style.display = '';
  }
}

async function pollSSO() {
  if (!ssoPolling) return;
  ssoPollCount++;
  if (ssoPollCount > 150) { // 5 min timeout (2s * 150)
    cancelSSO();
    alert('Время авторизации истекло. Попробуйте снова.');
    return;
  }
  try {
    const res = JSON.parse(await pywebview.api.sso_poll());
    if (res.status === 'completed') {
      ssoPolling = false;
      document.getElementById('auth-polling').style.display = 'none';
      // Show new account info if needed
      if (res.is_new && res.password) {
        document.getElementById('new-acc-login').textContent = res.username;
        document.getElementById('new-acc-pass').textContent = res.password;
        document.getElementById('auth-new-account').style.display = '';
      }
      loadAuthState();
      return;
    }
    if (res.status === 'error') {
      cancelSSO();
      alert(res.msg || 'Ошибка авторизации');
      return;
    }
    // Still pending — poll again in 2s
    ssoPollTimer = setTimeout(pollSSO, 2000);
  } catch(e) {
    ssoPollTimer = setTimeout(pollSSO, 2000);
  }
}

function cancelSSO() {
  ssoPolling = false;
  if (ssoPollTimer) clearTimeout(ssoPollTimer);
  document.getElementById('auth-polling').style.display = 'none';
  document.getElementById('btn-login').style.display = '';
}

function dismissNewAccount() {
  document.getElementById('auth-new-account').style.display = 'none';
}

async function doLogout() {
  await pywebview.api.logout();
  loadAuthState();
}

async function resetPassword() {
  const res = JSON.parse(await pywebview.api.reset_password());
  alert(res.msg || (res.ok ? 'Готово' : 'Ошибка'));
}

window.addEventListener('pywebviewready', init);
</script>
</body>
</html>"""

# ---------------------------------------------------------------------------
# ENTRY
# ---------------------------------------------------------------------------

def main():
    api = Api()
    html = HTML.replace('%RESOLUTIONS%', json.dumps(RESOLUTIONS))

    window = webview.create_window(
        f'Realm Chronos Launcher v{LAUNCHER_VERSION}',
        html=html,
        js_api=api,
        width=1200, height=740,
        min_size=(1000, 600),
        background_color='#1a1c23',
        frameless=True,
        easy_drag=True,
    )
    api.window = window
    webview.start(debug=False)


if __name__ == "__main__":
    main()
