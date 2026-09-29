"""Фасад графических изданий для интерфейса лаунчера: манифест (кэш в памяти),
представление для страницы «Издания», фоновое применение с прогрессом."""

import os
import threading

import content
import hardware


def _requests_session():
    import requests
    return requests.Session()


class EditionService:
    def __init__(self, urls, cache_path, builtin_path, session_factory=None,
                 gpu_detector=hardware.detect_gpus, is_running=None):
        self._urls = list(urls)
        self._cache = cache_path
        self._builtin = builtin_path
        self._session_factory = session_factory or _requests_session
        self._gpu_detector = gpu_detector
        self._is_running = is_running
        self._lock = threading.Lock()
        self._manifest = None
        self._source = ""
        self._recommended = None
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

    def view(self, game_dir):
        m = self.manifest()
        installed = bool(game_dir) and os.path.isdir(game_dir)
        if installed:
            state = content.load_state(game_dir)
            status = content.component_status(m, game_dir, state)
            active = content.detect_edition(m, status)
        else:
            state = content.empty_state()
            status = {c.id: {"available": c.type != "mpq", "active": False, "partial": False, "outdated": False}
                      for c in m.components}
            active = None
        return {
            "ok": True,
            "installed": installed,
            "source": self._source,
            "content_version": m.content_version,
            "active": active,
            "chosen": state.get("edition"),
            "recommended": self.recommended(),
            "editions": [{"id": e.id, "name": e.name, "tagline": e.tagline, "image": e.image}
                         for e in m.editions],
            "table": content.table_checks(m),
            "components": [dict(id=c.id, name=c.name, group=c.group, type=c.type, **status[c.id])
                           for c in m.components],
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

    def start_apply(self, game_dir, edition_id=None, component_ids=None):
        # pywebview вызывает API из разных потоков: проверка «занято» и запуск — атомарно.
        with self._start_lock:
            return self._start_apply_locked(game_dir, edition_id, component_ids)

    def _start_apply_locked(self, game_dir, edition_id, component_ids):
        if self.busy():
            return False, "Изменения уже применяются"
        if not game_dir or not os.path.isdir(game_dir):
            return False, "Сначала установите игру"
        try:
            m = self.manifest()
        except content.ManifestError as e:
            return False, str(e)
        if edition_id is not None:
            ed = next((e for e in m.editions if e.id == edition_id), None)
            if ed is None:
                return False, "Неизвестное издание"
            target, label = set(ed.components), ed.id
        else:
            target, label = set(component_ids or ()), "custom"
        state = content.load_state(game_dir)
        status = content.component_status(m, game_dir, state)
        try:
            actions = content.plan(m, status, state, target)
        except content.PlanError as e:
            return False, str(e)
        with self._job_lock:
            self._job = {"state": "running", "stage": "prepare", "progress": 0, "text": "Подготовка…",
                         "edition": label}
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, args=(m, game_dir, state, actions, label), daemon=True)
        self._thread.start()
        return True, ""

    def _run(self, m, game_dir, state, actions, label):
        has_downloads = any(a.kind == "files_install" for a in actions)

        def progress(stage, done, total, text):
            frac = done / total if total else 1.0
            if stage == "download":
                pct, verb = frac * 80, "Загрузка"
            else:
                pct = (80 + frac * 20) if has_downloads else frac * 100
                verb = "Применение"
            self._set_job(stage=stage, progress=int(pct), text=f"{verb}: {text}")

        try:
            content.Executor(m, game_dir, state, session=self._session_factory(), progress=progress,
                             is_running=self._is_running, cancel=self._cancel).run(actions, edition=label)
            self._set_job(state="finished", progress=100, text="Готово")
        except content.ApplyError as e:
            self._set_job(state="error", error=str(e))
        except Exception as e:
            self._set_job(state="error", error=f"Непредвиденная ошибка: {e}")
