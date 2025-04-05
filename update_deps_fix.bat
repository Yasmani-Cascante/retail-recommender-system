@echo off
echo Regenerando archivo de bloqueo de dependencias...
poetry lock --no-cache --regenerate

echo.
echo Instalando dependencias...
poetry install
