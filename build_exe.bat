@echo off
REM ============================================================
REM  Builds TierOneTrading.exe (one file, console app)
REM  Run this from the TierOneTrading folder on Windows.
REM ============================================================
echo Installing build tools...
pip install pyinstaller pyyaml requests pandas yfinance flask

echo Building executable...
pyinstaller --onefile --name TierOneTrading ^
  --hidden-import yfinance --hidden-import pandas ^
  --collect-data yfinance ^
  main.py

echo.
echo ============================================================
echo  Done! Your exe is at:  dist\TierOneTrading.exe
echo.
echo  IMPORTANT: config.yaml must sit NEXT TO the exe.
echo  To share: zip dist\TierOneTrading.exe + a blank config.yaml
echo  (never share a config.yaml containing your tokens/passwords)
echo ============================================================
pause
