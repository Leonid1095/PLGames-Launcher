"""Фасад графических изданий для интерфейса лаунчера: манифест (кэш в памяти),
представление для страницы «Издания», фоновое применение с прогрессом."""

import os
import threading

import content
import hardware
import useraddons


def _requests_session():
    import requests
    return requests.Session()


def short_name(name):
    """Короткое имя компонента для подписей: часть до двоеточия («Фильтры ReShade: …» → «Фильтры ReShade»)."""
    return name.split(":", 1)[0].strip()


class EditionService:
    def __init__(self, urls, cache_path, builtin_path, session_factory=None,
                 gpu_detector=hardware.detect_gpus, is_running=None, installers_dir=None,
                 caps_detector=hardware.detect_capabilities, bundled_addons_dir=None):
        self._installers_dir = installers_dir
        self._bundled_addons = bundled_addons_dir  # серверные аддоны, которые лаунчер кладёт в игру сам
        self._urls = list(urls)
        self._cache = cache_path
        self._builtin = builtin_path
        self._session_factory = session_factory or _requests_session
        self._gpu_detector = gpu_detector
        self._caps_detector = caps_detector
        self._is_running = is_running
        self._lock = threading.Lock()
        self._manifest = None
        self._source = ""
        self._recommended = None
        self._caps = None
        self._job_lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._cancel = threading.Event()
        self._job = {"state": "idle"}
        self._thread = None

    # ---- данные ----

    def preload(self):
        """Прогреть манифест и рекомендацию в фоне, чтобы вкладка открывалась сразу."""
        threading.Thread(target=self._preload, daemon=True).start()

    def _preload(self):
        try:
            self.manifest()
        except content.ManifestError:
            pass
        self.recommended()
        self.capabilities()

    def manifest(self, refresh=False):
        with self._lock:
            if self._manifest is None or refresh:
                self._manifest, self._source = content.load_manifest(
                    self._urls, self._cache, self._builtin, session=self._session_factory())
            return self._manifest

    def recommended(self):
        if self._recommended is None:
            try:
                gpus = self._gpu_detector()
            except Exception:
                gpus = []
            self._recommended = hardware.recommend_edition(gpus)
        return self._recommended

    def capabilities(self):
        if self._caps is None:
            try:
                self._caps = frozenset(self._caps_detector())
            except Exception:
                self._caps = frozenset()
        return self._caps

    def _edition_view(self, m, status, e, caps):
        comps = content.resolve_components(m, e.components, caps)
        replaced = [{"component": short_name(m.component(cid).name),
                     "by": short_name(m.component(m.component(cid).fallback).name),
                     "needs": content.CAPABILITIES[m.component(cid).requires]}
                    for cid in e.components if cid not in comps and m.component(cid).fallback]
        return {"id": e.id, "name": e.name, "tagline": e.tagline, "image": e.image, "note": e.note,
                "download": content.download_bytes(m, status, comps), "replaced": replaced}

    def _component_view(self, m, status, c, caps):
        active_conflicts = [o for o in c.conflicts if status[o]["active"]]
        return dict(id=c.id, name=c.name, group=c.group, type=c.type, **status[c.id],
                    download=content.download_bytes(m, status, [c.id]),
                    requires_ok=not c.requires or c.requires in caps, conflict_active=active_conflicts)

    def server_addons(self):
        """[{folder, title, notes}] серверных аддонов из поставки лаунчера."""
        out = []
        root = self._bundled_addons
        try:
            names = sorted(os.listdir(root)) if root else []
        except OSError:
            names = []
        for name in names:
            fields = useraddons.read_toc(os.path.join(root, name, name + ".toc"))
            if fields is not None:
                out.append({"folder": name, "title": useraddons.clean_title(fields.get("Title")) or name,
                            "notes": useraddons.clean_title(fields.get("Notes", ""))})
        return out

    def _addon_owners(self, m):
        """Папки, которые не считаются своими аддонами игрока: каталог и серверные (нижний регистр)."""
        owned = {f.lower() for c in m.components if c.scope == "addon" for f in c.folders}
        server = {a["folder"].lower() for a in self.server_addons()}
        return owned, server

    def set_user_addon(self, game_dir, folder, enabled):
        with self._start_lock:
            if self.busy():
                return False, "Сейчас применяются изменения — попробуйте через минуту"
            if not game_dir or not os.path.isdir(game_dir):
                return False, "Сначала установите игру"
            try:
                m = self.manifest()
            except content.ManifestError as e:
                return False, str(e)
            owned, server = self._addon_owners(m)
            return useraddons.set_enabled(game_dir, folder, enabled, owned, server)

    def view(self, game_dir):
        m = self.manifest()
        installed = bool(game_dir) and os.path.isdir(game_dir)
        if installed:
            state = content.load_state(game_dir)
            status = content.component_status(m, game_dir, state)
            active = content.detect_edition(m, status)
        else:
            state = content.empty_state()
            status = {c.id: {"available": c.type != "mpq", "active": False, "partial": False, "outdated": False,
                             "foreign": False}
                      for c in m.components}
            active = None
        caps = self.capabilities()
        return {
            "ok": True,
            "installed": installed,
            "source": self._source,
            "content_version": m.content_version,
            "active": active,
            "chosen": state.get("edition"),
            "recommended": self.recommended(),
            "editions": [self._edition_view(m, status, e, caps) for e in m.editions],
            "table": content.table_checks(m),
            "components": [self._component_view(m, status, c, caps)
                           for c in m.components if c.scope == "edition"],
            "addons": [dict(id=c.id, name=c.name, group=c.group, description=c.description, author=c.author,
                            license=c.license, default=c.default,
                            size=c.archive.size if c.archive is not None else 0, **status[c.id])
                       for c in m.components if c.scope == "addon"],
            "server_addons": self.server_addons(),
            "user_addons": useraddons.scan(game_dir, *self._addon_owners(m)) if installed else [],
            "job": self.status(),
        }

    # ---- применение ----

    def status(self):
        with self._job_lock:
            return dict(self._job)

    def _set_job(self, **kw):
        with self._job_lock:
            self._job.update(kw)

    def busy(self):
        return self._thread is not None and self._thread.is_alive()

    def cancel(self):
        """Прервать загрузку. Если изменения клиента уже начались — они доведутся до конца."""
        self._cancel.set()

    def join(self, timeout=None):
        if self._thread is not None:
            self._thread.join(timeout)

    def start_apply(self, game_dir, edition_id=None, component_ids=None, addon_ids=None):
        """Издание (edition_id), «Своё» (component_ids) или набор аддонов (addon_ids)."""
        # pywebview вызывает API из разных потоков: проверка «занято» и запуск — атомарно.
        with self._start_lock:
            return self._start_apply_locked(game_dir, edition_id, component_ids, addon_ids)

    def _start_apply_locked(self, game_dir, edition_id, component_ids, addon_ids=None):
        if self.busy():
            return False, "Изменения уже применяются"
        if not game_dir or not os.path.isdir(game_dir):
            return False, "Сначала установите игру"
        try:
            m = self.manifest()
        except content.ManifestError as e:
            return False, str(e)
        scope = "edition"
        if addon_ids is not None:
            target, label, scope = set(addon_ids), None, "addon"
        elif edition_id is not None:
            ed = next((e for e in m.editions if e.id == edition_id), None)
            if ed is None:
                return False, "Неизвестное издание"
            target, label = set(content.resolve_components(m, ed.components, self.capabilities())), ed.id
        else:
            target, label = set(component_ids or ()), "custom"
        state = content.load_state(game_dir)
        status = content.component_status(m, game_dir, state)
        try:
            actions = content.plan(m, status, state, target, scope=scope)
        except content.PlanError as e:
            return False, str(e)
        with self._job_lock:
            self._job = {"state": "running", "stage": "prepare", "progress": 0, "text": "Подготовка…",
                         "edition": label, "scope": scope}
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, args=(m, game_dir, state, actions, label),
                                        daemon=True)
        self._thread.start()
        return True, ""

    def _executor(self, m, game_dir, state, progress):
        return content.Executor(m, game_dir, state, session=self._session_factory(), progress=progress,
                                is_running=self._is_running, cancel=self._cancel,
                                installers_dir=self._installers_dir)

    def _run(self, m, game_dir, state, actions, label):
        has_downloads = any(a.kind in ("files_install", "zip_install", "installer_run") for a in actions)

        def progress(stage, done, total, text):
            frac = done / total if total else 1.0
            if stage == "download":
                pct, verb = frac * 80, "Загрузка"
            elif stage == "install":
                pct, verb = (85 if has_downloads else 10) + frac * 10, "Установка"
            else:
                pct = (80 + frac * 20) if has_downloads else frac * 100
                verb = "Применение"
            self._set_job(stage=stage, progress=int(pct), text=f"{verb}: {text}")

        try:
            state = self._executor(m, game_dir, state, progress).run(actions, edition=label)
            if label is not None and not state.get("addons_initialized"):
                state = self._install_default_addons(m, game_dir, progress)
            self._set_job(state="finished", progress=100, text="Готово")
        except content.ApplyError as e:
            self._set_job(state="error", error=str(e))
        except Exception as e:
            self._set_job(state="error", error=f"Непредвиденная ошибка: {e}")

    def _install_default_addons(self, m, game_dir, progress):
        """При первом выборе издания ставятся аддоны «по умолчанию»; дальше игрок решает сам."""
        state = content.load_state(game_dir)
        defaults = {c.id for c in m.components if c.scope == "addon" and c.default}
        status = content.component_status(m, game_dir, state)
        active = {c.id for c in m.components if c.scope == "addon" and status[c.id]["active"]}
        actions = content.plan(m, status, state, defaults | active, scope="addon")
        state["addons_initialized"] = True
        return self._executor(m, game_dir, state, progress).run(actions)
