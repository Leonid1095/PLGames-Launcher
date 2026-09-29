@echo off
echo === PLGames Launcher Build ===
echo.

echo Installing requirements...
pip install -r requirements.txt

echo.
echo Building launcher...
rem 7-Zip (7z.exe + 7z.dll) is optional: without it the launcher extracts the client with system tar.exe
set SEVENZIP=
if exist "7z.exe" if exist "7z.dll" set SEVENZIP=--add-data "7z.exe;." --add-data "7z.dll;." --add-data "7z-License.txt;."
pyinstaller --noconsole --onefile --name "PLGamesLauncher" ^
    --hidden-import "webview" ^
    --hidden-import "clr" ^
    --hidden-import "requests" ^
    --add-data "addons;addons" ^
    --add-data "content_default.json;." ^
    --add-data "aria2c.exe;." ^
    --add-data "PLGames_Wow3.3.5.torrent;." ^
    %SEVENZIP% ^
    --clean ^
    app.py

echo.
if exist "dist\PLGamesLauncher.exe" (
    echo === Build OK! ===
    echo.

    echo Copying support files...
    if exist "aria2c.exe" copy /Y "aria2c.exe" "dist\aria2c.exe"
    if exist "PLGames_Wow3.3.5.torrent" copy /Y "PLGames_Wow3.3.5.torrent" "dist\PLGames_Wow3.3.5.torrent"

    echo Creating portable ZIP...
    powershell -Command "Compress-Archive -Path 'dist\PLGamesLauncher.exe','dist\aria2c.exe','dist\PLGames_Wow3.3.5.torrent' -DestinationPath 'dist\PLGamesLauncher_Portable.zip' -Force"

    echo Building installer...
    if exist "installer.nsi" (
        "C:\Program Files (x86)\NSIS\makensis.exe" installer.nsi
    )

    echo.
    echo Output:
    echo   dist\PLGamesLauncher_Setup.exe    - installer (all-in-one)
    echo   dist\PLGamesLauncher_Portable.zip - portable (unzip and run)
    echo.
    echo To release: git tag v0.x.x and git push origin v0.x.x - CI publishes the release.
    echo NEVER attach Setup.exe or aria2c.exe to a GitHub release: the 0.3.4 updater
    echo replaces itself with the first .exe asset. aria2c and the torrent are inside the exe.
) else (
    echo === Build FAILED ===
)
echo.
pause
