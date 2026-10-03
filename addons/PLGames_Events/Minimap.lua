--[[ Метки на миникарте. Положение игрока — из GetPlayerMapPosition, пересчитанное в координаты
     мира по таблице зон; масштаб — по зуму миникарты; учитывается поворот миникарты. Дальние метки
     прижимаются к краю и показывают направление. Пока открыта карта мира, миникарта не
     обновляется: SetMapToCurrentZone сбил бы зону, которую смотрит игрок. ]]

local E = PLGamesEvents
local pins = {}
local SIZE = 14
-- диаметр миникарты в ярдах по уровню зума (стандартные значения клиента 3.3.5a)
local OUTDOOR = { [0] = 466 + 2 / 3, 400, 333 + 1 / 3, 266 + 2 / 3, 200, 133 + 1 / 3 }
local INDOOR = { [0] = 300, 240, 180, 120, 80, 50 }

-- Смещение метки от центра миникарты в пикселях. Чистая функция — проверяется тестами.
-- px, py, bx, by — координаты мира (x на север, y на запад); facing — поворот игрока (радианы,
-- против часовой от севера) или nil, если миникарта не вращается; radiusPx — радиус миникарты.
function E.MinimapOffset(px, py, bx, by, yardsAcross, radiusPx, facing, square)
    local scale = radiusPx / (yardsAcross / 2)
    local right, up = (py - by) * scale, (bx - px) * scale
    if facing then
        local c, s = math.cos(facing), math.sin(facing)
        right, up = right * c + up * s, -right * s + up * c
    end
    local edge = radiusPx - SIZE / 2
    local far
    if square then
        local m = math.max(math.abs(right), math.abs(up))
        far = m > edge
        if far then right, up = right * edge / m, up * edge / m end
    else
        local d = math.sqrt(right * right + up * up)
        far = d > edge
        if far then right, up = right * edge / d, up * edge / d end
    end
    return right, up, far
end

local function makePin()
    local pin = CreateFrame("Frame", nil, Minimap)
    pin:SetWidth(SIZE)
    pin:SetHeight(SIZE)
    pin:SetFrameLevel(Minimap:GetFrameLevel() + 5)
    pin.ring = pin:CreateTexture(nil, "BACKGROUND")
    pin.ring:SetAllPoints()
    pin.icon = pin:CreateTexture(nil, "ARTWORK")
    pin.icon:SetPoint("TOPLEFT", 1, -1)
    pin.icon:SetPoint("BOTTOMRIGHT", -1, 1)
    pin.icon:SetTexCoord(0.08, 0.92, 0.08, 0.92)
    pin:EnableMouse(true)
    pin:SetScript("OnEnter", function(self)
        local b = self.beacon
        if not b then return end
        GameTooltip:SetOwner(self, "ANCHOR_LEFT")
        GameTooltip:AddLine(b.title, E.Color(b))
        if b.sub and b.sub ~= "" then GameTooltip:AddLine(b.sub, 1, 1, 1, true) end
        local left = E.TimeLeft(b)
        if left then GameTooltip:AddLine((b.kind == "soon" and "Появится через " or "Осталось ") .. left, 0.8, 0.8, 0.8) end
        GameTooltip:Show()
    end)
    pin:SetScript("OnLeave", function() GameTooltip:Hide() end)
    return pin
end

local function hideAll()
    for _, pin in pairs(pins) do pin:Hide() end
end

local function update()
    if not (PLGames_EventsDB and PLGames_EventsDB.minimap) or (WorldMapFrame and WorldMapFrame:IsShown()) then
        if not (PLGames_EventsDB and PLGames_EventsDB.minimap) then hideAll() end
        return
    end
    local px, py, map = E.PlayerWorldPos()
    if not px then hideAll() return end
    local zoom = Minimap:GetZoom()
    local yards = ((IsIndoors and IsIndoors()) and INDOOR or OUTDOOR)[zoom] or OUTDOOR[0]
    local facing = GetCVar("rotateMinimap") == "1" and GetPlayerFacing() or nil
    local square = GetMinimapShape and GetMinimapShape() == "SQUARE"
    local radius = Minimap:GetWidth() / 2
    local seen = {}
    for id, b in pairs(E.beacons) do
        if b.map == map then
            local pin = pins[id] or makePin()
            pins[id] = pin
            pin.beacon = b
            E.StylePin(pin, b)
            local right, up, far = E.MinimapOffset(px, py, b.x, b.y, yards, radius, facing, square)
            pin:ClearAllPoints()
            pin:SetPoint("CENTER", Minimap, "CENTER", right, up)
            if far then pin:SetAlpha(0.6) end
            pin:Show()
            seen[id] = true
        end
    end
    for id, pin in pairs(pins) do
        if not seen[id] then pin:Hide() end
    end
end

local elapsed = 0
local frame = CreateFrame("Frame")
frame:SetScript("OnUpdate", function(_, dt)
    elapsed = elapsed + dt
    if elapsed >= 0.1 then
        elapsed = 0
        update()
    end
end)
frame:RegisterEvent("ZONE_CHANGED_NEW_AREA")
frame:SetScript("OnEvent", function()
    if not WorldMapFrame:IsShown() then SetMapToCurrentZone() end
end)
-- Игрок закрыл карту мира, возможно на чужой зоне: возвращаем текущую, иначе позиция игрока — 0,0
WorldMapFrame:HookScript("OnHide", function() SetMapToCurrentZone() end)
table.insert(E.listeners, update)
