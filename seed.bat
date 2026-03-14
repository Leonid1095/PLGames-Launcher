@echo off
REM ============================================
REM PLGames Seeder — раздача WoW 3.3.5a через aria2c
REM Запустить в папке где лежит скачанный клиент
REM ============================================

set TORRENT=%~dp0WoW 3.3.5a.torrent
set ARIA2C=%~dp0aria2c.exe
set DATA_DIR=%~dp0..

REM Путь к папке где лежит "WoW 3.3.5a" (папка с клиентом)
REM По умолчанию: на уровень выше от launcher/
REM Можно указать свой путь как первый аргумент: seed.bat "D:\Games"
if not "%~1"=="" set DATA_DIR=%~1

echo ============================================
echo  PLGames Seeder
echo  Торрент: %TORRENT%
echo  Папка данных: %DATA_DIR%
echo ============================================
echo.

if not exist "%ARIA2C%" (
    echo ОШИБКА: aria2c.exe не найден: %ARIA2C%
    pause
    exit /b 1
)

if not exist "%TORRENT%" (
    echo ОШИБКА: Торрент файл не найден: %TORRENT%
    pause
    exit /b 1
)

echo Запуск раздачи... (Ctrl+C для остановки)
echo.

"%ARIA2C%" ^
    --dir="%DATA_DIR%" ^
    --seed-ratio=0.0 ^
    --bt-seed-unverified=true ^
    --check-certificate=false ^
    --console-log-level=notice ^
    --summary-interval=10 ^
    --bt-enable-lpd=true ^
    --enable-dht=true ^
    --enable-peer-exchange=true ^
    --bt-tracker=udp://tracker.opentrackr.org:1337/announce,udp://open.stealth.si:80/announce,udp://tracker.torrent.eu.org:451/announce,udp://exodus.desync.com:6969/announce,udp://open.demonii.com:1337/announce ^
    --listen-port=6881-6999 ^
    --dht-listen-port=6881-6999 ^
    --max-upload-limit=0 ^
    --bt-max-peers=100 ^
    --check-integrity=true ^
    --file-allocation=none ^
    --log="%DATA_DIR%\aria2c_seed_log.txt" ^
    --log-level=info ^
    "%TORRENT%"

echo.
echo Раздача остановлена.
pause
