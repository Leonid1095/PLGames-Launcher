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

    echo Copying support files...
    if exist "aria2c.exe" copy /Y "aria2c.exe" "dist\aria2c.exe"
    if exist "WoW 3.3.5a.torrent" copy /Y "WoW 3.3.5a.torrent" "dist\WoW 3.3.5a.torrent"

    echo Creating portable ZIP...
    powershell -Command "Compress-Archive -Path 'dist\PLGamesLauncher.exe','dist\aria2c.exe','dist\WoW 3.3.5a.torrent' -DestinationPath 'dist\PLGamesLauncher_Portable.zip' -Force"

    echo Building installer...
    if exist "installer.nsi" (
        "C:\Program Files (x86)\NSIS\makensis.exe" installer.nsi
    )

    echo.
    echo Output:
    echo   dist\PLGamesLauncher_Setup.exe    - installer (all-in-one)
    echo   dist\PLGamesLauncher_Portable.zip - portable (unzip and run)
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
