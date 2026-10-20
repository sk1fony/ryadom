@echo off
chcp 65001 >nul
pushd "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 bootstrap.py %*
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Установите Python 3.10 или новее с python.org
        echo При установке включите Add Python to PATH
        pause
        popd
        exit /b 1
    )
    python bootstrap.py %*
)
if errorlevel 1 pause
popd
