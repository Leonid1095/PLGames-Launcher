import json
import os
import shutil
import tempfile
import time
import unittest

import editions
import hardware
from tests.test_content import FakeSession, good_routes, make_client, manifest_dict


class RecommendTests(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(hardware.recommend_edition([]), "remaster")
        self.assertEqual(hardware.recommend_edition([{"name": "Intel(R) UHD Graphics 620", "vram_mb": 1024}]),
                         "classic")
        self.assertEqual(hardware.recommend_edition([{"name": "Intel(R) UHD Graphics", "vram_mb": 1024},
                                                     {"name": "NVIDIA GeForce RTX 3060", "vram_mb": 4095}]),
                         "ultra")
        self.assertEqual(hardware.recommend_edition([{"name": "NVIDIA GeForce GTX 1050", "vram_mb": 2048}]),
                         "remaster")

    def test_detect_returns_list(self):
        gpus = hardware.detect_gpus()
        self.assertIsInstance(gpus, list)
        for g in gpus:
            self.assertIn("name", g)
            self.assertIn("vram_mb", g)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.gd = make_client(self.tmp)
        builtin = os.path.join(self.tmp, "builtin.json")
        with open(builtin, "w", encoding="utf-8") as f:
            json.dump(manifest_dict(), f)
        self.svc = editions.EditionService(
            ["https://offline/m.json"], os.path.join(self.tmp, "cache.json"), builtin,
            session_factory=lambda: FakeSession(good_routes()),
            gpu_detector=lambda: [{"name": "NVIDIA GeForce RTX 3060", "vram_mb": 4095}],
            is_running=lambda name: False)

    def wait(self):
        end = time.time() + 10
        while self.svc.busy() and time.time() < end:
            time.sleep(0.02)
        return self.svc.status()

    def test_view_of_fresh_client(self):
        v = self.svc.view(self.gd)
        self.assertTrue(v["ok"] and v["installed"])
        self.assertEqual(v["source"], "builtin")
        self.assertEqual(v["active"], "custom")
        self.assertIsNone(v["chosen"])
        self.assertEqual(v["recommended"], "ultra")
        self.assertEqual([e["id"] for e in v["editions"]], ["classic", "remaster", "ultra"])

    def test_view_without_game(self):
        v = self.svc.view("")
        self.assertFalse(v["installed"])
        self.assertIsNone(v["active"])

    def test_apply_edition_then_custom(self):
        self.assertEqual(self.svc.start_apply(self.gd, edition_id="ultra"), (True, ""))
        self.assertEqual(self.wait()["state"], "finished")
        v = self.svc.view(self.gd)
        self.assertEqual((v["active"], v["chosen"]), ("ultra", "ultra"))
        self.assertEqual(self.svc.start_apply(self.gd, component_ids=["hd_water"]), (True, ""))
        self.assertEqual(self.wait()["state"], "finished")
        v = self.svc.view(self.gd)
        self.assertEqual((v["active"], v["chosen"]), ("custom", "custom"))

    def test_concurrent_starts_only_one_wins(self):
        """pywebview вызывает API из разных потоков: двойной клик не должен запустить два Executor."""
        import threading
        from unittest import mock
        import content

        real = content.component_status

        def slow_status(*a, **kw):
            time.sleep(0.1)  # холодный диск / антивирус
            return real(*a, **kw)

        results = []
        with mock.patch.object(content, "component_status", side_effect=slow_status):
            threads = [threading.Thread(target=lambda e=e: results.append(self.svc.start_apply(self.gd, edition_id=e)))
                       for e in ("ultra", "classic")]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.wait()
        self.assertEqual(sorted(ok for ok, _ in results), [False, True], results)
        self.assertEqual(self.svc.status()["state"], "finished")

    def test_cancel_during_download_leaves_client_untouched(self):
        from tests.test_content import BASE, CONF, FakeResponse

        class SlowResponse(FakeResponse):
            def iter_content(self, chunk):
                for b in self.body:
                    time.sleep(0.05)
                    yield bytes([b])

        routes = good_routes()
        routes[BASE + "/dxvk/d3d9.dll"] = SlowResponse(body=b"x" * 200)  # ~10 с при отмене не дождёмся
        self.svc._session_factory = lambda: FakeSession(routes)
        self.assertEqual(self.svc.start_apply(self.gd, edition_id="ultra"), (True, ""))
        time.sleep(0.3)
        self.svc.cancel()
        self.svc.join(5)
        st = self.svc.status()
        self.assertEqual(st["state"], "error")
        self.assertIn("отмен", st["error"])
        self.assertFalse(os.path.exists(os.path.join(self.gd, "d3d9.dll")))
        self.assertFalse(os.path.exists(os.path.join(self.gd, "PLGames", "state.json")))

    def test_rejects_unknown_edition_and_missing_game(self):
        self.assertEqual(self.svc.start_apply(self.gd, edition_id="nope"), (False, "Неизвестное издание"))
        self.assertFalse(self.svc.start_apply("", edition_id="ultra")[0])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
