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
    echo Output: dist\PLGamesLauncher.exe
    echo.
    echo To release:
    echo   1. git tag v2.x.x
    echo   2. git push origin v2.x.x
    echo   3. Upload dist\PLGamesLauncher.exe to GitHub Release
) else (
    echo === Build FAILED ===
)
echo.
pause
