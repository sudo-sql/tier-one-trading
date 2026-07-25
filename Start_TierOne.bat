@echo off
title TierOne Trading
cd /d C:\Users\tjcas\Desktop\TierOneTrading
:loop
python main.py
echo.
echo App stopped or crashed - restarting in 15 seconds (Ctrl+C to quit)...
timeout /t 15 >nul
goto loop
