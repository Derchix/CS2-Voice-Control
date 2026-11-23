@echo off
chcp 65001 >nul
title CS2 Voice Control

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

echo [1/3] Проверка и установка зависимостей...
pip install -r requirements.txt --quiet

if not exist "vosk-model-small-ru-0.22" (
    echo [2/3] Загрузка языковой модели Vosk (45 МБ)...
    powershell -Command "Invoke-WebRequest -Uri 'https://alphacephei.com' -OutFile 'model.zip'"
    echo Распаковка архива...
    powershell -Command "Expand-Archive -Path 'model.zip' -DestinationPath '.' -Force"
    del model.zip
) else (
    echo [2/3] Языковая модель найдена.
)

echo [3/3] Запуск голосового управления...
python main.py
pause
