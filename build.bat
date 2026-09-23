@echo off
cd /d "%~dp0"
rem The version comes from version_info.txt, so it is only ever set in one place.
for /f "usebackq delims=" %%v in (`py -c "import re; print(re.search(r'ProductVersion.{4}([0-9.]+)', open('version_info.txt').read()).group(1))"`) do set VERSION=%%v
if not defined VERSION goto :failed
py -m pip install --upgrade pyinstaller || goto :failed
py -m PyInstaller --noconfirm --onefile --windowed --name EQTriage --icon triage.ico --version-file version_info.txt --distpath dist\EQTriage triage.py || goto :failed
rem Package only the exe: running it from dist leaves personal position/pins/settings files that must not ship.
powershell -NoProfile -Command "$stage = Join-Path $env:TEMP 'EQTriage-package'; Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue; New-Item -ItemType Directory (Join-Path $stage 'EQTriage') | Out-Null; Copy-Item 'dist\EQTriage\EQTriage.exe' (Join-Path $stage 'EQTriage'); Compress-Archive -Path (Join-Path $stage 'EQTriage') -DestinationPath 'dist\EQTriage-v%VERSION%.zip' -Force" || goto :failed
echo.
echo Built %~dp0dist\EQTriage\ and %~dp0dist\EQTriage-v%VERSION%.zip
echo Attach the zip to the GitHub release for v%VERSION%.
pause
exit /b 0
:failed
echo.
echo Build failed, see the messages above.
pause
exit /b 1
