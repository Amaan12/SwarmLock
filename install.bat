@echo off
echo ========================================================
echo   Installing SwarmLock Multi-Agent Coordinator Globally
echo ========================================================
echo.
python -m pip install -e .
echo.
if %ERRORLEVEL% EQU 0 (
    echo [SUCCESS] SwarmLock installed! You can now run 'swarmlock' anywhere.
    echo Try: swarmlock --help
) else (
    echo [ERROR] Installation failed. Please check Python and pip are installed.
)
pause
