import json
import os
import shutil
import tempfile
import time
import unittest

import editions
import hardware
from tests.test_content import (CONF, DLL, FakeSession, ext_manifest, ext_routes, fallback_manifest, good_routes,
                                make_client, manifest_dict)


class RecommendTests(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(hardware.recommend_edition([]), "remaster")
        self.assertEqual(hardware.recommend_edition([{"name": "Intel(R) UHD Graphics 620", "vram_mb": 1024}]),
                         "classic")
        self.assertEqual(hardware.recommend_edition([{"name": "Intel(R) UHD Graphics", "vram_mb": 1024},
                                                     {"name": "NVIDIA GeForce RTX 3060", "vram_mb": 4095}]),
                         "forever")
        self.assertEqual(hardware.recommend_edition([{"name": "NVIDIA GeForce GTX 1050", "vram_mb": 2048}]),
                         "remaster")

    def test_detect_returns_list(self):
        gpus = hardware.detect_gpus()
        self.assertIsInstance(gpus, list)
        for g in gpus:
            self.assertIn("name", g)
            self.assertIn("vram_mb", g)

    def test_capabilities_from_vulkan_version(self):
        self.assertEqual(hardware.detect_capabilities(probe=lambda: (1, 3)), frozenset({"vulkan13"}))
        self.assertEqual(hardware.detect_capabilities(probe=lambda: (1, 4)), frozenset({"vulkan13"}))
        self.assertEqual(hardware.detect_capabilities(probe=lambda: (1, 2)), frozenset())
        self.assertEqual(hardware.detect_capabilities(probe=lambda: None), frozenset())

        def broken():
            raise OSError("no vulkan-1.dll")
        self.assertEqual(hardware.detect_capabilities(probe=broken), frozenset())

    def test_vulkan_probe_does_not_crash(self):
        v = hardware.vulkan_version()
        self.assertTrue(v is None or (isinstance(v, tuple) and len(v) == 2), v)


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
            caps_detector=lambda: frozenset(), is_running=lambda name: False)

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
        self.assertEqual(v["recommended"], "forever")
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


class AddonServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.gd = make_client(self.tmp)
        data = ext_manifest()
        data["components"][-2]["default"] = True  # Questie ставится новым игрокам сразу
        builtin = os.path.join(self.tmp, "builtin.json")
        with open(builtin, "w", encoding="utf-8") as f:
            json.dump(data, f)
        self.svc = editions.EditionService(
            ["https://offline/m.json"], os.path.join(self.tmp, "cache.json"), builtin,
            session_factory=lambda: FakeSession(ext_routes()),
            gpu_detector=lambda: [], caps_detector=lambda: frozenset(), is_running=lambda name: False,
            installers_dir=os.path.join(self.tmp, "installers"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def wait(self):
        end = time.time() + 10
        while self.svc.busy() and time.time() < end:
            time.sleep(0.02)
        return self.svc.status()

    def questie(self):
        return os.path.join(self.gd, "Interface", "AddOns", "Questie", "Core.lua")

    def test_view_lists_addons_separately_with_download_size(self):
        v = self.svc.view(self.gd)
        self.assertEqual([a["id"] for a in v["addons"]], ["addon_questie"])
        self.assertNotIn("addon_questie", [c["id"] for c in v["components"]])
        forever = next(e for e in v["editions"] if e["id"] == "forever")
        self.assertGreater(forever["download"], 0)

    def test_first_edition_installs_default_addons_once(self):
        ok, _ = self.svc.start_apply(self.gd, edition_id="classic")
        self.assertTrue(ok)
        self.assertEqual(self.wait()["state"], "finished")
        self.assertTrue(os.path.isfile(self.questie()))
        ok, _ = self.svc.start_apply(self.gd, addon_ids=[])  # игрок выключил аддон
        self.assertTrue(ok)
        self.assertEqual(self.wait()["state"], "finished")
        self.assertFalse(os.path.exists(self.questie()))
        ok, _ = self.svc.start_apply(self.gd, edition_id="remaster")
        self.assertTrue(ok)
        self.assertEqual(self.wait()["state"], "finished")
        self.assertFalse(os.path.exists(self.questie()))  # второй раз «по умолчанию» не навязывается

    def test_view_lists_server_and_players_own_addons_and_toggles_them(self):
        bundle = os.path.join(self.tmp, "bundle")
        os.makedirs(os.path.join(bundle, "PLGames_Events"))
        with open(os.path.join(bundle, "PLGames_Events", "PLGames_Events.toc"), "w", encoding="utf-8") as f:
            f.write("## Interface: 30300\n## Title: PLGames |cff5fb4ffEvents|r\n## Notes: Метки событий\n")
        own = os.path.join(self.gd, "Interface", "AddOns")
        for folder in ("PLGames_Events", "Questie", "Prat"):
            os.makedirs(os.path.join(own, folder))
            with open(os.path.join(own, folder, folder + ".toc"), "w") as f:
                f.write("## Interface: 30300\n")
        self.svc._bundled_addons = bundle
        v = self.svc.view(self.gd)
        self.assertEqual(v["server_addons"], [{"folder": "PLGames_Events", "title": "PLGames Events",
                                               "notes": "Метки событий"}])
        self.assertEqual([a["folder"] for a in v["user_addons"]], ["Prat"])
        self.assertTrue(next(a for a in v["addons"] if a["id"] == "addon_questie")["foreign"])
        self.assertEqual(self.svc.set_user_addon(self.gd, "Prat", False), (True, ""))
        self.assertFalse(self.svc.view(self.gd)["user_addons"][0]["enabled"])
        self.assertFalse(self.svc.set_user_addon(self.gd, "PLGames_Events", False)[0])

    def test_addons_do_not_change_chosen_edition(self):
        self.svc.start_apply(self.gd, edition_id="classic")
        self.wait()
        self.svc.start_apply(self.gd, addon_ids=["addon_questie"])
        self.wait()
        self.assertEqual(self.svc.view(self.gd)["chosen"], "classic")


class HealTests(unittest.TestCase):
    """Самовосстановление: оборванная установка продолжается, испорченные файлы ставятся заново."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.gd = make_client(self.tmp)
        builtin = os.path.join(self.tmp, "builtin.json")
        with open(builtin, "w", encoding="utf-8") as f:
            json.dump(ext_manifest(), f)
        self.running = False
        self.svc = editions.EditionService(
            ["https://offline/m.json"], os.path.join(self.tmp, "cache.json"), builtin,
            session_factory=lambda: FakeSession(ext_routes()), gpu_detector=lambda: [],
            caps_detector=lambda: frozenset(), is_running=lambda gd: self.running,
            installers_dir=os.path.join(self.tmp, "installers"))

    def wait(self):
        end = time.time() + 10
        while self.svc.busy() and time.time() < end:
            time.sleep(0.02)
        return self.svc.status()

    def apply_ultra(self):
        self.assertEqual(self.svc.start_apply(self.gd, edition_id="ultra"), (True, ""))
        self.assertEqual(self.wait()["state"], "finished")

    def test_nothing_to_do(self):
        self.apply_ultra()
        self.assertEqual(self.svc.heal(self.gd), "ok")
        self.assertEqual(self.svc.heal(""), "skip")

    def test_game_running_is_left_alone(self):
        self.apply_ultra()
        os.remove(os.path.join(self.gd, "d3d9.dll"))
        self.running = True
        self.assertEqual(self.svc.heal(self.gd), "skip")
        self.assertFalse(os.path.exists(os.path.join(self.gd, "d3d9.dll")))

    def test_tampered_edition_file_is_reinstalled_and_edition_kept(self):
        self.apply_ultra()
        dll = os.path.join(self.gd, "d3d9.dll")
        with open(dll, "r+b") as f:
            f.write(b"XX")  # тот же размер, другое содержимое
        os.utime(dll, ns=(1, 1))  # время изменения другое — считаем хэш
        self.assertEqual(self.svc.heal(self.gd), "repair")
        self.assertEqual(self.wait()["state"], "finished")
        with open(dll, "rb") as f:
            self.assertEqual(f.read(), DLL)
        v = self.svc.view(self.gd)
        self.assertEqual((v["active"], v["chosen"]), ("ultra", "ultra"))
        self.assertEqual(self.svc.heal(self.gd), "ok")

    def test_unchanged_file_is_not_rehashed(self):
        self.apply_ultra()
        from unittest import mock
        import content
        with mock.patch.object(content, "_sha256_file", side_effect=AssertionError("лишний хэш")):
            self.assertEqual(self.svc.heal(self.gd), "ok")

    def test_deleted_addon_comes_back(self):
        self.assertEqual(self.svc.start_apply(self.gd, addon_ids=["addon_questie"]), (True, ""))
        self.assertEqual(self.wait()["state"], "finished")
        shutil.rmtree(os.path.join(self.gd, "Interface", "AddOns", "Questie"))
        self.assertEqual(self.svc.heal(self.gd), "repair")
        self.assertEqual(self.wait()["state"], "finished")
        self.assertTrue(os.path.isfile(os.path.join(self.gd, "Interface", "AddOns", "Questie", "Core.lua")))

    def test_interrupted_install_is_rolled_back_and_resumed(self):
        import content
        from tests.test_content import Crash
        real = content.Executor._do_config_apply

        def crash(*a, **kw):
            raise Crash()
        content.Executor._do_config_apply = crash
        try:
            self.assertEqual(self.svc.start_apply(self.gd, edition_id="ultra"), (True, ""))
            self.svc.join(10)  # поток «умер» посреди установки
        finally:
            content.Executor._do_config_apply = real
        self.assertTrue(os.path.isfile(content.journal_path(self.gd)))
        self.assertTrue(os.path.isfile(os.path.join(self.gd, "PLGames", "pending.json")))
        self.assertEqual(self.svc.heal(self.gd), "resume")
        self.assertEqual(self.wait()["state"], "finished")
        v = self.svc.view(self.gd)
        self.assertEqual((v["active"], v["chosen"]), ("ultra", "ultra"))
        self.assertFalse(os.path.exists(content.journal_path(self.gd)))
        self.assertFalse(os.path.exists(os.path.join(self.gd, "PLGames", "pending.json")))


class FallbackServiceTests(unittest.TestCase):
    """Forever на ПК без Vulkan 1.3: вместо Northlight ставится замена (в тестовом манифесте — DXVK)."""

    def make(self, caps):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.gd = make_client(self.tmp)
        builtin = os.path.join(self.tmp, "builtin.json")
        with open(builtin, "w", encoding="utf-8") as f:
            json.dump(fallback_manifest(), f)
        return editions.EditionService(
            ["https://offline/m.json"], os.path.join(self.tmp, "cache.json"), builtin,
            session_factory=lambda: FakeSession(ext_routes()), gpu_detector=lambda: [],
            caps_detector=lambda: caps, is_running=lambda name: False,
            installers_dir=os.path.join(self.tmp, "installers"))

    def wait(self, svc):
        end = time.time() + 10
        while svc.busy() and time.time() < end:
            time.sleep(0.02)
        return svc.status()

    def test_view_tells_what_replaces_what_and_counts_replacement_download(self):
        svc = self.make(frozenset())
        forever = next(e for e in svc.view(self.gd)["editions"] if e["id"] == "forever")
        self.assertEqual(forever["replaced"], [{"component": "Northlight", "by": "DXVK", "needs": "Vulkan 1.3"}])
        self.assertEqual(forever["download"], len(DLL) + len(CONF))
        full = next(e for e in self.make(frozenset({"vulkan13"})).view(self.gd)["editions"] if e["id"] == "forever")
        self.assertEqual(full["replaced"], [])

    def test_apply_on_pc_without_vulkan_installs_fallback_and_stays_forever(self):
        svc = self.make(frozenset())
        self.assertEqual(svc.start_apply(self.gd, edition_id="forever"), (True, ""))
        self.assertEqual(self.wait(svc)["state"], "finished")
        v = svc.view(self.gd)
        self.assertEqual(v["active"], "forever")
        comps = {c["id"]: c for c in v["components"]}
        self.assertTrue(comps["dxvk"]["active"])
        self.assertFalse(comps["northlight"]["active"])
        self.assertFalse(comps["northlight"]["requires_ok"])
        self.assertEqual(comps["northlight"]["conflict_active"], ["dxvk"])
        self.assertGreater(comps["northlight"]["download"], 0)
        self.assertEqual(comps["dxvk"]["download"], 0)
