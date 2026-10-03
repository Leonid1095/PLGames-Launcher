# ⚔ PLGames Launcher

<p align="center">
  <img src="https://img.shields.io/badge/version-0.5.0-blue?style=flat-square" alt="Version">
  <img src="https://img.shields.io/badge/python-3.10+-yellow?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/platform-Windows-lightgrey?style=flat-square&logo=windows" alt="Platform">
  <img src="https://img.shields.io/badge/license-Proprietary-red?style=flat-square" alt="License">
</p>

<p align="center">
  <b>Универсальный игровой лаунчер в стиле Battle.net</b><br>
  <sub>Мультипроект · Telegram SSO · Автообновление · HD патчи</sub>
</p>

---

## Возможности

| Функция | Описание |
|---------|----------|
| **Мультипроект** | Управление несколькими серверами/играми из одного лаунчера |
| **Серверный манифест** | Проекты, новости и баннеры загружаются с сервера автоматически |
| **Telegram SSO** | Авторизация через Telegram бота — без паролей |
| **Автообновление** | Лаунчер обновляется сам через GitHub Releases |
| **Установка клиента** | Торрент → автоматическая распаковка архива клиента (7-Zip или системный tar) |
| **Графические издания** | Классика / Ремастер / Forever / «Своё» — в духе WoW: Forever, по манифесту компонентов |
| **Настройки графики** | Редактор WTF/Config.wtf без запуска игры |
| **Статус сервера** | Онлайн/оффлайн + количество игроков в реальном времени |
| **Auto-realmlist** | Автоматическая запись realmlist при авторизации |

## Скриншот

<p align="center">
  <i>Battle.net-style UI с hero-слайдером, карточками новостей и боковой панелью</i>
</p>

## Архитектура

```
PLGames Launcher
├── app.py              # pywebview-бэкенд (Api) + inline HTML/CSS/JS
├── gameutils.py        # Папка клиента: безопасные пути, Config.wtf, MPQ, запущена ли игра
├── client_install.py   # Распаковка архива клиента после торрента
├── content.py          # Издания: манифест, state.json, планировщик, исполнитель с откатом
├── editions.py         # Фасад изданий для UI (фоновое применение, прогресс)
├── hardware.py         # Видеокарта → рекомендуемое издание
├── content_default.json      # Встроенный манифест изданий (без сети)
├── content/manifest.src.json # Исходник манифеста для публикации
├── tools/build_content_manifest.py  # Сборка манифеста + файлов для сервера и GitHub
├── tests/              # python -m unittest discover -s tests -t . -v
├── build.bat           # Сборка .exe (PyInstaller)
├── installer.nsi       # NSIS-инсталлятор
├── requirements.txt    # Python-зависимости
├── aria2c.exe          # Загрузчик торрентов (сторонний бинарь)
└── .github/workflows/  # CI: сборка и публикация релиза по тегу v*
```

## Как работает

```
┌─────────────┐     GET /api/launcher/manifest     ┌──────────────┐
│  Лаунчер    │ ◄──────────────────────────────────►│   Сервер     │
│  (клиент)   │     POST /api/auth/sso/start       │   (API)      │
│             │ ◄──────────────────────────────────►│              │
│  pywebview  │     GET /api/status                │  Express/    │
│  + HTML/JS  │ ◄──────────────────────────────────►│  Nginx       │
└─────────────┘                                     └──────────────┘
       │
       │  GitHub Releases API
       ▼
┌─────────────┐
│  GitHub     │  Проверка новых версий
│  Releases   │  Скачивание .exe
└─────────────┘
```

## Серверный манифест

Лаунчер при запуске загружает `GET /api/launcher/manifest`:

```json
{
  "projects": [
    {
      "id": "wow_chronos",
      "name": "Chronos",
      "full_name": "Realm Chronos",
      "subtitle": "WotLK 3.3.5a",
      "status_url": "https://server.com/api/status",
      "banners": [
        {"image": "https://...", "title": "Phase 2!"}
      ],
      "news": [
        {"tag": "Анонс", "title": "...", "text": "...", "date": "2026-03-07"}
      ]
    }
  ]
}
```

Добавил проект в JSON на сервере — он автоматически появился в лаунчере у всех пользователей.

## Установка клиента

1. «Установить» → торрент `PLGames_Wow3.3.5.torrent` (aria2c) скачивает `PLGames_Wow3.3.5.rar`.
2. После докачки лаунчер сам распаковывает архив вшитым 7-Zip 26.03 (`7z.exe` + `7z.dll`, лицензия —
   `7z-License.txt`); без них — системным `tar.exe` (Windows 11 читает RAR5). Распаковка идёт во временную
   папку и переносится на место только целиком; перед стартом проверяется свободное место. Процесс
   распаковщика привязан к лаунчеру (Job Object): закрыли/упал лаунчер — распаковка останавливается.
3. Путь к игре переключается на распакованную папку, лаунчер предлагает удалить архив
   (оставьте его для раздачи) и открывает вкладку «Издания».

Если архив уже скачан вручную — «Уже скачали архив клиента? Распаковать…» в панели «Путь к игре».

## Графические издания

Вкладка **«ИЗДАНИЯ»** (только WoW): Классика / Ремастер / **Forever** + таблица сравнения, бейдж
«Рекомендуем для вашего ПК» по видеокарте, на карточке — сколько придётся скачать. Режим **«Своё»** —
переключатели компонентов в «Настройках». Вкладка **«АДДОНЫ»** — каталог аддонов 3.3.5a, свои аддоны
игрока и встроенные аддоны сервера (см. ниже).

У компонента может быть требование к ПК (`"requires": "vulkan13"`) и замена (`"fallback"`): если
ПК требованию не отвечает, издание ставит замену и всё равно считается этим изданием. Vulkan лаунчер
спрашивает у драйвера сам (`hardware.vulkan_version`: `vkCreateInstance` → `apiVersion` видеокарт).
Так Forever на ПК без Vulkan 1.3 ставит фильтры ReShade вместо Northlight — отдельная «Ультра» не нужна.

Издание = набор компонентов из манифеста:

| Тип | Что делает | Выключение |
|-----|-----------|------------|
| `mpq` | включает MPQ, уже лежащие в клиенте | переименование в `*.disabled` |
| `files` | скачивает файлы (размер + SHA-256, перебор зеркал) и кладёт в папку игры | удаляет; чужой файл на том же месте возвращается из `PLGames/backup/` |
| `config` | пишет значения в `WTF/Config.wtf` | возвращает прежние значения |
| `zip` | архив с папками аддонов → `Interface/AddOns`; исполняемое и выход за папку — отказ; чужая папка с тем же именем → `PLGames/backup/kept/` | папки удаляются |
| `installer` | пакет со своим установщиком (Northlight): распаковка в `%LOCALAPPDATA%\PLGamesLauncher\installers\`, запуск `install` с `{client}`/`{locale}`, прогресс — из его вывода | его `uninstall` |

У компонента есть область `scope`: `edition` (входит в издания) или `addon` (каталог аддонов). Смена
издания аддоны не трогает, а аддоны не превращают издание в «Своё». Аддоны с `"default": true`
ставятся при первом выборе издания, дальше игрок решает сам.

Манифест ищется так: `https://plgames-wow.ru/launcher/content/manifest2.json` → GitHub Release
`content-latest` → кэш `%APPDATA%\PLGamesLauncher\content-manifest2.json` → встроенный `content_default.json`.
`manifest2.json` — схема 2 (типы `zip`/`installer`, области); `manifest.json` (схема 1) остаётся для
лаунчеров 0.4.x, которые новых типов не знают, — не удалять.

Применение атомарно: сначала все загрузки (клиент не трогается), затем изменения по журналу; при ошибке
всё откатывается. Загрузки лежат в `<игра>\PLGames\downloads\` до установки: обрыв докачивается с места
(`Range`), отмена или ошибка не заставляют качать заново; файл, который уже лежит в клиенте байт-в-байт,
не скачивается вовсе. Пока запущен `wow.exe` из этой папки — применение запрещено.
Состояние клиента: `<игра>\PLGames\state.json` (удалите папку `PLGames`, чтобы лаунчер «забыл» выбор).

`wow.exe` не патчится никогда — на сервере Warden с проверками памяти.

### Контент в `content/manifest.src.json`

| Компонент | Что внутри | Где |
|-----------|-----------|-----|
| HD-паки (8 шт.) | MPQ, уже лежащие в клиенте | Ремастер, Forever |
| `gfx_high` / `gfx_ultra` | Config.wtf: дальность, трава, эффекты; в `gfx_ultra` ещё детализация окружения, частицы, погода, мипы текстур и земли, облака | Ремастер / Forever |
| `reshade` | ReShade 6.8.0 **с поддержкой дополнений** (d3d9.dll), Glamarye Fast Effects (MIT): затенение (AO), имитация отражённого света, FXAA, резкость; OtisFX AdaptiveFog (MIT): туман по глубине; пресет `PLGames_Ultra.ini` | Forever без Vulkan 1.3 (замена Northlight), «Своё» |
| `dxvk` | DXVK 3.1.1 (32-бит d3d9.dll → Vulkan), `dxvk.conf` (анизотропия 16x) | только «Своё» (нужен Vulkan 1.3) |

`reshade` и `dxvk` взаимоисключающие (оба — `d3d9.dll`). Файлы с `"mutable": true` (ReShade.ini,
пресет, dxvk.conf) программа переписывает сама — их правки не считаются «устареванием».
Обычная (подписанная) сборка ReShade при сетевом трафике отключает дополнения и буфер глубины
(`source/runtime.cpp`, `#if RESHADE_ADDON == 1`), поэтому AO и туман в онлайне без глубины не работают.
Мы ставим официальную сборку «with full add-on support» (reshade.me, не подписана): в ней этой проверки нет.
Глубину берёт встроенный Generic Depth (буфер 2560x1440 INTZ, проверено на клиенте 3.3.5a):
- `DepthCopyBeforeClears=0` — обязательно. WoW 3.3.5a не очищает этот буфер так, как ждёт
  дополнение («No clear operations were found»), и с копированием перед очисткой глубина пустая;
- `RESHADE_DEPTH_INPUT_IS_REVERSED=0` — D3D9, прямая глубина. Всё уже в `ReShade.ini`;
- у Glamarye выключен `depth_detect`: без глубины он иначе отключается целиком, а так
  сглаживание, резкость и мягкий свет работают всегда, затенение — когда есть глубина.

MSAA в игре должно быть выключено: с ним глубина недоступна (сглаживание даёт FXAA из Glamarye).
Проверка: Home → Glamarye → Debug mode → «show depth buffer» — сцена в градиенте, ближнее тёмное;
Home → «Дополнения» → Generic Depth показывает выбранный буфер.

### Издание «Forever»

| Компонент | Что внутри |
|-----------|-----------|
| `forever_dungeons` | Data/patch-A, B — текстуры подземелий и зданий (Project Reforged B) |
| `forever_world` | Data/patch-C, D — современные деревья, растения, здания (Reforged D **без** тайлов рельефа `.adt`: рельеф обязан совпадать с картами сервера) |
| `forever_terrain` | Data/patch-F, G — текстуры земли, воды, модели неба (Reforged E, без аддона внутри MPQ) |
| `forever_spells` | Data/patch-I — эффекты заклинаний (Reforged P); Data/ruRU/patch-ruRU-Y — `SpellVisualKitModelAttach.dbc`, сведённая с нашим HD-паком персонажей |
| `forever_sky` | Data/ruRU/Patch-ruRU-X — HD-небо и освещение зон (Sectym) |
| `northlight` | Northlight 0.3.183 (MIT): тени от солнца и персонажей, отражённый свет, объёмный туман; ставится последним — его кэш света строится по итоговому набору MPQ. Наш пакет = их архив + правка `app/mpq.py` (MPQ без `(listfile)` считаются пустыми — иначе падает на наших HD-паках). Ставится с `--no-art-layer`: их слой освещения конфликтует с небом Sectym |

Паки собираются `tools/build_forever_packs.py` (StormLib из `tools/bin`, MIT) из скачанных Reforged и неба,
части ≤1,8 ГБ (лимит файла GitHub — 2 ГиБ). Northlight несовместим с ReShade на видеокартах NVIDIA
(компоненты взаимоисключающие; ReShade — замена Northlight без Vulkan 1.3). Горячие клавиши в игре: Ctrl+Shift+F10 — все эффекты,
F9 — тени, F8 — отражённый свет, F7 — туман.

### Аддоны

Каталог — `content/addons.catalog.json` (20 аддонов 3.3.5a, источники закреплены коммитом/релизом и
SHA-256); `tools/build_addon_packs.py --raw <папка с исходными zip>` собирает нормализованные архивы
(в корне — папки аддонов, только файлы аддонов) и вписывает компоненты в `manifest.src.json`. По умолчанию:
Questie и DBM. Если папка аддона из каталога уже лежит в игре, а ставил её не лаунчер, — пометка
«стоит ваша версия» (`foreign`); включение ставит нашу, вашу кладёт в `PLGames/backup/kept/`.

**Установлены вами** (`useraddons.py`): остальные папки `Interface/AddOns` (кроме каталога, серверных и
`Blizzard_*`) группами — модули по `## Dependencies` входят в аддон, от которого зависят. Проверка: нет
`<Папка>/<Папка>.toc` — «игра не загрузит»; `## Interface` не 3.x — «другая версия игры». Выключение
переносит всю группу в `<игра>/PLGames/addons-off/`, включение возвращает; настройки (WTF) не трогаются.

**Аддоны сервера** — папки `addons/` в поставке; лаунчер кладёт их в игру при каждом запуске, выключить нельзя:
- PLGames Live City — реплики жителей пузырём над головой, а не в чате;
- PLGames Events — метки событий сервера на карте мира, миникарте и в списке (боссы, события зон, караваны,
  цепочки, стройки). Серверная часть — `data/lua/scripts/62_plg_event_beacons.lua` в репозитории WOW.
  Протокол и устройство: `docs/superpowers/specs/2026-10-03-event-beacons-design.md`. Таблица зон
  `MapAreas.lua` — из `WorldMapArea.dbc` клиента: `python tools/build_map_areas.py --client <игра>`.
  В игре: `/plgev` (список), `/plgev test` (пробная метка), `/plgev minimap`, `/plgev clear`.

### Проверка до публикации и публикация

```bash
# 1. Описать компоненты в content/manifest.src.json (у files-компонентов — "src": путь к файлу)
# 2. Собрать
python tools/build_content_manifest.py
# 3. Проверить в игре без сервера (игра закрыта; вернуть как было — та же команда с другим изданием)
python tools/try_content.py "D:\Games\PLGames_Wow3.3.5" forever
python tools/try_content.py "D:\Games\PLGames_Wow3.3.5" --addons addon_questie,addon_dbm
# 4. dist-content/server/* → на сервер в /launcher/content/ (nginx, статика)
#    dist-content/github/* → ассеты пререлиза «content-latest» (заменить все файлы):
gh release upload content-latest dist-content/github/* --clobber
#    Пока сервер не отдаёт /launcher/content/, лаунчер берёт манифест и файлы с GitHub.
```

Сборщик проверяет результат тем же `parse_manifest`, что и лаунчер: https-ссылки, безопасные пути,
разрешённые расширения, конфликты общих файлов.

## Сборка

### Требования
- Python 3.10+
- Windows 10/11

### Установка зависимостей
```bash
pip install -r requirements.txt
```

### Запуск из исходников
```bash
python app.py
```

### Тесты
```bash
python -m unittest discover -s tests -t . -v
```
Lua-тесты (`tests/test_event_beacons.py`: серверный скрипт меток и аддон в Lua 5.1) нужен пакет
`lupa` (`pip install lupa`); без него они пропускаются.

### Сборка .exe
```bash
build.bat
```
Результат: `dist/PLGamesLauncher/PLGamesLauncher.exe`

## Автообновление

Лаунчер проверяет GitHub Releases при запуске:
1. Сравнивает `LAUNCHER_VERSION` с последним тегом (`/releases/latest` — пререлизы не видны)
2. Если есть новая версия — показывает диалог
3. Скачивает `PLGamesLauncher.exe`, подменяет им себя и перезапускается

Для релиза:
```bash
git tag v0.4.0
git push origin v0.4.0   # CI: тесты → сборка → релиз с PLGamesLauncher.exe и торрентом
```

⚠️ В релизе лаунчера должен быть ровно один `.exe` — сам лаунчер. Версии до 0.4.0 берут первый
`.exe` из ассетов (или файл со словом `setup`) и подменяют им себя: `aria2c.exe` или установщик
в релизе сломают лаунчер у игроков. `aria2c.exe` и `PLGames_Wow3.3.5.torrent` вшиты в exe
(файл рядом с лаунчером важнее вшитого). Контент изданий живёт в отдельном **пререлизе**
`content-latest`, чтобы не стать «последним» релизом.

## Текущие проекты

| Проект | Тип | Статус |
|--------|-----|--------|
| Realm Chronos | WoW 3.3.5a Private Server | Active |

---

<p align="center">
  <b>PLGames</b> — игровая платформа<br>
  <sub>Built with pywebview · Powered by Telegram SSO</sub>
</p>
