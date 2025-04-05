#!/usr/bin/env python3
"""
Script para pre-computar embeddings de productos.

Este script carga los datos de productos, genera embeddings usando sentence-transformers,
y guarda los resultados para uso en producción sin necesidad de cargar modelos ML pesados.
"""

import os
import sys
import pickle
import logging
import traceback
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Union

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"precompute_{time.strftime('%Y%m%d_%H%M%S')}.log")
    ]
)
logger = logging.getLogger(__name__)

def safe_import_transformers() -> Any:
    """
    Importa sentence-transformers con manejo seguro de errores.
    
    Returns:
        El módulo SentenceTransformer o termina el programa si falla
    """
    try:
        from sentence_transformers import SentenceTransformer
        logger.info("✓ Sentence Transformers importado exitosamente")
        return SentenceTransformer
    except ImportError as e:
        logger.error(f"✗ Error importando sentence-transformers: {e}")
        logger.error("  Asegúrate de haber instalado las dependencias correctamente:")
        logger.error("  pip install sentence-transformers==2.2.2 torch==1.13.1")
        sys.exit(1)

def add_project_to_path() -> None:
    """Añade el directorio raíz del proyecto al path para importaciones."""
    # Obtener directorio raíz del proyecto (2 niveles arriba de scripts/)
    project_root = Path(__file__).parent.parent.absolute()
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
        logger.info(f"Añadido {project_root} al path de Python")

def load_product_data() -> List[Dict[str, Any]]:
    """
    Carga datos de productos con múltiples fallbacks.
    
    Returns:
        Lista de productos
    """
    add_project_to_path()
    
    try:
        # Intento 1: Cargar desde Shopify si está configurado
        if os.getenv("SHOPIFY_ACCESS_TOKEN") and os.getenv("SHOPIFY_SHOP_URL"):
            logger.info("Intentando cargar productos desde Shopify...")
            try:
                from src.api.integrations.shopify_client import get_shopify_products
                products = get_shopify_products()
                if products and len(products) > 0:
                    logger.info(f"✓ Cargados {len(products)} productos desde Shopify")
                    return products
            except Exception as e:
                logger.warning(f"! No se pudieron cargar productos desde Shopify: {e}")
        
        # Intento 2: Cargar desde datos de muestra en el módulo
        logger.info("Intentando cargar productos desde datos de muestra en código...")
        try:
            from src.api.core.sample_data import SAMPLE_PRODUCTS
            if SAMPLE_PRODUCTS and len(SAMPLE_PRODUCTS) > 0:
                logger.info(f"✓ Cargados {len(SAMPLE_PRODUCTS)} productos de muestra")
                return SAMPLE_PRODUCTS
        except Exception as e:
            logger.warning(f"! No se pudieron cargar productos de muestra desde código: {e}")
        
        # Intento 3: Cargar desde archivo local
        logger.info("Intentando cargar productos desde archivo local...")
        sample_paths = [
            Path("data/sample_products.pkl"),
            Path("src/api/core/sample_products.pkl"),
            Path("sample_products.pkl")
        ]
        
        for path in sample_paths:
            if path.exists():
                try:
                    with open(path, "rb") as f:
                        products = pickle.load(f)
                        if products and len(products) > 0:
                            logger.info(f"✓ Cargados {len(products)} productos desde {path}")
                            return products
                except Exception as e:
                    logger.warning(f"! Error al cargar desde {path}: {e}")
        
        # Último recurso: Crear datos de muestra básicos
        logger.warning("! No se encontraron datos de productos. Creando datos mínimos de muestra.")
        minimal_products = [
            {
                "id": "product1",
                "title": "Camiseta básica",
                "body_html": "Camiseta de algodón de alta calidad.",
                "product_type": "Ropa"
            },
            {
                "id": "product2",
                "title": "Pantalón vaquero",
                "body_html": "Pantalón vaquero clásico de corte recto.",
                "product_type": "Ropa"
            },
            {
                "id": "product3",
                "title": "Zapatillas deportivas",
                "body_html": "Zapatillas para running con amortiguación.",
                "product_type": "Calzado"
            }
        ]
        logger.info(f"✓ Creados {len(minimal_products)} productos mínimos de muestra")
        return minimal_products
    
    except Exception as e:
        logger.error(f"✗ Error crítico cargando datos de productos: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)

def extract_product_text(product: Dict[str, Any]) -> str:
    """
    Extrae texto relevante de un producto para generar embeddings.
    
    Args:
        product: Diccionario con datos del producto
        
    Returns:
        Texto combinado para generar embeddings
    """
    # Extraer campos con manejo de valores faltantes
    title = product.get('title', '') or product.get('name', '')
    description = (
        product.get('body_html', '') or 
        product.get('description', '') or 
        product.get('body', '')
    )
    category = (
        product.get('product_type', '') or 
        product.get('category', '') or 
        product.get('type', '')
    )
    tags = product.get('tags', '') or ''
    
    if isinstance(tags, list):
        tags = ' '.join(tags)
    
    # Combinar textos en un formato apropiado
    text = f"{title}. {description}. Categoría: {category}. Tags: {tags}".strip()
    return text

def precompute_embeddings() -> bool:
    """
    Pre-computa y guarda embeddings de productos.
    
    Returns:
        True si la operación fue exitosa, False en caso contrario
    """
    try:
        # Crear directorio data si no existe
        os.makedirs("data", exist_ok=True)
        
        # 1. Importar SentenceTransformer
        SentenceTransformer = safe_import_transformers()
        
        # 2. Cargar modelo
        logger.info("Cargando modelo de embeddings...")
        start_time = time.time()
        model = SentenceTransformer('all-MiniLM-L6-v2')
        logger.info(f"✓ Modelo cargado en {time.time() - start_time:.2f} segundos")
        
        # 3. Cargar datos de productos
        products = load_product_data()
        if not products or len(products) == 0:
            raise ValueError("No se pudieron cargar productos o la lista está vacía")
        
        logger.info(f"✓ Cargados {len(products)} productos")
        
        # 4. Extraer textos para embeddings
        logger.info("Preparando textos para embeddings...")
        product_texts = []
        for i, product in enumerate(products):
            text = extract_product_text(product)
            product_texts.append(text)
            
            # Mostrar progreso cada 100 productos
            if (i + 1) % 100 == 0 or i == 0 or i == len(products) - 1:
                logger.info(f"  Procesados {i+1}/{len(products)} productos")
        
        # 5. Computar embeddings
        logger.info("Calculando embeddings...")
        start_time = time.time()
        embeddings = model.encode(product_texts, show_progress_bar=True)
        logger.info(f"✓ Embeddings calculados en {time.time() - start_time:.2f} segundos")
        
        # 6. Verificar integridad de embeddings
        if len(embeddings) != len(products):
            raise ValueError(f"Número de embeddings ({len(embeddings)}) no coincide con productos ({len(products)})")
        
        # 7. Guardar productos y embeddings
        logger.info("Guardando embeddings y datos de productos...")
        with open("data/embeddings.pkl", "wb") as f:
            pickle.dump(embeddings, f)
        
        with open("data/product_data.pkl", "wb") as f:
            pickle.dump(products, f)
        
        logger.info(f"✓ Pre-computación completada exitosamente: {len(products)} productos procesados")
        logger.info(f"  Embeddings guardados en: data/embeddings.pkl")
        logger.info(f"  Datos de productos guardados en: data/product_data.pkl")
        return True
    
    except Exception as e:
        logger.error(f"✗ Error durante pre-computación: {e}")
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    success = precompute_embeddings()
    sys.exit(0 if success else 1)
