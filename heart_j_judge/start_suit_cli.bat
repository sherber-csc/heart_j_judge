@echo off
cd /d "%~dp0"
python main_suit.py

if errorlevel 1 (
    echo.
    echo [Heart J Judge] Failed to start the Suit Guess CLI.
    pause
)
