@echo off
echo Creando entorno virtual con Poetry...
poetry env remove --all
poetry env use python

echo.
echo Instalando dependencias sin modelos de ML complejos...
poetry install --without sentence-transformers,torch

echo.
echo Verificando instalación básica...
poetry run python -c "import numpy; import scikit_learn; print('NumPy version:', numpy.__version__); print('scikit-learn version:', scikit_learn.__version__)"

echo.
echo Sistema listo para usar el recomendador TF-IDF
