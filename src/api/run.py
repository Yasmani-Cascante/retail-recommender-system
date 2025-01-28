import uvicorn
import sys
from pathlib import Path

# Añadir el directorio raíz al PATH de Python
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))

if __name__ == "__main__":
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)