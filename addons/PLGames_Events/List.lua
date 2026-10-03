--[[ Список активных событий на экране: рамка слева от миникарты, перетаскивается мышью.
     Клик по строке — карта мира на зоне события; Shift+клик — стрелка TomTom. /plgev — скрыть. ]]

local E = PLGamesEvents
local ROWS, WIDTH, ROW_H = 8, 236, 16

local box = CreateFrame("Frame", "PLGamesEventsList", UIParent)
box:SetWidth(WIDTH)
box:SetHeight(20)
box:SetPoint("TOPRIGHT", MinimapCluster, "TOPLEFT", -8, -18)
box:SetMovable(true)
box:EnableMouse(true)
box:RegisterForDrag("LeftButton")
box:SetClampedToScreen(true)
box:SetScript("OnDragStart", box.StartMoving)
box:SetScript("OnDragStop", function(self)
    self:StopMovingOrSizing()
    local point, _, rel, x, y = self:GetPoint()
    PLGames_EventsDB.pos = { point, rel, x, y }
end)
box:SetBackdrop({ bgFile = "Interface\\Tooltips\\UI-Tooltip-Background",
                  edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border", edgeSize = 12,
                  insets = { left = 3, right = 3, top = 3, bottom = 3 } })
box:SetBackdropColor(0, 0, 0, 0.55)
box:SetBackdropBorderColor(0.4, 0.4, 0.45, 0.8)
box:Hide()

local header = box:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
header:SetPoint("TOPLEFT", 8, -6)
header:SetText("События сервера")

local rows = {}
for i = 1, ROWS do
    local row = CreateFrame("Button", nil, box)
    row:SetHeight(ROW_H)
    row:SetPoint("TOPLEFT", 6, -6 - i * ROW_H)
    row:SetPoint("RIGHT", -6, 0)
    row.icon = row:CreateTexture(nil, "ARTWORK")
    row.icon:SetWidth(ROW_H - 2)
    row.icon:SetHeight(ROW_H - 2)
    row.icon:SetPoint("LEFT")
    row.icon:SetTexCoord(0.08, 0.92, 0.08, 0.92)
    row.time = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    row.time:SetPoint("RIGHT")
    row.text = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    row.text:SetPoint("LEFT", row.icon, "RIGHT", 4, 0)
    row.text:SetPoint("RIGHT", row.time, "LEFT", -4, 0)
    row.text:SetJustifyH("LEFT")
    row:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight", "ADD")
    row:SetScript("OnClick", function(self)
        if not self.beacon then return end
        if IsShiftKeyDown() then E.Waypoint(self.beacon) else E.ShowOnMap(self.beacon) end
    end)
    row:SetScript("OnEnter", function(self)
        local b = self.beacon
        if not b then return end
        GameTooltip:SetOwner(self, "ANCHOR_LEFT")
        GameTooltip:AddLine(b.title, E.Color(b))
        if b.sub and b.sub ~= "" then GameTooltip:AddLine(b.sub, 1, 1, 1, true) end
        GameTooltip:AddLine("Клик — показать на карте" .. (TomTom and ", Shift+клик — стрелка TomTom" or ""), 0.5, 0.8, 1)
        GameTooltip:Show()
    end)
    row:SetScript("OnLeave", function() GameTooltip:Hide() end)
    rows[i] = row
end

local function update()
    if not (PLGames_EventsDB and PLGames_EventsDB.list) then box:Hide() return end
    local list = E.Sorted()
    if #list == 0 then box:Hide() return end
    for i = 1, ROWS do
        local row, b = rows[i], list[i]
        if b then
            row.beacon = b
            row.icon:SetTexture(E.ICONS[b.kind] or E.ICONS.event)
            row.icon:SetDesaturated(b.kind == "soon")
            row.text:SetText(b.title)
            row.text:SetTextColor(E.Color(b))
            local left = E.TimeLeft(b)
            row.time:SetText(left and ((b.kind == "soon" and "через " or "") .. left) or "")
            row:Show()
        else
            row.beacon = nil
            row:Hide()
        end
    end
    box:SetHeight(12 + (math.min(#list, ROWS) + 1) * ROW_H)
    box:Show()
end

local elapsed = 0
box:SetScript("OnUpdate", function(_, dt)  -- таймеры в строках
    elapsed = elapsed + dt
    if elapsed >= 1 then elapsed = 0 update() end
end)

local watcher = CreateFrame("Frame")
watcher:RegisterEvent("PLAYER_LOGIN")
watcher:SetScript("OnEvent", function()
    local pos = PLGames_EventsDB and PLGames_EventsDB.pos
    if pos then
        box:ClearAllPoints()
        box:SetPoint(pos[1], UIParent, pos[2], pos[3], pos[4])
    end
    update()
end)
table.insert(E.listeners, update)
