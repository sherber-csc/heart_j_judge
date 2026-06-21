@echo off
cd /d "%~dp0"

if not exist ".ui_deps\streamlit" (
    echo [Heart J Judge] First-time setup: installing Streamlit locally...
    python -m pip install streamlit --target ".ui_deps"
    if errorlevel 1 (
        echo.
        echo [Heart J Judge] Failed to install Streamlit.
        echo Please check your network or Python/pip environment, then try again.
        pause
        exit /b 1
    )
)

set "PYTHONPATH=%~dp0.ui_deps;%PYTHONPATH%"
python -m streamlit run ui_suit.py --global.developmentMode false

if errorlevel 1 (
    echo.
    echo [Heart J Judge] Failed to start the UI.
    pause
)
