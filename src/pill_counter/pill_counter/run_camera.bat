@echo off
REM Chay chuong trinh dem thuoc bang camera
cd /d "%~dp0"
C:\pillsenv\Scripts\python.exe camera_count.py --popup
pause
