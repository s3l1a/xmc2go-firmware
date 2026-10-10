@echo off
rem XMC 2Go updater CLI launcher - run from any directory.
rem Examples:
rem   "XMC 2Go CLI.bat" list
rem   "XMC 2Go CLI.bat" info
rem   "XMC 2Go CLI.bat" update dist\app_traffic_B.img
cd /d "%~dp0"
python "%~dp0host\cli\main.py" %*
