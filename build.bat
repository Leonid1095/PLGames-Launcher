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
    --add-data "aria2c.exe;." ^
    --add-data "WoW 3.3.5a.torrent;." ^
    --clean ^
    app.py

echo.
if exist "dist\PLGamesLauncher.exe" (
    echo === Build OK! ===
    echo.

    echo Creating portable ZIP...
    powershell -Command "Compress-Archive -Path 'dist\PLGamesLauncher.exe' -DestinationPath 'dist\PLGamesLauncher_Portable.zip' -Force"

    echo Building installer...
    if exist "installer.nsi" (
        "C:\Program Files (x86)\NSIS\makensis.exe" installer.nsi
    )

    echo.
    echo Output:
    echo   dist\PLGamesLauncher.exe          - standalone
    echo   dist\PLGamesLauncher_Portable.zip - portable
    echo   dist\PLGamesLauncher_Setup.exe    - installer
    echo.
    echo To release:
    echo   1. git tag v0.x.x
    echo   2. git push origin v0.x.x
    echo   3. Upload Setup + Portable ZIP to GitHub Release
) else (
    echo === Build FAILED ===
)
echo.
pause
