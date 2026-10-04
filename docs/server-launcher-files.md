# Файлы лаунчера на сервере (/launcher/)

С этого адреса лаунчер 0.5.1+ берёт:
- **контент изданий** — `https://plgames-wow.ru/launcher/content/`. Сейчас там 404, и лаунчер качает с GitHub;
- **архив клиента** — `https://plgames-wow.ru/launcher/client/PLGames_Wow3.3.5.rar`. Нужен для двух вещей:
  web seed в торренте (клиент качается, даже когда никто не раздаёт) и починка отдельных файлов кусками (Range).

Пока на сервере ничего нет, всё работает по-старому: контент с GitHub, клиент — только у раздающих.

Выполняется на сервере под пользователем `plgames`. Пункт 4 — под `sudo`.

## 1. Папки

```bash
mkdir -p /home/plgames/launcher-files/client /home/plgames/launcher-files/content
chmod o+x /home/plgames                # nginx (www-data) должен дойти до папки
chmod -R o+rX /home/plgames/launcher-files
```

## 2. Архив клиента (≈ 19,6 ГБ)

Сервер качает его сам, по тому же торренту. Раздаёт ПК владельца, поэтому qBittorrent на нём должен быть включён.

```bash
sudo apt-get install -y aria2
cd /home/plgames/launcher-files/client
curl -LO https://github.com/Leonid1095/PLGames-Launcher/raw/main/PLGames_Wow3.3.5.torrent
aria2c --seed-time=0 --file-allocation=none PLGames_Wow3.3.5.torrent
ls -l PLGames_Wow3.3.5.rar             # размер должен быть ровно 21069765019 байт
rm PLGames_Wow3.3.5.torrent
```

Пока nginx не настроен, aria2c сообщит, что не смог взять файл с собственного адреса (web seed в торренте).
Это не ошибка: файл придёт от раздающих.

## 3. Контент изданий

Сначала владелец загружает контент в пререлиз `content-latest` на GitHub. Потом сервер забирает всё оттуда:

```bash
curl -LO https://github.com/Leonid1095/PLGames-Launcher/raw/main/tools/mirror_content.py
python3 -m pip install --user requests   # если ещё нет
python3 mirror_content.py /home/plgames/launcher-files/content
```

Скрипт кладёт файлы по путям `<компонент>/<версия>/<файл>` и сверяет SHA-256. То, что уже совпадает,
он не качает. Манифесты подменяет последними, поэтому лаунчер не увидит ссылок на недокачанные файлы.
После каждого нового контента на GitHub — тот же запуск.

## 4. nginx

В `/etc/nginx/sites-available/plgames-wow.ru`, в блок `server` с `listen 443`, выше `location /`:

```nginx
    # Файлы лаунчера: архив клиента (Range — для починки и web seed) и контент изданий.
    # no-cache = «перепроверяй»: манифесты всегда свежие, большие файлы получают 304 и не качаются заново.
    location /launcher/ {
        alias /home/plgames/launcher-files/;
        autoindex off;
        add_header Cache-Control "no-cache";
    }
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

## 5. Проверка

```bash
curl -sI https://plgames-wow.ru/launcher/client/PLGames_Wow3.3.5.rar | grep -iE "^(HTTP|content-length|accept-ranges)"
# HTTP/2 200, content-length: 21069765019, accept-ranges: bytes
curl -s -r 0-7 https://plgames-wow.ru/launcher/client/PLGames_Wow3.3.5.rar | xxd | head -1
# 5261 7221 1a07 0100 → «Rar!» — Range работает
curl -s https://plgames-wow.ru/launcher/content/manifest2.json | head -c 200
curl -s https://plgames-wow.ru/launcher/content/client-index.json | head -c 120
```

## Новая раздача клиента

Новый архив — новые смещения файлов. На ПК владельца:
1. `python tools/build_client_index.py --rar <новый архив>`;
2. сборка контента и выкладка на GitHub;
3. новый `.torrent` с web seed: `python tools/torrent_webseed.py <torrent> https://plgames-wow.ru/launcher/client/<имя>.rar`;
4. на сервере — пункты 2 и 3 заново.
