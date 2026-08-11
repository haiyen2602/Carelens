@echo off
REM Chay he thong dem thuoc bang VLM tu webcam.
cd /d "%~dp0"
python camera_counter.py %*
pause
