@echo off
echo Creando entorno virtual con Poetry...
poetry env remove --all
poetry env use python
poetry install --without torch,sentence-transformers

echo.
echo Instalando PyTorch y sentence-transformers manualmente...
poetry run pip install torch==2.0.1
poetry run pip install sentence-transformers==2.2.2

echo.
echo Verificando instalacion...
poetry run python -c "import torch; import sentence_transformers; print('PyTorch version:', torch.__version__); print('Sentence Transformers installed')"
