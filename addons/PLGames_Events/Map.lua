--[[ Метки на карте мира: кнопки поверх WorldMapButton. Видны на карте своей зоны и на карте
     континента. Подсказка — название, подпись, время; клик — стрелка TomTom (если стоит). ]]

local E = PLGamesEvents
local pins = {}         -- id -> кнопка (переиспользуются)
local SIZE = 22

local function makePin()
    local pin = CreateFrame("Button", nil, WorldMapButton)
    pin:SetWidth(SIZE)
    pin:SetHeight(SIZE)
    pin:SetFrameLevel(WorldMapButton:GetFrameLevel() + 6)
    pin.ring = pin:CreateTexture(nil, "BACKGROUND")
    pin.ring:SetAllPoints()
    pin.icon = pin:CreateTexture(nil, "ARTWORK")
    pin.icon:SetPoint("TOPLEFT", 2, -2)
    pin.icon:SetPoint("BOTTOMRIGHT", -2, 2)
    pin.icon:SetTexCoord(0.08, 0.92, 0.08, 0.92)
    pin:SetScript("OnEnter", function(self)
        local b = self.beacon
        if not b then return end
        WorldMapTooltip:SetOwner(self, "ANCHOR_RIGHT")
        WorldMapTooltip:AddLine(b.title, E.Color(b))
        if b.sub and b.sub ~= "" then WorldMapTooltip:AddLine(b.sub, 1, 1, 1, true) end
        local left = E.TimeLeft(b)
        if left then WorldMapTooltip:AddLine((b.kind == "soon" and "Появится через " or "Осталось ") .. left, 0.8, 0.8, 0.8) end
        if TomTom then WorldMapTooltip:AddLine("Клик — стрелка TomTom", 0.5, 0.8, 1) end
        WorldMapTooltip:Show()
    end)
    pin:SetScript("OnLeave", function() WorldMapTooltip:Hide() end)
    pin:SetScript("OnClick", function(self) if self.beacon then E.Waypoint(self.beacon) end end)
    return pin
end

function E.StylePin(pin, b)
    local r, g, bl = E.Color(b)
    pin.ring:SetTexture(r, g, bl, 0.95)
    pin.icon:SetTexture(E.ICONS[b.kind] or E.ICONS.event)
    pin.icon:SetDesaturated(b.kind == "soon")
    pin:SetAlpha(b.kind == "soon" and 0.75 or 1)
end

local function update()
    if not WorldMapFrame:IsShown() or E.indexing then return end
    local wma = GetCurrentMapAreaID()
    local w, h = WorldMapButton:GetWidth(), WorldMapButton:GetHeight()
    local seen = {}
    for id, b in pairs(E.beacons) do
        local nx, ny = E.PlaceOn(wma, b)
        if nx then
            local pin = pins[id] or makePin()
            pins[id] = pin
            pin.beacon = b
            E.StylePin(pin, b)
            pin:ClearAllPoints()
            pin:SetPoint("CENTER", WorldMapButton, "TOPLEFT", nx * w, -ny * h)
            pin:Show()
            seen[id] = true
        end
    end
    for id, pin in pairs(pins) do
        if not seen[id] then pin:Hide() end
    end
end

local frame = CreateFrame("Frame")
frame:RegisterEvent("WORLD_MAP_UPDATE")
frame:SetScript("OnEvent", update)
WorldMapFrame:HookScript("OnShow", update)
table.insert(E.listeners, update)
