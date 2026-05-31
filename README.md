# ⚔ PLGames Launcher

<p align="center">
  <img src="https://img.shields.io/badge/version-0.3.3-blue?style=flat-square" alt="Version">
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
| **HD Patch Manager** | Управление HD-патчами (MPQ) прямо из лаунчера |
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
├── app.py              # Всё приложение: pywebview-бэкенд + inline HTML/CSS/JS
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

### Сборка .exe
```bash
build.bat
```
Результат: `dist/PLGamesLauncher/PLGamesLauncher.exe`

## Автообновление

Лаунчер проверяет GitHub Releases при запуске:
1. Сравнивает `LAUNCHER_VERSION` с последним тегом
2. Если есть новая версия — показывает диалог
3. Скачивает `.exe` и перезапускает

Для релиза:
```bash
git tag v0.3.0
git push origin v0.3.0
# Загрузить .exe в GitHub Release
```

## Текущие проекты

| Проект | Тип | Статус |
|--------|-----|--------|
| Realm Chronos | WoW 3.3.5a Private Server | Active |

---

<p align="center">
  <b>PLGames</b> — игровая платформа<br>
  <sub>Built with pywebview · Powered by Telegram SSO</sub>
</p>
