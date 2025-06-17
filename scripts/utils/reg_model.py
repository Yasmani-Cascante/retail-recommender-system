# SCRIPT 2: Regenerar modelo TF-IDF
# regenerate_model.py

import os
import logging

logger = logging.getLogger(__name__)

def force_model_regeneration():
    """Fuerza regeneración del modelo TF-IDF."""
    model_path = "data/tfidf_model.pkl"
    
    if os.path.exists(model_path):
        print(f"🗑️ Eliminando modelo incompatible: {model_path}")
        os.remove(model_path)
        print("✅ Modelo eliminado. Se regenerará automáticamente en el próximo inicio.")
    else:
        print("ℹ️ No se encontró modelo existente.")

if __name__ == "__main__":
    force_model_regeneration()