--[[ ============================================================
  PLGames Live City — реплики NPC пузырём над головой, без спама в чат.

  КАК ЭТО РАБОТАЕТ:
   • Сервер шлёт реплику NPC обычным MONSTER_SAY (пузырь + строка в чате).
   • Строку в чат-ОКНЕ рисует FrameXML (ChatFrame) — её мы и режем фильтром.
   • Пузырь над головой рисует игровой ДВИЖОК (WorldFrame) отдельно — фильтр
     его НЕ трогает → пузырь остаётся.
   • MONSTER_YELL НЕ режем (там механики боссов!). Режем только ambient SAY/EMOTE.

  Игрок может вернуть реплики в чат: /livecity chat
============================================================ ]]

local FILTER_EVENTS = { "CHAT_MSG_MONSTER_SAY", "CHAT_MSG_MONSTER_EMOTE" }

-- Фильтр: вернуть true → строка НЕ печатается в чат-окно (пузырь не затрагивается).
local function suppress(self, event, ...)
    if PLGames_LiveCityDB and PLGames_LiveCityDB.chat then
        return false  -- игрок попросил вернуть реплики в чат
    end
    return true
end

local f = CreateFrame("Frame")
f:RegisterEvent("PLAYER_LOGIN")
f:SetScript("OnEvent", function()
    PLGames_LiveCityDB = PLGames_LiveCityDB or { chat = false }

    -- Пузыри над NPC должны быть включены, иначе речь не видно нигде.
    SetCVar("chatBubbles", "1")
    SetCVar("chatBubblesParty", "1")

    for _, ev in ipairs(FILTER_EVENTS) do
        ChatFrame_AddMessageEventFilter(ev, suppress)
    end

    DEFAULT_CHAT_FRAME:AddMessage("|cff5fb4ff[Live City]|r реплики NPC — пузырём над головой. Вернуть в чат: |cffffd100/livecity chat|r")
end)

-- /livecity [chat|bubbles] — переключатель
SLASH_PLGLIVECITY1 = "/livecity"
SlashCmdList["PLGLIVECITY"] = function(msg)
    msg = (msg or ""):lower():gsub("%s+", "")
    if msg == "chat" then
        PLGames_LiveCityDB.chat = true
        DEFAULT_CHAT_FRAME:AddMessage("|cff5fb4ff[Live City]|r реплики NPC снова в чате.")
    elseif msg == "bubbles" or msg == "" then
        PLGames_LiveCityDB.chat = false
        SetCVar("chatBubbles", "1")
        DEFAULT_CHAT_FRAME:AddMessage("|cff5fb4ff[Live City]|r реплики NPC — только пузырём (чат чист).")
    else
        DEFAULT_CHAT_FRAME:AddMessage("|cff5fb4ff[Live City]|r /livecity bubbles — пузыри (по умолчанию) | /livecity chat — вернуть в чат")
    end
end
