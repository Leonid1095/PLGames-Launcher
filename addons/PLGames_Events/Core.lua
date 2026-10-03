--[[ ============================================================
  PLGames Events — метки событий сервера на карте.

  Сервер (скрипт 61_plg_event_beacons) шлёт скрытые сообщения с префиксом PLGEV
  от игрока самому себе. Этот файл принимает их, хранит метки и раздаёт остальным
  частям аддона: Map.lua (карта мира), Minimap.lua (миникарта), List.lua (список).

  Протокол (поля через ^, время — секунды ДО конца):
    S — дальше полный список       B^id^вид^фракция^карта^зона^x^y^сек^название^подпись
    P^id^x^y — сдвиг   T^id^сек — новый таймер   E^id — убрать

  Команды: /plgev — список вкл/выкл, /plgev test — пробная метка, /plgev clear,
           /plgev minimap — метки на миникарте вкл/выкл.
============================================================ ]]

PLGamesEvents = PLGamesEvents or {}
local E = PLGamesEvents

E.PREFIX = "PLGEV"
E.beacons = {}          -- id -> метка
E.listeners = {}        -- функции, которые перерисовывают метки после изменений

E.FACTION_COLORS = {
    H = { 0.85, 0.18, 0.18 },
    A = { 0.20, 0.45, 0.95 },
    N = { 1.00, 0.78, 0.20 },
}
E.ICONS = {
    boss = "Interface\\Icons\\INV_Misc_Bone_HumanSkull_01",
    soon = "Interface\\Icons\\INV_Misc_Bone_HumanSkull_01",
    event = "Interface\\Icons\\Ability_Warrior_BattleShout",
    caravan = "Interface\\Icons\\Ability_Mount_Kodo_03",
    chain = "Interface\\Icons\\INV_Misc_Map_01",
    build = "Interface\\Icons\\Trade_Engineering",
}

-- ------------------------------------------------------------
-- Зоны карты мира (MapAreas.lua) и пересчёт координат
-- ------------------------------------------------------------
E.areaToWma = {}        -- id зоны (AreaTable) -> id WorldMapArea
E.continentWma = {}     -- id карты -> id WorldMapArea континента

function E.IndexAreas(areas)
    E.areas = areas or {}
    E.areaToWma, E.continentWma = {}, {}
    local best = {}
    for wma, r in pairs(E.areas) do
        local map, area = r[1], r[2]
        if area ~= 0 then
            if not E.areaToWma[area] or wma < E.areaToWma[area] then E.areaToWma[area] = wma end
        else
            local size = math.abs(r[3] - r[4]) * math.abs(r[5] - r[6])
            if not best[map] or size > best[map] then best[map], E.continentWma[map] = size, wma end
        end
    end
end

-- Мир (x — на север, y — на запад) -> доли карты 0..1 (слева направо, сверху вниз).
function E.WorldToMap(row, x, y)
    local left, right, top, bottom = row[3], row[4], row[5], row[6]
    return (left - y) / (left - right), (top - x) / (top - bottom)
end

function E.MapToWorld(row, nx, ny)
    local left, right, top, bottom = row[3], row[4], row[5], row[6]
    return top - ny * (top - bottom), left - nx * (left - right)
end

-- Где поставить метку на карте, которую сейчас показывает WorldMapArea wma: nx, ny или nil.
function E.PlaceOn(wma, b)
    local row = E.areas and E.areas[wma]
    if not row or row[1] ~= b.map then return nil end
    if row[2] ~= 0 and row[2] ~= b.zone then return nil end
    local nx, ny = E.WorldToMap(row, b.x, b.y)
    if nx < 0 or nx > 1 or ny < 0 or ny > 1 then return nil end
    return nx, ny
end

-- ------------------------------------------------------------
-- Протокол
-- ------------------------------------------------------------
local function split(s)
    local t, start = {}, 1
    while true do
        local i = string.find(s, "^", start, true)
        if not i then t[#t + 1] = string.sub(s, start); return t end
        t[#t + 1] = string.sub(s, start, i - 1)
        start = i + 1
    end
end

local function now() return GetTime() end

function E.Changed()
    for _, fn in ipairs(E.listeners) do pcall(fn) end
end

function E.Apply(msg)
    local f = split(msg)
    local op = f[1]
    if op == "S" then
        E.beacons = {}
    elseif op == "B" and #f >= 11 then
        local secs = tonumber(f[9]) or 0
        E.beacons[f[2]] = {
            id = f[2], kind = f[3], fac = f[4], map = tonumber(f[5]), zone = tonumber(f[6]),
            x = tonumber(f[7]), y = tonumber(f[8]), endsAt = secs > 0 and (now() + secs) or nil,
            title = f[10], sub = f[11],
        }
    elseif op == "P" and E.beacons[f[2]] then
        E.beacons[f[2]].x, E.beacons[f[2]].y = tonumber(f[3]), tonumber(f[4])
    elseif op == "T" and E.beacons[f[2]] then
        local secs = tonumber(f[3]) or 0
        E.beacons[f[2]].endsAt = secs > 0 and (now() + secs) or nil
    elseif op == "E" then
        E.beacons[f[2] or ""] = nil
    else
        return false
    end
    return true
end

-- Только от сервера: сообщение «от себя самого». Шёпот аддона от другого игрока отбрасывается.
function E.OnAddonMessage(prefix, msg, channel, sender)
    if prefix ~= E.PREFIX or channel ~= "WHISPER" or sender ~= UnitName("player") then return end
    if E.Apply(msg or "") then E.Changed() end
end

-- Сколько осталось: «12:05», «1 ч 05 мин» или nil.
function E.TimeLeft(b)
    if not b.endsAt then return nil end
    local s = math.max(0, math.floor(b.endsAt - now()))
    if s >= 3600 then return string.format("%d ч %02d мин", math.floor(s / 3600), math.floor(s % 3600 / 60)) end
    return string.format("%d:%02d", math.floor(s / 60), s % 60)
end

function E.Sorted()
    local list = {}
    for _, b in pairs(E.beacons) do list[#list + 1] = b end
    table.sort(list, function(a, b)
        local ea, eb = a.endsAt or math.huge, b.endsAt or math.huge
        if ea ~= eb then return ea < eb end
        return a.id < b.id
    end)
    return list
end

function E.Color(b)
    return unpack(E.FACTION_COLORS[b.fac] or E.FACTION_COLORS.N)
end

-- ------------------------------------------------------------
-- Зона на карте мира: индекс (континент, зона) для SetMapZoom и TomTom
-- ------------------------------------------------------------
E.zoneIndex = {}        -- WorldMapArea id -> { континент, зона }

function E.BuildZoneIndex()
    if WorldMapFrame and WorldMapFrame:IsShown() then return end
    E.indexing = true
    for c = 1, select("#", GetMapContinents()) do
        SetMapZoom(c)
        E.zoneIndex[GetCurrentMapAreaID()] = { c, 0 }
        for z = 1, select("#", GetMapZones(c)) do
            SetMapZoom(c, z)
            E.zoneIndex[GetCurrentMapAreaID()] = { c, z }
        end
    end
    SetMapToCurrentZone()
    E.indexing = false
end

function E.WmaFor(b)
    return E.areaToWma[b.zone] or E.continentWma[b.map]
end

-- Открыть карту мира на зоне метки
function E.ShowOnMap(b)
    local idx = E.zoneIndex[E.WmaFor(b) or -1]
    if not idx then return end
    if not WorldMapFrame:IsShown() then ShowUIPanel(WorldMapFrame) end
    if idx[2] > 0 then SetMapZoom(idx[1], idx[2]) else SetMapZoom(idx[1]) end
end

-- Стрелка TomTom, если он стоит
function E.Waypoint(b)
    local wma = E.WmaFor(b)
    local idx, row = E.zoneIndex[wma or -1], E.areas[wma or -1]
    if not (TomTom and TomTom.AddZWaypoint and idx and row) then return false end
    local nx, ny = E.WorldToMap(row, b.x, b.y)
    return pcall(TomTom.AddZWaypoint, TomTom, idx[1], idx[2], nx * 100, ny * 100, b.title)
end

-- ------------------------------------------------------------
-- Положение игрока в координатах мира (для миникарты и /plgev test)
-- ------------------------------------------------------------
function E.PlayerWorldPos()
    local row = E.areas[GetCurrentMapAreaID()]
    local px, py = GetPlayerMapPosition("player")
    if not row or (px == 0 and py == 0) then return nil end
    local x, y = E.MapToWorld(row, px, py)
    return x, y, row[1], row[2]
end

-- ------------------------------------------------------------
-- События клиента и команды
-- ------------------------------------------------------------
local frame = CreateFrame("Frame")
frame:RegisterEvent("PLAYER_LOGIN")
frame:RegisterEvent("PLAYER_ENTERING_WORLD")
frame:RegisterEvent("CHAT_MSG_ADDON")
frame:SetScript("OnEvent", function(_, event, ...)
    if event == "CHAT_MSG_ADDON" then
        E.OnAddonMessage(...)
    elseif event == "PLAYER_LOGIN" then
        PLGames_EventsDB = PLGames_EventsDB or {}
        if PLGames_EventsDB.list == nil then PLGames_EventsDB.list = true end
        if PLGames_EventsDB.minimap == nil then PLGames_EventsDB.minimap = true end
        E.IndexAreas(PLGamesEventsMapAreas)
    elseif event == "PLAYER_ENTERING_WORLD" then
        E.BuildZoneIndex()
        if not E.asked then
            E.asked = true  -- после /reload список у клиента пуст — просим сервер прислать его заново
            SendAddonMessage(E.PREFIX, "H", "WHISPER", UnitName("player"))
        end
    end
end)

-- Метка, чьё время вышло больше минуты назад, убирается сама: сервер её уже снял, а сообщение
-- могло потеряться (до полного списка ждать до двух минут).
function E.Sweep(t)
    local changed = false
    for id, b in pairs(E.beacons) do
        if b.endsAt and t - b.endsAt > 60 then
            E.beacons[id] = nil
            changed = true
        end
    end
    return changed
end

local sweepElapsed = 0
frame:SetScript("OnUpdate", function(_, dt)
    sweepElapsed = sweepElapsed + dt
    if sweepElapsed < 5 then return end
    sweepElapsed = 0
    if E.Sweep(now()) then E.Changed() end
end)

local function say(text)
    DEFAULT_CHAT_FRAME:AddMessage("|cff5fb4ff[События]|r " .. text)
end

SLASH_PLGEVENTS1 = "/plgev"
SlashCmdList["PLGEVENTS"] = function(arg)
    arg = string.lower(arg or "")
    if arg == "test" then
        local x, y, map, zone = E.PlayerWorldPos()
        if not x then say("Не удалось определить вашу позицию — откройте и закройте карту и повторите.") return end
        E.beacons.test = { id = "test", kind = "event", fac = "N", map = map, zone = zone, x = x, y = y,
                           endsAt = now() + 120, title = "Проверка меток", sub = "/plgev clear — убрать" }
        E.Changed()
        say("Пробная метка поставлена на ваше место на 2 минуты: карта мира, миникарта и список.")
    elseif arg == "clear" then
        E.beacons = {}
        E.Changed()
        say("Метки убраны. Сервер пришлёт актуальные в течение двух минут.")
    elseif arg == "minimap" then
        PLGames_EventsDB.minimap = not PLGames_EventsDB.minimap
        E.Changed()
        say("Метки на миникарте: " .. (PLGames_EventsDB.minimap and "вкл" or "выкл"))
    else
        PLGames_EventsDB.list = not PLGames_EventsDB.list
        E.Changed()
        say("Список событий: " .. (PLGames_EventsDB.list and "вкл" or "выкл") ..
            ". Ещё: /plgev test, /plgev clear, /plgev minimap")
    end
end
