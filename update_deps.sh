#!/bin/bash
echo "Regenerando archivo de bloqueo de dependencias..."
poetry lock --no-update

echo ""
echo "Instalando dependencias..."
poetry install
