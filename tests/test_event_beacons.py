"""Метки событий: серверный скрипт 62_plg_event_beacons.lua и аддон PLGames_Events в Lua 5.1 (пакет lupa).

Без lupa тесты пропускаются; серверные — ещё и вне репозитория WOW (в CI лаунчера скрипта нет)."""

import math
import os
import unittest

try:
    from lupa import lua51
except ImportError:  # pragma: no cover
    lua51 = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON = os.path.join(ROOT, "addons", "PLGames_Events")
# серверные скрипты: рядом в репозитории WOW или там, куда указывает PLG_SERVER_SCRIPTS
SERVER = os.environ.get("PLG_SERVER_SCRIPTS") or os.path.join(ROOT, "..", "data", "lua", "scripts")
BEACONS = os.path.join(SERVER, "62_plg_event_beacons.lua")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# Заглушка любого фрейма WoW: любой метод — пустышка, арифметика с ней даёт 0.
WOW_STUBS = r"""
local stubmt = {}
function stub()
    return setmetatable({}, stubmt)
end
stubmt.__index = function() return function() return stub() end end
stubmt.__add = function() return 0 end
stubmt.__sub = function() return 0 end
stubmt.__mul = function() return 0 end
stubmt.__div = function() return 0 end
stubmt.__unm = function() return 0 end
stubmt.__concat = function() return "" end
CreateFrame = function() return stub() end
WorldMapButton, WorldMapFrame, Minimap, MinimapCluster, UIParent = stub(), stub(), stub(), stub(), stub()
GameTooltip, WorldMapTooltip, DEFAULT_CHAT_FRAME = stub(), stub(), stub()
SlashCmdList = {}
CLOCK = 1000
GetTime = function() return CLOCK end
UnitName = function() return "Олег" end
SENT = {}
SendAddonMessage = function(p, m, c, t) SENT[#SENT + 1] = m end
unpack = unpack or table.unpack
"""


@unittest.skipIf(lua51 is None, "нужен пакет lupa (pip install lupa)")
class AddonTests(unittest.TestCase):
    def setUp(self):
        self.lua = lua51.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(WOW_STUBS)
        for name in ("MapAreas.lua", "Core.lua", "Map.lua", "Minimap.lua", "List.lua"):
            self.lua.execute(read(os.path.join(ADDON, name)))
        self.E = self.lua.globals().PLGamesEvents
        self.E.IndexAreas(self.lua.globals().PLGamesEventsMapAreas)

    def msg(self, text, sender="Олег", channel="WHISPER"):
        self.E.OnAddonMessage("PLGEV", text, channel, sender)

    def beacon(self, bid):
        return self.E.beacons[bid]

    def test_protocol_from_self_only(self):
        self.msg("B^ev17^event^H^1^17^-471^-2607^300^Сбор ресурсов^Степи (Перекрёсток)")
        b = self.beacon("ev17")
        self.assertEqual((b.kind, b.fac, b.map, b.zone, b.x, b.y), ("event", "H", 1, 17, -471, -2607))
        self.assertEqual(b.endsAt, 1300)
        self.assertEqual(b.sub, "Степи (Перекрёсток)")
        self.msg("B^fake^boss^N^1^17^0^0^0^Подделка^", sender="Злодей")
        self.msg("B^fake^boss^N^1^17^0^0^0^Подделка^", channel="GUILD")
        self.assertIsNone(self.beacon("fake"))
        self.msg("P^ev17^-480^-2600")
        self.msg("T^ev17^0")
        b = self.beacon("ev17")
        self.assertEqual((b.x, b.y, b.endsAt), (-480, -2600, None))
        self.msg("E^ev17")
        self.assertIsNone(self.beacon("ev17"))
        self.msg("B^a^event^N^1^17^1^1^0^Пустая подпись^")
        self.assertEqual(self.beacon("a").sub, "")
        self.msg("S")
        self.assertIsNone(self.beacon("a"))

    def test_world_to_map_on_known_point(self):
        areas = self.lua.globals().PLGamesEventsMapAreas
        nx, ny = self.E.WorldToMap(areas[11], -471, -2607)  # центр Перекрёстка на карте Степей
        self.assertAlmostEqual(nx, 0.516, places=2)
        self.assertAlmostEqual(ny, 0.308, places=2)
        x, y = self.E.MapToWorld(areas[11], nx, ny)
        self.assertAlmostEqual(x, -471, places=3)
        self.assertAlmostEqual(y, -2607, places=3)
        self.assertEqual(self.E.areaToWma[17], 11)
        self.assertEqual(self.E.continentWma[1], 13)

    def test_pin_shows_on_own_zone_and_continent_only(self):
        self.msg("B^ev17^event^H^1^17^-471^-2607^0^Сбор^")
        b = self.beacon("ev17")
        self.assertIsNotNone(self.E.PlaceOn(11, b)[0])   # Степи
        self.assertIsNotNone(self.E.PlaceOn(13, b)[0])   # Калимдор
        self.assertIsNone(self.E.PlaceOn(4, b))          # Дуротар — чужая зона
        self.assertIsNone(self.E.PlaceOn(14, b))         # Восточные королевства

    def test_minimap_offsets(self):
        # метка в 100 ярдах к северу, миникарта 466⅔ ярда поперёк, радиус 70 px
        r, u, far = self.E.MinimapOffset(0, 0, 100, 0, 466 + 2 / 3, 70, None, False)
        self.assertAlmostEqual(r, 0, places=6)
        self.assertAlmostEqual(u, 100 * 70 / (233 + 1 / 3), places=6)
        self.assertFalse(far)
        # к западу (y растёт) — влево
        r, u, _ = self.E.MinimapOffset(0, 0, 0, 100, 466 + 2 / 3, 70, None, False)
        self.assertLess(r, 0)
        # игрок смотрит на запад (π/2), миникарта вращается: север оказывается справа
        r, u, _ = self.E.MinimapOffset(0, 0, 100, 0, 466 + 2 / 3, 70, math.pi / 2, False)
        self.assertGreater(r, 0)
        self.assertAlmostEqual(u, 0, places=6)
        # далеко — прижата к краю круга
        r, u, far = self.E.MinimapOffset(0, 0, 5000, 0, 466 + 2 / 3, 70, None, False)
        self.assertTrue(far)
        self.assertAlmostEqual(math.hypot(r, u), 70 - 7, places=6)

    def test_expired_marks_are_swept_and_list_is_sorted(self):
        self.msg("B^late^event^N^1^17^0^0^10^Старое^")
        self.msg("B^soon^soon^N^1^17^0^0^600^Скоро^")
        self.msg("B^open^chain^N^1^17^0^0^0^Без таймера^")
        self.assertEqual([b.id for b in self.E.Sorted().values()], ["late", "soon", "open"])
        self.assertFalse(self.E.Sweep(1000 + 10 + 30))
        self.assertTrue(self.E.Sweep(1000 + 10 + 61))
        self.assertIsNone(self.beacon("late"))
        self.assertEqual(self.E.TimeLeft(self.beacon("soon")), "10:00")


@unittest.skipIf(lua51 is None or not os.path.isfile(BEACONS), "нужны lupa и репозиторий WOW со скриптом сервера")
class ServerBeaconsTests(unittest.TestCase):
    STUBS = r"""
    BUS = {}
    LW_EventBus = {
        Subscribe = function(name, fn) BUS[name] = BUS[name] or {}; table.insert(BUS[name], fn) end,
        Publish = function(name, data) for _, fn in ipairs(BUS[name] or {}) do fn(data) end end,
    }
    PLAYER_EVENTS, SERVER_EVENTS = {}, {}
    RegisterPlayerEvent = function(id, fn) PLAYER_EVENTS[id] = fn end
    RegisterServerEvent = function(id, fn) SERVER_EVENTS[id] = fn end
    INBOX = {}
    local function player(name)
        local p = { name = name }
        function p:SendAddonMessage(prefix, msg, channel, receiver)
            INBOX[#INBOX + 1] = { to = self.name, prefix = prefix, msg = msg, channel = channel, receiver = receiver.name }
        end
        function p:RegisterEvent(fn, delay, repeats) fn(1, delay, repeats, self) end
        return p
    end
    PLAYERS = { player("Олег"), player("Анна") }
    GetPlayersInWorld = function() return PLAYERS end
    print = function() end
    LW_Config = { GetZone = function(id) return ZONES[id] end }
    ZONES = { [17] = { zone_name = "Степи (Перекрёсток)", faction = "horde", center_map = 1, center_x = -471, center_y = -2607 } }
    LW_Utils = { IsCreatureValid = function(c) return c ~= nil and c.valid end }
    LW_EventManager = { _activeEvents = {}, _definitions = { resource_gathering = { display_name_ru = "Сбор ресурсов" } } }
    LW_WorldBosses = { _bosses = {}, _activeInstances = {}, _respawnTimers = {}, CFG = { BERSERK_SECONDS = 900, RAMPAGE_GRACE = 180 } }
    LW_EventChains = { _chains = {}, _nodes = {}, _activeChains = {} }
    CARAVAN = nil
    PLG_CaravanPayload = { GetActive = function() return CARAVAN end }
    BUILDS = {}
    LW_Construction = { GetConstructing = function() return BUILDS end }
    """

    def setUp(self):
        self.lua = lua51.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(self.STUBS)
        self.lua.execute(read(BEACONS))
        self.g = self.lua.globals()
        self.B = self.g.PLG_EventBeacons
        self.now = self.lua.eval("os.time()")

    def inbox(self, to="Олег"):
        msgs = [m.msg for m in self.g.INBOX.values() if m.to == to]
        self.lua.execute("INBOX = {}")
        return msgs

    def tick(self):
        self.lua.execute("for _, fn in ipairs(BUS.tick_5s) do fn({}) end")
        return self.inbox()

    def test_zone_event_appears_pauses_and_ends(self):
        self.lua.execute("LW_EventManager._activeEvents[17] = { type = 'resource_gathering', endTime = os.time() + 300 }")
        msgs = self.tick()
        self.assertEqual(len(msgs), 1)
        f = msgs[0].split("^")
        self.assertEqual(f[:9], ["B", "ev17", "event", "H", "1", "17", "-471", "-2607", f[8]])
        self.assertTrue(298 <= int(f[8]) <= 300)
        self.assertEqual(f[9:], ["Сбор ресурсов", "Степи (Перекрёсток)"])
        self.assertEqual(self.tick(), [])  # ничего не изменилось — ничего не шлём
        self.lua.execute("LW_EventManager._activeEvents[17].paused = true")
        paused = self.tick()[0].split("^")
        self.assertEqual((paused[8], paused[10]), ("0", "ждёт игроков рядом"))
        self.lua.execute("LW_EventManager._activeEvents[17] = nil")
        self.assertEqual(self.tick(), ["E^ev17"])
        # все игроки получают одно и то же, сообщение — от игрока самому себе
        self.lua.execute("LW_EventManager._activeEvents[17] = { type = 'resource_gathering', endTime = os.time() + 300 }")
        self.B.Reconcile()
        for m in self.g.INBOX.values():
            self.assertEqual((m.prefix, m.channel, m.to), ("PLGEV", 7, m.receiver))

    def test_world_boss_soon_then_fight_then_moves(self):
        self.lua.execute("""
            LW_WorldBosses._bosses[100180] = { name_ru = 'Каменный Великан', zone_id = 17, spawn_map = 1,
                                               spawn_x = -500, spawn_y = -2700 }
            LW_WorldBosses._respawnTimers[100180] = os.time() + 3600
        """)
        self.assertEqual(self.tick(), [])  # больше 30 мин до появления — метки нет
        self.lua.execute("LW_WorldBosses._respawnTimers[100180] = os.time() + 600")
        self.assertEqual(self.tick()[0].split("^")[2], "soon")
        self.lua.execute("""
            BOSS = { valid = true, x = -500, y = -2700 }
            function BOSS.GetX(c) return c.x end
            function BOSS.GetY(c) return c.y end
            LW_WorldBosses._activeInstances[100180] = { creature = BOSS, spawnTime = os.time() }
        """)
        fight = self.tick()[0].split("^")
        self.assertEqual((fight[2], fight[10]), ("boss", "мировой босс"))
        self.assertTrue(1078 <= int(fight[8]) <= 1080)  # 15 мин до ярости + 3 мин до ухода
        self.lua.execute("BOSS.x = -503")
        self.assertEqual(self.tick(), [])  # сдвиг меньше 8 ярдов не шлём
        self.lua.execute("BOSS.x = -540")
        self.assertEqual(self.tick(), ["P^boss100180^-540^-2700"])
        # исчез молча (BossAIUpdate: невалиден → инстанс снят, следующий спавн через respawn_hours)
        self.lua.execute("""
            BOSS.valid = false
            LW_WorldBosses._activeInstances[100180] = nil
            LW_WorldBosses._respawnTimers[100180] = os.time() + 7200
        """)
        self.assertEqual(self.tick(), ["E^boss100180"])

    def test_caravan_chain_and_build(self):
        self.lua.execute("""
            CARAVAN = { region = 'Степи', from = 'Перекрёсток', to = 'Оргриммар', map = 1, zone = 17, owner = 1,
                        x = -471, y = -2607, wp = 3, wps = 10, start_time = os.time(), max_duration = 2700 }
            LW_EventChains._chains[2] = { chain_name = 'Тень над Степями' }
            LW_EventChains._nodes[2] = { [5] = { description_ru = 'Отбейте кочевников', duration = 600 } }
            LW_EventChains._activeChains[2] = { zone_id = 17, current_node_id = 5, nodeStartTime = os.time() }
            BUILDS = { { zone_id = 17, building_type = 'forge', tier = 2, name_ru = 'Кузница', map = 1,
                         x = -453, y = -2597, end_time = os.time() + 900 } }
        """)
        msgs = {m.split("^")[1]: m.split("^") for m in self.tick()}
        self.assertEqual(sorted(msgs), ["bd17forge", "car", "ch2"])
        self.assertEqual(msgs["car"][3], "H")
        self.assertEqual(msgs["car"][9:], ["Караван: Перекрёсток → Оргриммар", "Степи, пройдено 20%"])
        self.assertEqual(msgs["ch2"][6], "-451")  # севернее центра зоны, чтобы не лечь на метку события
        self.assertEqual(msgs["bd17forge"][9], "Стройка: Кузница (тир 2)")
        self.lua.execute("CARAVAN.x = -400")
        self.assertEqual(self.tick(), ["P^car^-400^-2607"])

    def test_text_is_cleaned_and_messages_fit_the_client_limit(self):
        clean = self.B.Clean("|cffFF0000Опасно|r: a^b|c\nd", 40)
        self.assertEqual(clean, "Опасно: a b c d")
        self.assertEqual(self.B.Clean("Ёжик" * 30, 5), "ЁжикЁ")
        self.lua.execute("""
            ZONES[17].zone_name = string.rep('Очень длинное название зоны ', 10)
            LW_EventManager._definitions.resource_gathering.display_name_ru = string.rep('Сбор', 40)
            LW_EventManager._activeEvents[17] = { type = 'resource_gathering', endTime = os.time() + 99999 }
        """)
        msg = self.tick()[0]
        self.assertLessEqual(len(("PLGEV\t" + msg).encode("utf-8")), 255)

    def test_login_gets_full_list_and_addon_can_ask_again(self):
        self.lua.execute("LW_EventManager._activeEvents[17] = { type = 'resource_gathering', endTime = os.time() + 300 }")
        self.B.Reconcile()
        self.inbox()
        self.lua.execute("PLAYER_EVENTS[3](3, PLAYERS[2])")
        msgs = self.inbox("Анна")
        self.assertEqual(msgs[0], "S")
        self.assertEqual([m.split("^")[1] for m in msgs[1:]], ["ev17"])
        self.lua.execute("SERVER_EVENTS[30](30, PLAYERS[1], 7, 'PLGEV', 'H', PLAYERS[1])")
        self.assertEqual(self.inbox()[0], "S")

    def test_server_scripts_with_getters_compile(self):
        for name in ("13_lw_construction.lua", "54_plg_caravan_payload.lua", "62_plg_event_beacons.lua"):
            ok, err = self.lua.eval("function(src, name) local f, e = loadstring(src, name) return f ~= nil, e end")(
                read(os.path.join(SERVER, name)), name)
            self.assertTrue(ok, err)
