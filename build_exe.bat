@echo off
setlocal
py -m pip install --upgrade pyinstaller
if errorlevel 1 goto error
py -m PyInstaller --noconfirm --clean --onefile --windowed --name Lofi12XT_WAV_Batch_Prep lofi12xt_wav_batch_prep.py
if errorlevel 1 goto error
echo.
echo Build complete. Copy ffmpeg.exe into the dist folder beside the EXE.
pause
exit /b 0
:error
echo Build failed. Check the error above.
pause
exit /b 1
