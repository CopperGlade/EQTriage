@echo off
cd /d "%~dp0"
rem The version comes from version_info.txt, so it is only ever set in one place.
for /f "usebackq delims=" %%v in (`py -c "import re; print(re.search(r'ProductVersion.{4}([0-9.]+)', open('version_info.txt').read()).group(1))"`) do set VERSION=%%v
if not defined VERSION goto :failed
rem Only Qt Core, Gui and Widgets are used. The full pyside6 package installs the add-on modules into the same
rem folder, where PyInstaller would bundle them, so they are removed and only the essentials kept.
py -m pip uninstall -y pyside6 pyside6-addons
py -m pip install --upgrade pyside6-essentials pyinstaller || goto :failed
py -m PyInstaller --noconfirm --onefile --windowed --name EQTriage --icon triage.ico --version-file version_info.txt --add-data "version_info.txt;." --exclude-module PySide6.QtNetwork --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick --exclude-module PySide6.QtOpenGL --exclude-module PySide6.QtOpenGLWidgets --exclude-module PySide6.QtSvg --exclude-module PySide6.QtPrintSupport --exclude-module PySide6.QtXml --exclude-module PySide6.QtConcurrent --exclude-module PySide6.QtSql --exclude-module PySide6.QtTest --exclude-module PySide6.QtUiTools --exclude-module PySide6.QtDesigner --exclude-module PySide6.QtHelp --distpath dist\EQTriage triage.py || goto :failed
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
