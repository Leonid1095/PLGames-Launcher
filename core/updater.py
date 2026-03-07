"""
Update system and file integrity checker.
- Checks for launcher updates
- Checks for game file updates via manifest (JSON with file hashes)
- Verifies file integrity via SHA256
"""

import os
import hashlib
import json
import threading
import requests


MANIFEST_FILENAME = "plgames_manifest.json"
CHUNK_SIZE = 8192


class UpdateChecker:
    def __init__(self, manifest_url: str, launcher_update_url: str):
        self.manifest_url = manifest_url
        self.launcher_update_url = launcher_update_url
        self._progress_callback = None
        self._cancel = False

    def set_progress_callback(self, cb):
        """cb(status_text: str, progress_pct: float | None)"""
        self._progress_callback = cb

    def cancel(self):
        self._cancel = True

    def _report(self, text: str, pct: float | None = None):
        if self._progress_callback:
            self._progress_callback(text, pct)

    # --- Launcher self-update check ---
    def check_launcher_update(self, current_version: str) -> dict | None:
        """Returns {version, download_url, changelog} or None."""
        try:
            r = requests.get(self.launcher_update_url, timeout=5)
            if r.status_code != 200:
                return None
            data = r.json()
            if data.get("version", current_version) != current_version:
                return data
        except Exception:
            pass
        return None

    # --- Game file manifest ---
    def fetch_remote_manifest(self) -> dict | None:
        """Fetch remote file manifest: {files: [{path, sha256, size, url}]}."""
        try:
            r = requests.get(self.manifest_url, timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    def load_local_manifest(self, game_path: str) -> dict:
        path = os.path.join(game_path, MANIFEST_FILENAME)
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"files": []}

    def save_local_manifest(self, game_path: str, manifest: dict):
        path = os.path.join(game_path, MANIFEST_FILENAME)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
        except Exception:
            pass

    # --- Integrity check ---
    def hash_file(self, filepath: str) -> str | None:
        if not os.path.isfile(filepath):
            return None
        sha = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                while True:
                    chunk = f.read(CHUNK_SIZE * 16)  # 128KB chunks for speed
                    if not chunk:
                        break
                    sha.update(chunk)
            return sha.hexdigest()
        except Exception:
            return None

    def verify_integrity(self, game_path: str, manifest: dict | None = None) -> list[dict]:
        """
        Verify game files against manifest.
        Returns list of {path, status} where status is 'ok', 'modified', 'missing'.
        """
        self._cancel = False

        if manifest is None:
            manifest = self.load_local_manifest(game_path)

        files = manifest.get("files", [])
        if not files:
            self._report("Манифест пуст — нечего проверять", None)
            return []

        results = []
        total = len(files)

        for idx, entry in enumerate(files):
            if self._cancel:
                self._report("Проверка отменена", None)
                break

            rel_path = entry.get("path", "")
            expected_hash = entry.get("sha256", "")
            full_path = os.path.join(game_path, rel_path)

            pct = (idx + 1) / total * 100
            self._report(f"Проверка {idx+1}/{total}: {os.path.basename(rel_path)}", pct)

            if not os.path.isfile(full_path):
                results.append({"path": rel_path, "status": "missing"})
                continue

            actual_hash = self.hash_file(full_path)
            if actual_hash == expected_hash:
                results.append({"path": rel_path, "status": "ok"})
            else:
                results.append({"path": rel_path, "status": "modified"})

        ok = sum(1 for r in results if r["status"] == "ok")
        modified = sum(1 for r in results if r["status"] == "modified")
        missing = sum(1 for r in results if r["status"] == "missing")
        self._report(f"Готово: {ok} ОК, {modified} изменено, {missing} отсутствует", 100)
        return results

    # --- Download updates ---
    def download_updates(self, game_path: str, files_to_update: list[dict]) -> bool:
        """Download files from manifest. Each entry needs {path, url}."""
        self._cancel = False
        total = len(files_to_update)

        for idx, entry in enumerate(files_to_update):
            if self._cancel:
                self._report("Загрузка отменена", None)
                return False

            url = entry.get("url", "")
            rel_path = entry.get("path", "")
            full_path = os.path.join(game_path, rel_path)
            pct = (idx + 1) / total * 100
            self._report(f"Скачивание {idx+1}/{total}: {os.path.basename(rel_path)}", pct)

            try:
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                r = requests.get(url, stream=True, timeout=30)
                if r.status_code == 200:
                    with open(full_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                            if self._cancel:
                                return False
                            f.write(chunk)
                else:
                    self._report(f"Ошибка загрузки {rel_path}: HTTP {r.status_code}", pct)
            except Exception as e:
                self._report(f"Ошибка: {e}", pct)

        self._report("Обновление завершено", 100)
        return True


def run_integrity_check_async(checker: UpdateChecker, game_path: str,
                               on_done=None):
    """Run integrity check in background thread."""
    def _worker():
        results = checker.verify_integrity(game_path)
        if on_done:
            on_done(results)
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t
