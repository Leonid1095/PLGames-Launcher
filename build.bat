@echo off
echo === PLGames Launcher Build (Portable) ===
echo.

echo Installing requirements...
pip install -r requirements.txt

echo.
echo Building portable launcher...
pyinstaller --noconsole --name "PLGamesLauncher" ^
    --hidden-import "webview" ^
    --hidden-import "clr" ^
    --hidden-import "requests" ^
    --clean ^
    app.py

echo.
if exist "dist\PLGamesLauncher\PLGamesLauncher.exe" (
    echo === Build OK! ===
    echo.
    echo Portable folder: dist\PLGamesLauncher\
    echo Just copy folder into your WoW directory and run PLGamesLauncher.exe
) else (
    echo === Build FAILED ===
)
echo.
pause
