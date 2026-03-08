@echo off
echo === PLGames Launcher Build ===
echo.

echo Installing requirements...
pip install -r requirements.txt

echo.
echo Building launcher...
pyinstaller --noconsole --onefile --name "PLGamesLauncher" ^
    --hidden-import "webview" ^
    --hidden-import "clr" ^
    --hidden-import "requests" ^
    --clean ^
    app.py

echo.
if exist "dist\PLGamesLauncher.exe" (
    echo === Build OK! ===
    echo.
    echo Copying aria2c.exe and torrent files...
    if exist "aria2c.exe" copy /Y "aria2c.exe" "dist\aria2c.exe"
    if exist "WoW 3.3.5a.torrent" copy /Y "WoW 3.3.5a.torrent" "dist\WoW 3.3.5a.torrent"
    echo.
    echo Output: dist\PLGamesLauncher.exe
    echo         dist\aria2c.exe
    echo         dist\WoW 3.3.5a.torrent
    echo.
    echo To release:
    echo   1. git tag v0.x.x
    echo   2. git push origin v0.x.x
    echo   3. Upload dist\ folder contents to GitHub Release
) else (
    echo === Build FAILED ===
)
echo.
pause
