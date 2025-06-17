@echo off
echo Creando entorno virtual con Poetry...
poetry env remove --all
poetry env use python
poetry install --without torch,sentence-transformers,huggingface-hub

echo.
echo Instalando versiones compatibles de PyTorch, huggingface-hub y sentence-transformers...
poetry run pip install torch==1.13.1 --extra-index-url https://download.pytorch.org/whl/cpu
poetry run pip install "huggingface-hub==0.12.0"
poetry run pip install "sentence-transformers==2.2.2"

echo.
echo Verificando instalacion...
poetry run python -c "import torch; import sentence_transformers; from sentence_transformers import SentenceTransformer; print('PyTorch version:', torch.__version__); print('Sentence Transformers version:', sentence_transformers.__version__)"
