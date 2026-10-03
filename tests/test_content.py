import hashlib
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import content
import gameutils

DLL = b"MZ fake dxvk d3d9"
CONF = b"d3d9.samplerAnisotropy = 16\n"
BASE = "https://cdn.test"
MIRROR = "https://mirror.test"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def manifest_dict(dll_urls=None):
    return {
        "schema": 1, "content_version": "t1",
        "components": [
            {"id": "hd_textures", "name": "HD-текстуры", "group": "Графика", "type": "mpq",
             "files": [{"name": "patch-ruRU-4.MPQ", "folder": "Data/ruRU"},
                       {"name": "patch-ruRU-5.MPQ", "folder": "Data/ruRU"}]},
            {"id": "hd_water", "name": "Вода", "group": "Эффекты", "type": "mpq",
             "files": [{"name": "Patch-ruRU-V.mpq", "folder": "Data/ruRU"}]},
            {"id": "missing_pack", "name": "Нет в клиенте", "group": "Графика", "type": "mpq",
             "files": [{"name": "patch-Z.MPQ", "folder": "Data"}]},
            {"id": "dxvk", "name": "DXVK", "group": "Производительность", "type": "files", "version": "2.4",
             "files": [{"path": "d3d9.dll", "size": len(DLL), "sha256": sha(DLL),
                        "urls": dll_urls or [BASE + "/dxvk/d3d9.dll"]},
                       {"path": "dxvk.conf", "size": len(CONF), "sha256": sha(CONF),
                        "urls": [BASE + "/dxvk/dxvk.conf"]}]},
            {"id": "gfx_ultra", "name": "Ультра-настройки", "group": "Настройки", "type": "config",
             "values": {"farclip": "1277", "spellEffectLevel": "6"}},
        ],
        "editions": [
            {"id": "classic", "name": "Классика", "components": []},
            {"id": "remaster", "name": "Ремастер", "components": ["hd_textures", "hd_water", "missing_pack", "dxvk"]},
            {"id": "ultra", "name": "Ультра",
             "components": ["hd_textures", "hd_water", "missing_pack", "dxvk", "gfx_ultra"]},
        ],
        "table": [
            {"label": "Оригинал", "editions": ["classic"]},
            {"label": "HD", "components": ["hd_textures", "hd_water"]},
            {"label": "Макс", "components": ["gfx_ultra"]},
        ],
    }


class FakeResponse:
    def __init__(self, status=200, body=b"", json_data=None):
        self.status_code, self.body, self._json = status, body, json_data

    def iter_content(self, chunk):
        for i in range(0, len(self.body), chunk):
            yield self.body[i:i + chunk]

    def json(self):
        if self._json is None:
            raise ValueError("not json")
        return self._json

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, **kw):
        self.calls.append(url)
        if url not in self.routes:
            raise ConnectionError("unreachable " + url)
        return self.routes[url]


def good_routes():
    return {BASE + "/dxvk/d3d9.dll": FakeResponse(body=DLL), BASE + "/dxvk/dxvk.conf": FakeResponse(body=CONF)}


def make_client(root):
    gd = os.path.join(root, "Game")
    os.makedirs(os.path.join(gd, "Data", "ruRU"))
    os.makedirs(os.path.join(gd, "WTF"))
    open(os.path.join(gd, "Wow.exe"), "wb").close()
    for name in ("patch-ruRU-4.MPQ", "patch-ruRU-5.MPQ", "Patch-ruRU-V.mpq"):
        with open(os.path.join(gd, "Data", "ruRU", name), "wb") as f:
            f.write(b"mpq")
    with open(os.path.join(gd, "WTF", "Config.wtf"), "w") as f:
        f.write('SET farclip "777"\n')
    return gd


def NOT_RUNNING(name):
    return False


class ParseManifestTests(unittest.TestCase):
    def test_valid_manifest(self):
        m = content.parse_manifest(manifest_dict())
        self.assertEqual([c.id for c in m.components][:2], ["hd_textures", "hd_water"])
        self.assertEqual(m.component("gfx_ultra").values_dict(), {"farclip": "1277", "spellEffectLevel": "6"})
        rows = content.table_checks(m)
        self.assertEqual(rows[0]["checks"], {"classic": True, "remaster": False, "ultra": False})
        self.assertEqual(rows[1]["checks"], {"classic": False, "remaster": True, "ultra": True})
        self.assertEqual(rows[2]["checks"], {"classic": False, "remaster": False, "ultra": True})

    def _bad(self, mutate, msg):
        d = manifest_dict()
        mutate(d)
        with self.assertRaises(content.ManifestError, msg=msg):
            content.parse_manifest(d)

    def test_rejects_unsafe_paths_and_types(self):
        for bad in ("../evil.dll", "C:/x.dll", "sub/../../x.dll", "run.exe", "Wow.exe", "/abs.dll"):
            self._bad(lambda d, b=bad: d["components"][3]["files"][0].__setitem__("path", b), bad)

    def test_rejects_http_bad_sha_unknown_members_and_schema(self):
        self._bad(lambda d: d["components"][3]["files"][0].__setitem__("urls", ["http://x/d3d9.dll"]), "http")
        self._bad(lambda d: d["components"][3]["files"][0].__setitem__("sha256", "abc"), "sha")
        self._bad(lambda d: d["editions"][1]["components"].append("nope"), "unknown")
        self._bad(lambda d: d.__setitem__("schema", 99), "schema")
        self._bad(lambda d: d["components"][0]["files"][0].__setitem__("folder", "../.."), "folder")

    def test_shared_file_requires_conflict(self):
        d = manifest_dict()
        d["components"].append({"id": "reshade", "name": "ReShade", "type": "files", "version": "6",
                                "files": [{"path": "d3d9.dll", "size": 1, "sha256": sha(b"r"),
                                           "urls": [BASE + "/r.dll"]}]})
        with self.assertRaises(content.ManifestError):
            content.parse_manifest(d)
        d["components"][-1]["conflicts"] = ["dxvk"]
        content.parse_manifest(d)


class LoadManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache = os.path.join(self.tmp, "cache", "manifest.json")
        self.builtin = os.path.join(self.tmp, "builtin.json")
        with open(self.builtin, "w", encoding="utf-8") as f:
            json.dump(manifest_dict(), f)

    def test_network_success_writes_cache(self):
        s = FakeSession({"https://a/m.json": FakeResponse(json_data=manifest_dict())})
        m, src = content.load_manifest(["https://a/m.json"], self.cache, self.builtin, session=s)
        self.assertEqual(src, "https://a/m.json")
        self.assertTrue(os.path.isfile(self.cache))

    def test_falls_back_mirror_then_cache_then_builtin(self):
        bad = FakeResponse(json_data={"schema": 99})
        s = FakeSession({"https://a/m.json": FakeResponse(status=404),
                         "https://b/m.json": FakeResponse(json_data=manifest_dict())})
        self.assertEqual(content.load_manifest(["https://a/m.json", "https://b/m.json"], self.cache,
                                               self.builtin, session=s)[1], "https://b/m.json")
        offline = FakeSession({"https://a/m.json": bad})
        self.assertEqual(content.load_manifest(["https://a/m.json"], self.cache, self.builtin,
                                               session=offline)[1], "cache")
        os.remove(self.cache)
        self.assertEqual(content.load_manifest(["https://a/m.json"], self.cache, self.builtin,
                                               session=offline)[1], "builtin")

    def test_everything_fails(self):
        with self.assertRaises(content.ManifestError):
            content.load_manifest(["https://a/m.json"], self.cache, None, session=FakeSession({}))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class StatusAndPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.gd = make_client(self.tmp)
        self.m = content.parse_manifest(manifest_dict())

    def status(self, state=None):
        return content.component_status(self.m, self.gd, state or content.load_state(self.gd))

    def test_fresh_client_is_custom_and_missing_pack_unavailable(self):
        st = self.status()
        self.assertTrue(st["hd_textures"]["active"])
        self.assertFalse(st["missing_pack"]["available"])
        self.assertEqual(content.detect_edition(self.m, st), "custom")

    def test_all_disabled_is_classic(self):
        for name in ("patch-ruRU-4.MPQ", "patch-ruRU-5.MPQ", "Patch-ruRU-V.mpq"):
            gameutils.toggle_mpq(self.gd, name, "Data/ruRU", False)
        self.assertEqual(content.detect_edition(self.m, self.status()), "classic")

    def test_partially_enabled_component_is_custom(self):
        for name in ("patch-ruRU-4.MPQ", "Patch-ruRU-V.mpq"):
            gameutils.toggle_mpq(self.gd, name, "Data/ruRU", False)
        st = self.status()
        self.assertTrue(st["hd_textures"]["partial"])
        self.assertFalse(st["hd_textures"]["active"])
        self.assertEqual(content.detect_edition(self.m, st), "custom")

    def test_plan_classic_and_ultra_from_fresh(self):
        st, state = self.status(), content.load_state(self.gd)
        classic = content.plan(self.m, st, state, set())
        self.assertEqual([(a.kind, a.component) for a in classic],
                         [("mpq_off", "hd_textures"), ("mpq_off", "hd_water")])
        ultra = content.plan(self.m, st, state, set(self.m.editions[2].components))
        self.assertEqual([(a.kind, a.component) for a in ultra],
                         [("files_install", "dxvk"), ("config_apply", "gfx_ultra")])

    def test_outdated_files_reinstalled(self):
        state = content.empty_state()
        state["components"]["dxvk"] = {"version": "2.3", "files": {"d3d9.dll": "x", "dxvk.conf": "y"}}
        acts = content.plan(self.m, self.status(state), state, {"dxvk"})
        self.assertEqual([(a.kind, a.component) for a in acts],
                         [("mpq_off", "hd_textures"), ("mpq_off", "hd_water"),
                          ("files_remove", "dxvk"), ("files_install", "dxvk")])

    def test_conflicts_and_unknown_rejected(self):
        d = manifest_dict()
        d["components"].append({"id": "reshade", "name": "ReShade", "type": "files", "version": "6",
                                "conflicts": ["dxvk"],
                                "files": [{"path": "d3d9.dll", "size": 1, "sha256": sha(b"r"),
                                           "urls": [BASE + "/r.dll"]}]})
        m = content.parse_manifest(d)
        st = content.component_status(m, self.gd, content.empty_state())
        with self.assertRaises(content.PlanError):
            content.plan(m, st, content.empty_state(), {"dxvk", "reshade"})
        with self.assertRaises(content.PlanError):
            content.plan(m, st, content.empty_state(), {"nope"})

    def test_state_roundtrip_and_corrupt_file(self):
        state = content.empty_state()
        state["edition"] = "ultra"
        content.save_state(self.gd, state)
        self.assertEqual(content.load_state(self.gd)["edition"], "ultra")
        with open(os.path.join(self.gd, "PLGames", "state.json"), "w") as f:
            f.write("{broken")
        self.assertIsNone(content.load_state(self.gd)["edition"])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.gd = make_client(self.tmp)
        self.m = content.parse_manifest(manifest_dict())

    def apply(self, edition_id, session=None, is_running=NOT_RUNNING):
        state = content.load_state(self.gd)
        st = content.component_status(self.m, self.gd, state)
        ed = next(e for e in self.m.editions if e.id == edition_id)
        acts = content.plan(self.m, st, state, set(ed.components))
        ex = content.Executor(self.m, self.gd, state, session=session or FakeSession(good_routes()),
                              is_running=is_running)
        return ex.run(acts, edition=edition_id)

    def p(self, *parts):
        return os.path.join(self.gd, *parts)

    def read(self, *parts):
        with open(self.p(*parts), "rb") as f:
            return f.read()

    def test_ultra_installs_verifies_and_records(self):
        state = self.apply("ultra")
        self.assertEqual(self.read("d3d9.dll"), DLL)
        self.assertEqual(self.read("dxvk.conf"), CONF)
        self.assertEqual(gameutils.read_config_wtf(self.gd)["farclip"], "1277")
        self.assertEqual(state["components"]["dxvk"]["version"], "2.4")
        self.assertEqual(content.load_state(self.gd)["edition"], "ultra")
        self.assertFalse(os.path.exists(self.p("PLGames", "tmp")))
        st = content.component_status(self.m, self.gd, content.load_state(self.gd))
        self.assertEqual(content.detect_edition(self.m, st), "ultra")

    def test_back_to_classic_restores_everything(self):
        self.apply("ultra")
        self.apply("classic")
        self.assertFalse(os.path.exists(self.p("d3d9.dll")))
        cfg = gameutils.read_config_wtf(self.gd)
        self.assertEqual(cfg["farclip"], "777")
        self.assertNotIn("spellEffectLevel", cfg)
        self.assertTrue(os.path.isfile(self.p("Data", "ruRU", "patch-ruRU-4.MPQ.disabled")))
        self.assertEqual(content.load_state(self.gd)["components"], {})

    def test_config_previous_value_found_regardless_of_case(self):
        with open(self.p("WTF", "Config.wtf"), "w") as f:
            f.write('SET FARCLIP "500"\n')
        self.apply("ultra")
        self.apply("classic")
        with open(self.p("WTF", "Config.wtf")) as f:
            lines = [l.strip() for l in f if l.lower().startswith("set farclip ")]
        self.assertEqual(lines, ['SET farclip "500"'])

    def test_foreign_file_backed_up_and_restored(self):
        with open(self.p("d3d9.dll"), "wb") as f:
            f.write(b"user reshade")
        self.apply("ultra")
        self.assertEqual(self.read("PLGames", "backup", "d3d9.dll"), b"user reshade")
        self.apply("classic")
        self.assertEqual(self.read("d3d9.dll"), b"user reshade")
        self.assertFalse(os.path.exists(self.p("PLGames", "backup", "d3d9.dll")))

    def test_user_file_over_ours_is_kept_on_reinstall(self):
        """Игрок положил свой d3d9.dll (например, ReShade) поверх нашего, потом
        переключил несвязанный компонент в «Своё» — его файл не должен пропасть."""
        self.apply("ultra")
        with open(self.p("d3d9.dll"), "wb") as f:
            f.write(b"player's own reshade build")  # другой размер → компонент «устарел»
        state = content.load_state(self.gd)
        st = content.component_status(self.m, self.gd, state)
        acts = content.plan(self.m, st, state, set(self.m.editions[2].components) - {"hd_water"})
        self.assertIn(content.Action("files_remove", "dxvk"), acts)
        content.Executor(self.m, self.gd, state, session=FakeSession(good_routes()),
                         is_running=NOT_RUNNING).run(acts, edition="custom")
        self.assertEqual(self.read("d3d9.dll"), DLL)
        kept = [os.path.join(dp, f) for dp, _, fs in os.walk(self.p("PLGames", "backup")) for f in fs]
        self.assertEqual(len(kept), 1, kept)
        with open(kept[0], "rb") as f:
            self.assertEqual(f.read(), b"player's own reshade build")

    def test_removal_prunes_empty_folders_but_keeps_used_ones(self):
        extra = b"shader"
        d = manifest_dict()
        d["components"][3]["files"].append({"path": "reshade-shaders/Shaders/x.fx", "size": len(extra),
                                            "sha256": sha(extra), "urls": [BASE + "/x.fx"]})
        self.m = content.parse_manifest(d)
        routes = good_routes()
        routes[BASE + "/x.fx"] = FakeResponse(body=extra)
        self.apply("ultra", session=FakeSession(routes))
        self.assertTrue(os.path.isfile(self.p("reshade-shaders", "Shaders", "x.fx")))
        self.apply("classic")
        self.assertFalse(os.path.exists(self.p("reshade-shaders")))
        self.assertTrue(os.path.isdir(self.p("Data", "ruRU")))

    def test_mutable_file_edited_by_game_is_not_outdated_and_is_removed(self):
        """ReShade переписывает свой ini сам — это не «устаревание» и не файл игрока."""
        d = manifest_dict()
        d["components"][3]["files"][1]["mutable"] = True  # dxvk.conf
        self.m = content.parse_manifest(d)
        self.apply("ultra")
        with open(self.p("dxvk.conf"), "ab") as f:
            f.write(b"# edited at runtime\n")
        st = content.component_status(self.m, self.gd, content.load_state(self.gd))
        self.assertFalse(st["dxvk"]["outdated"])
        self.apply("classic")
        self.assertFalse(os.path.exists(self.p("dxvk.conf")))
        self.assertFalse(os.path.exists(self.p("PLGames", "backup", "kept")))

    def test_bad_checksum_falls_back_to_mirror(self):
        self.m = content.parse_manifest(manifest_dict(dll_urls=[BASE + "/bad.dll", MIRROR + "/d3d9.dll"]))
        routes = good_routes()
        routes[BASE + "/bad.dll"] = FakeResponse(body=b"tampered!!")
        routes[MIRROR + "/d3d9.dll"] = FakeResponse(body=DLL)
        s = FakeSession(routes)
        self.apply("ultra", session=s)
        self.assertEqual(self.read("d3d9.dll"), DLL)
        self.assertIn(BASE + "/bad.dll", s.calls)

    def test_download_failure_leaves_client_untouched(self):
        routes = good_routes()
        routes[BASE + "/dxvk/d3d9.dll"] = FakeResponse(body=b"tampered!!")
        with self.assertRaises(content.ApplyError):
            self.apply("ultra", session=FakeSession(routes))
        self.assertFalse(os.path.exists(self.p("d3d9.dll")))
        self.assertEqual(gameutils.read_config_wtf(self.gd)["farclip"], "777")
        self.assertFalse(os.path.exists(self.p("PLGames", "state.json")))

    def test_failure_mid_apply_rolls_back(self):
        real = gameutils.toggle_mpq

        def flaky(gp, name, folder, enable):
            return False if name == "Patch-ruRU-V.mpq" else real(gp, name, folder, enable)

        with mock.patch.object(gameutils, "toggle_mpq", side_effect=flaky):
            with self.assertRaises(content.ApplyError):
                self.apply("classic")
        self.assertTrue(os.path.isfile(self.p("Data", "ruRU", "patch-ruRU-4.MPQ")))
        self.assertFalse(os.path.exists(self.p("Data", "ruRU", "patch-ruRU-4.MPQ.disabled")))
        self.assertFalse(os.path.exists(self.p("PLGames", "state.json")))

    def test_refuses_while_game_running(self):
        with self.assertRaises(content.ApplyError) as cm:
            self.apply("classic", is_running=lambda name: True)
        self.assertIn("Закройте игру", str(cm.exception))

    def test_no_actions_only_records_edition(self):
        for name in ("patch-ruRU-4.MPQ", "patch-ruRU-5.MPQ", "Patch-ruRU-V.mpq"):
            gameutils.toggle_mpq(self.gd, name, "Data/ruRU", False)
        self.apply("classic", is_running=lambda name: True)  # игра запущена, но менять нечего
        self.assertEqual(content.load_state(self.gd)["edition"], "classic")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class _DropAfter(FakeResponse):
    """Ответ, у которого соединение рвётся после первых `keep` байт."""

    def __init__(self, body, keep, status=200):
        super().__init__(status=status, body=body)
        self.keep = keep

    def iter_content(self, chunk):
        yield self.body[:self.keep]
        raise ConnectionError("connection reset")


class ScriptedSession:
    """Отдаёт ответы по очереди и запоминает заголовки запросов."""

    def __init__(self, script):
        self.script, self.calls = script, []

    def get(self, url, headers=None, **kw):
        self.calls.append((url, dict(headers or {})))
        queue = self.script.get(url)
        if not queue:
            raise ConnectionError("unreachable " + url)
        resp = queue.pop(0)
        return resp(headers or {}) if callable(resp) else resp


class DownloadResumeTests(unittest.TestCase):
    """Большие файлы: докачка с места обрыва и кэш скачанного между попытками."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.gd = make_client(self.tmp)
        self.m = content.parse_manifest(manifest_dict())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_ultra(self, session, cancel=None):
        state = content.load_state(self.gd)
        st = content.component_status(self.m, self.gd, state)
        ed = next(e for e in self.m.editions if e.id == "ultra")
        acts = content.plan(self.m, st, state, set(ed.components))
        return content.Executor(self.m, self.gd, state, session=session, is_running=NOT_RUNNING,
                                cancel=cancel).run(acts, edition="ultra")

    def read(self, rel):
        with open(os.path.join(self.gd, rel), "rb") as f:
            return f.read()

    def test_resumes_after_connection_drop(self):
        def rest(headers):
            self.assertEqual(headers.get("Range"), "bytes=5-")
            return FakeResponse(status=206, body=DLL[5:])

        s = ScriptedSession({BASE + "/dxvk/d3d9.dll": [_DropAfter(DLL, 5), rest],
                             BASE + "/dxvk/dxvk.conf": [FakeResponse(body=CONF)]})
        self.run_ultra(s)
        self.assertEqual(self.read("d3d9.dll"), DLL)

    def test_server_without_range_restarts_file(self):
        s = ScriptedSession({BASE + "/dxvk/d3d9.dll": [_DropAfter(DLL, 5), FakeResponse(body=DLL)],
                             BASE + "/dxvk/dxvk.conf": [FakeResponse(body=CONF)]})
        self.run_ultra(s)
        self.assertEqual(self.read("d3d9.dll"), DLL)

    def test_finished_downloads_survive_a_failed_run(self):
        first = ScriptedSession({BASE + "/dxvk/d3d9.dll": [FakeResponse(body=DLL)],
                                 BASE + "/dxvk/dxvk.conf": [FakeResponse(body=b"tampered")]})
        with self.assertRaises(content.ApplyError):
            self.run_ultra(first)
        second = ScriptedSession({BASE + "/dxvk/dxvk.conf": [FakeResponse(body=CONF)]})
        self.run_ultra(second)  # d3d9.dll второй раз не качается: в маршрутах его уже нет
        self.assertEqual(self.read("d3d9.dll"), DLL)
        self.assertEqual([u for u, _ in second.calls], [BASE + "/dxvk/dxvk.conf"])
        cache = os.path.join(self.gd, "PLGames", "downloads")
        self.assertEqual(os.listdir(cache), [])  # всё уехало в клиент

    def test_cancel_keeps_partial_file_for_next_run(self):
        import threading
        cancel = threading.Event()

        class CancelMidway(FakeResponse):
            def iter_content(self, chunk):
                yield DLL[:7]
                cancel.set()
                yield DLL[7:]

        first = ScriptedSession({BASE + "/dxvk/d3d9.dll": [CancelMidway(body=DLL)]})
        with self.assertRaises(content.ApplyCancelled):
            self.run_ultra(first, cancel=cancel)
        second = ScriptedSession({BASE + "/dxvk/d3d9.dll": [lambda h: FakeResponse(status=206, body=DLL[7:])],
                                  BASE + "/dxvk/dxvk.conf": [FakeResponse(body=CONF)]})
        self.run_ultra(second)
        self.assertEqual(self.read("d3d9.dll"), DLL)
        self.assertEqual(second.calls[0][1].get("Range"), "bytes=7-")

    def test_identical_file_already_in_client_is_not_downloaded(self):
        with open(os.path.join(self.gd, "d3d9.dll"), "wb") as f:
            f.write(DLL)
        s = ScriptedSession({BASE + "/dxvk/dxvk.conf": [FakeResponse(body=CONF)]})
        self.run_ultra(s)
        self.assertEqual(self.read("d3d9.dll"), DLL)
        self.assertNotIn("d3d9.dll", content.load_state(self.gd)["backups"])
        self.assertEqual([u for u, _ in s.calls], [BASE + "/dxvk/dxvk.conf"])


def make_zip(entries):
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


ADDON_ZIP = make_zip({"Questie/Questie.toc": b"## Interface: 30300\n", "Questie/Core.lua": b"print(1)",
                      "Questie/Media/icon.blp": b"BLP2", "Questie/README.png": b"skip me"})
PKG_ZIP = make_zip({"runtime/python.exe": b"MZ", "app/install.py": b"#"})


def ext_manifest(addon_zip=ADDON_ZIP, pkg_zip=PKG_ZIP):
    d = manifest_dict()
    d["components"] += [
        {"id": "addon_questie", "name": "Questie", "group": "Квесты и карта", "type": "zip", "version": "1",
         "scope": "addon", "description": "Квесты на карте", "author": "Questie team", "license": "GPL-3.0",
         "archive": {"size": len(addon_zip), "sha256": sha(addon_zip), "urls": [BASE + "/questie.zip"]},
         "target": "Interface/AddOns", "folders": ["Questie"]},
        {"id": "northlight", "name": "Northlight", "group": "Свет", "type": "installer", "version": "0.3",
         "conflicts": ["dxvk"],
         "archive": {"size": len(pkg_zip), "sha256": sha(pkg_zip), "urls": [BASE + "/nl.zip"]},
         "install": ["runtime/python.exe", "app/install.py", "--client", "{client}", "--locale", "{locale}"],
         "uninstall": ["runtime/python.exe", "app/install.py", "uninstall", "--client", "{client}"],
         "progress": r"^\s*(?P<label>\w+): (?P<pct>\d+)%",
         "marker": "northlight-renderer.ini"},
    ]
    d["editions"].append({"id": "forever", "name": "Forever",
                          "components": ["hd_textures", "gfx_ultra", "northlight"]})
    return d


def ext_routes():
    r = good_routes()
    r[BASE + "/questie.zip"] = FakeResponse(body=ADDON_ZIP)
    r[BASE + "/nl.zip"] = FakeResponse(body=PKG_ZIP)
    return r


class ExtendedTypesParseTests(unittest.TestCase):
    def test_parses_zip_and_installer(self):
        m = content.parse_manifest(ext_manifest())
        q, n = m.component("addon_questie"), m.component("northlight")
        self.assertEqual((q.scope, q.target, q.folders), ("addon", "Interface/AddOns", ("Questie",)))
        self.assertEqual(n.install[0], "runtime/python.exe")
        self.assertEqual(n.marker, "northlight-renderer.ini")

    def test_rejects_bad_extended_components(self):
        cases = [
            lambda c: c[-2].update(folders=["../evil"]),
            lambda c: c[-2].update(target="C:/Windows"),
            lambda c: c[-2].update(scope="everything"),
            lambda c: c[-2]["archive"].update(urls=["http://x/q.zip"]),
            lambda c: c[-1].update(install=["../../cmd.exe", "/c"]),
            lambda c: c[-1].update(install=[]),
            lambda c: c[-1].update(marker="../outside.ini"),
            lambda c: c[-1].update(progress="(unclosed"),
        ]
        for i, breaker in enumerate(cases):
            d = ext_manifest()
            breaker(d["components"])
            with self.assertRaises(content.ManifestError, msg=f"case {i}"):
                content.parse_manifest(d)

    def test_addon_cannot_be_part_of_edition(self):
        d = ext_manifest()
        d["editions"][0]["components"] = ["addon_questie"]
        with self.assertRaises(content.ManifestError):
            content.parse_manifest(d)


def fallback_manifest():
    """Forever из ext_manifest, где Northlight без Vulkan 1.3 заменяется на DXVK."""
    d = ext_manifest()
    d["components"][-1].update(requires="vulkan13", fallback="dxvk")
    return d


class RequirementFallbackTests(unittest.TestCase):
    def test_parses_requires_and_fallback(self):
        n = content.parse_manifest(fallback_manifest()).component("northlight")
        self.assertEqual((n.requires, n.fallback), ("vulkan13", "dxvk"))

    def test_rejects_bad_requirements(self):
        cases = [
            lambda c: c[-1].update(requires="raytracing"),
            lambda c: c[-1].update(fallback="nope"),
            lambda c: c[-1].update(fallback="addon_questie"),
            lambda c: c[-1].pop("requires"),
            lambda c: c[3].update(requires="vulkan13"),  # у замены не может быть своих требований
        ]
        for i, breaker in enumerate(cases):
            d = fallback_manifest()
            breaker(d["components"])
            with self.assertRaises(content.ManifestError, msg=f"case {i}"):
                content.parse_manifest(d)

    def test_resolve_swaps_component_when_pc_lacks_capability(self):
        m = content.parse_manifest(fallback_manifest())
        ids = ("hd_textures", "gfx_ultra", "northlight")
        self.assertEqual(content.resolve_components(m, ids, {"vulkan13"}), ids)
        self.assertEqual(content.resolve_components(m, ids, set()), ("hd_textures", "gfx_ultra", "dxvk"))
        self.assertEqual(content.resolve_components(m, ("dxvk", "northlight"), set()), ("dxvk",))

    def test_edition_with_fallback_in_place_is_still_detected(self):
        m = content.parse_manifest(fallback_manifest())
        tmp = tempfile.mkdtemp()
        try:
            gd = make_client(tmp)
            state = content.load_state(gd)
            st = content.component_status(m, gd, state)
            target = set(content.resolve_components(m, m.editions[-1].components, set()))
            content.Executor(m, gd, state, session=FakeSession(ext_routes()), is_running=NOT_RUNNING,
                             installers_dir=os.path.join(tmp, "inst")).run(
                content.plan(m, st, state, target), edition="forever")
            st = content.component_status(m, gd, content.load_state(gd))
            self.assertTrue(st["dxvk"]["active"])
            self.assertFalse(st["northlight"]["active"])
            self.assertEqual(content.detect_edition(m, st), "forever")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class AddonScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.gd = make_client(self.tmp)
        self.inst = os.path.join(self.tmp, "installers")
        self.m = content.parse_manifest(ext_manifest())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_plan(self, target, scope="edition", edition=None, session=None):
        state = content.load_state(self.gd)
        st = content.component_status(self.m, self.gd, state)
        acts = content.plan(self.m, st, state, set(target), scope=scope)
        ex = content.Executor(self.m, self.gd, state, session=session or FakeSession(ext_routes()),
                              is_running=NOT_RUNNING, installers_dir=self.inst)
        return ex.run(acts, edition=edition)

    def addon_dir(self, *parts):
        return os.path.join(self.gd, "Interface", "AddOns", *parts)

    def test_addon_installs_only_addon_files(self):
        self.run_plan({"addon_questie"}, scope="addon")
        with open(self.addon_dir("Questie", "Core.lua"), "rb") as f:
            self.assertEqual(f.read(), b"print(1)")
        self.assertTrue(os.path.isfile(self.addon_dir("Questie", "Media", "icon.blp")))
        self.assertFalse(os.path.exists(self.addon_dir("Questie", "README.png")))
        st = content.component_status(self.m, self.gd, content.load_state(self.gd))
        self.assertTrue(st["addon_questie"]["active"])

    def test_edition_switch_keeps_addons_and_edition_detection_ignores_them(self):
        self.run_plan({"addon_questie"}, scope="addon")
        ed = next(e for e in self.m.editions if e.id == "classic")
        self.run_plan(set(ed.components), edition="classic")
        self.assertTrue(os.path.isfile(self.addon_dir("Questie", "Core.lua")))
        st = content.component_status(self.m, self.gd, content.load_state(self.gd))
        self.assertEqual(content.detect_edition(self.m, st), "classic")

    def test_addon_removal_deletes_folder(self):
        self.run_plan({"addon_questie"}, scope="addon")
        self.run_plan(set(), scope="addon")
        self.assertFalse(os.path.exists(self.addon_dir("Questie")))

    def test_catalog_addon_installed_by_hand_is_reported_as_foreign(self):
        os.makedirs(self.addon_dir("Questie"))
        st = content.component_status(self.m, self.gd, content.load_state(self.gd))
        self.assertFalse(st["addon_questie"]["foreign"])  # пустая папка из раздачи клиента — не аддон
        with open(self.addon_dir("Questie", "Questie.toc"), "w") as f:
            f.write("## Interface: 30300\n")
        st = content.component_status(self.m, self.gd, content.load_state(self.gd))
        self.assertEqual((st["addon_questie"]["active"], st["addon_questie"]["foreign"]), (False, True))
        self.run_plan({"addon_questie"}, scope="addon")
        st = content.component_status(self.m, self.gd, content.load_state(self.gd))
        self.assertEqual((st["addon_questie"]["active"], st["addon_questie"]["foreign"]), (True, False))
        self.assertFalse(st["northlight"]["foreign"])

    def test_players_own_copy_is_kept_aside(self):
        os.makedirs(self.addon_dir("Questie"))
        with open(self.addon_dir("Questie", "Old.lua"), "wb") as f:
            f.write(b"old")
        self.run_plan({"addon_questie"}, scope="addon")
        self.assertFalse(os.path.exists(self.addon_dir("Questie", "Old.lua")))
        kept = os.path.join(self.gd, "PLGames", "backup", "kept")
        found = [os.path.join(r, n) for r, _, ns in os.walk(kept) for n in ns]
        self.assertTrue(any(p.endswith(os.path.join("Questie", "Old.lua")) for p in found))

    def test_archive_with_executable_or_escape_is_refused_untouched(self):
        for bad in ({"Questie/Questie.toc": b"x", "Questie/run.exe": b"MZ"},
                    {"Questie/Questie.toc": b"x", "Questie/../../evil.lua": b"x"}):
            z = make_zip(bad)
            self.m = content.parse_manifest(ext_manifest(addon_zip=z))
            routes = ext_routes()
            routes[BASE + "/questie.zip"] = FakeResponse(body=z)
            with self.assertRaises(content.ApplyError):
                self.run_plan({"addon_questie"}, scope="addon", session=FakeSession(routes))
            self.assertFalse(os.path.exists(self.addon_dir("Questie")))


class InstallerTypeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.gd = make_client(self.tmp)
        self.inst = os.path.join(self.tmp, "installers")
        self.m = content.parse_manifest(ext_manifest())
        self.calls = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake_runner(self, fail=False):
        def run(argv, cwd, on_line):
            self.calls.append((list(argv), cwd))
            if "uninstall" in argv:
                os.remove(os.path.join(self.gd, "northlight-renderer.ini"))
                return 0
            on_line("  Northrend: 50% (566/1131 tiles)")
            if fail:
                on_line("ERROR: world cache failed")
                return 1
            with open(os.path.join(self.gd, "northlight-renderer.ini"), "w") as f:
                f.write("[Renderer]\n")
            return 0
        return run

    def apply(self, edition, runner):
        state = content.load_state(self.gd)
        st = content.component_status(self.m, self.gd, state)
        ed = next(e for e in self.m.editions if e.id == edition)
        acts = content.plan(self.m, st, state, set(ed.components))
        seen = []
        ex = content.Executor(self.m, self.gd, state, session=FakeSession(ext_routes()), is_running=NOT_RUNNING,
                              installers_dir=self.inst, progress=lambda **kw: seen.append(kw))
        with mock.patch.object(content, "_run_process", side_effect=runner):
            ex.run(acts, edition=edition)
        return seen

    def test_install_runs_package_command_with_client_and_locale(self):
        seen = self.apply("forever", self.fake_runner())
        argv, cwd = self.calls[0]
        self.assertTrue(argv[0].endswith(os.path.join("runtime", "python.exe")))
        self.assertTrue(os.path.isfile(argv[0]))
        self.assertIn(self.gd, argv)
        self.assertEqual(argv[argv.index("--locale") + 1], "ruRU")
        self.assertTrue(any("Northrend: 50%" in str(kw.get("text")) for kw in seen))
        st = content.component_status(self.m, self.gd, content.load_state(self.gd))
        self.assertTrue(st["northlight"]["active"])
        self.assertEqual(content.detect_edition(self.m, st), "forever")

    def test_failed_install_is_reported_and_rolled_back(self):
        with self.assertRaises(content.ApplyError) as cm:
            self.apply("forever", self.fake_runner(fail=True))
        self.assertIn("world cache failed", str(cm.exception))
        self.assertEqual(gameutils.read_config_wtf(self.gd)["farclip"], "777")
        self.assertFalse(os.path.exists(os.path.join(self.gd, "PLGames", "state.json")))

    def test_leaving_edition_runs_uninstaller(self):
        self.apply("forever", self.fake_runner())
        self.apply("classic", self.fake_runner())
        self.assertIn("uninstall", self.calls[-1][0])
        self.assertFalse(os.path.exists(os.path.join(self.gd, "northlight-renderer.ini")))
        self.assertNotIn("northlight", content.load_state(self.gd)["components"])
