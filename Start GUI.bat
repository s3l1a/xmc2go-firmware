@echo off
rem XMC 2Go updater GUI launcher - double-click or run from any directory.
cd /d "%~dp0"
start "XMC 2Go updater" python "%~dp0host\gui\gui.py"
