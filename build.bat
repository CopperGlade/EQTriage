@echo off
cd /d "%~dp0"
py -m pip install --upgrade pyinstaller || goto :failed
py -m PyInstaller --noconfirm --onefile --windowed --name EQTriage --icon triage.ico --version-file version_info.txt --distpath dist\EQTriage triage.py || goto :failed
echo.
echo Built %~dp0dist\EQTriage\
echo Copy that EQTriage folder into your EverQuest folder, e.g. C:\QUARM\EQTriage\
pause
exit /b 0
:failed
echo.
echo Build failed, see the messages above.
pause
exit /b 1
