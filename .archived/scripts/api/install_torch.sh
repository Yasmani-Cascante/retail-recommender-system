#!/bin/bash
echo "Instalando PyTorch manualmente..."
pip install torch==1.13.1+cpu torchvision==0.14.1+cpu -f https://download.pytorch.org/whl/cpu/torch_stable.html

echo ""
echo "Instalando sentence-transformers..."
pip install sentence-transformers==2.2.2

echo ""
echo "Instalando dependencias restantes..."
poetry install --no-interaction
