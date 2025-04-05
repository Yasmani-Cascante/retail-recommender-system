
import numpy as np
import json
import logging
import os
import time
from sentence_transformers import SentenceTransformer

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def precompute_embeddings():
    """
    Pre-computa embeddings para todos los productos y los guarda en archivos
    que pueden ser fácilmente cargados en runtime.
    """
    start_time = time.time()
    logging.info("Iniciando pre-computación de embeddings...")
    
    # 1. Cargar productos
    try:
        # Primero intentar importar desde src.api.core.store
        try:
            from src.api.core.store import init_shopify
            client = init_shopify()
            if client:
                products = client.get_products()
                logging.info(f"Cargados {len(products)} productos desde Shopify")
            else:
                # Si no hay cliente Shopify, usar datos de muestra
                from src.api.core.sample_data import SAMPLE_PRODUCTS
                products = SAMPLE_PRODUCTS
                logging.info(f"Usando {len(products)} productos de muestra")
        except Exception as e:
            logging.warning(f"Error importando desde src.api.core.store: {str(e)}")
            # Si falla, intentar importar solo los datos de muestra
            try:
                from src.api.core.sample_data import SAMPLE_PRODUCTS
                products = SAMPLE_PRODUCTS
                logging.info(f"Usando {len(products)} productos de muestra (fallback)")
            except Exception as e2:
                logging.error(f"Error importando datos de muestra: {str(e2)}")
                # Como último recurso, definir productos de muestra aquí
                products = [
                    {
                        "id": "1",
                        "title": "T-Shirt",
                        "body_html": "Basic cotton t-shirt",
                        "variants": [{"price": "19.99"}],
                        "product_type": "Clothing"
                    },
                    {
                        "id": "2",
                        "title": "Jeans",
                        "body_html": "Comfortable denim jeans",
                        "variants": [{"price": "49.99"}],
                        "product_type": "Clothing"
                    },
                    {
                        "id": "3",
                        "title": "Sneakers",
                        "body_html": "Casual sneakers",
                        "variants": [{"price": "79.99"}],
                        "product_type": "Footwear"
                    }
                ]
                logging.info(f"Usando {len(products)} productos de muestra hardcoded")
        
        # Debug: Mostrar estructura del primer producto
        if products and len(products) > 0:
            logging.debug(f"Estructura del primer producto: {list(products[0].keys())}")
    except Exception as e:
        logging.error(f"Error cargando productos: {str(e)}")
        # Definir productos de muestra como fallback final
        products = [
            {
                "id": "1",
                "title": "T-Shirt",
                "body_html": "Basic cotton t-shirt",
                "variants": [{"price": "19.99"}],
                "product_type": "Clothing"
            },
            {
                "id": "2",
                "title": "Jeans",
                "body_html": "Comfortable denim jeans",
                "variants": [{"price": "49.99"}],
                "product_type": "Clothing"
            },
            {
                "id": "3",
                "title": "Sneakers",
                "body_html": "Casual sneakers",
                "variants": [{"price": "79.99"}],
                "product_type": "Footwear"
            }
        ]
        logging.info(f"Fallback a {len(products)} productos de muestra")
    
    # 2. Cargar modelo de embeddings
    logging.info("Cargando modelo sentence-transformers...")
    try:
        model = SentenceTransformer('all-MiniLM-L6-v2')
        logging.info("Modelo de embeddings cargado correctamente")
    except Exception as e:
        logging.error(f"Error cargando modelo de embeddings: {str(e)}")
        return False
    
    # 3. Preparar datos para embeddings
    product_ids = [str(p.get('id', '')) for p in products]
    descriptions = [f"{p.get('title', '')}. {p.get('body_html', '')}" for p in products]
    
    logging.info(f"Generando embeddings para {len(descriptions)} productos...")
    
    # 4. Generar embeddings
    try:
        embeddings = model.encode(descriptions)
        logging.info(f"Embeddings generados correctamente: {embeddings.shape}")
    except Exception as e:
        logging.error(f"Error generando embeddings: {str(e)}")
        return False
    
    # 5. Guardar embeddings y metadatos
    os.makedirs('embeddings', exist_ok=True)
    
    try:
        np.save('embeddings/product_embeddings.npy', embeddings)
        logging.info("Embeddings guardados en embeddings/product_embeddings.npy")
    except Exception as e:
        logging.error(f"Error guardando embeddings: {str(e)}")
        return False
    
    # Guardar metadata de productos (solo lo necesario)
    product_metadata = []
    for p in products:
        # Extraer precio
        price = 0.0
        if p.get("variants") and len(p["variants"]) > 0:
            price_str = p["variants"][0].get("price", "0")
            try:
                price = float(price_str)
            except (ValueError, TypeError):
                price = 0.0
                
        # Extraer metadatos relevantes
        product_metadata.append({
            "id": str(p.get("id", "")),
            "title": p.get("title", ""),
            "description": p.get("body_html", ""),
            "price": price,
            "category": p.get("product_type", "General")
        })
    
    try:
        with open('embeddings/product_metadata.json', 'w') as f:
            json.dump(product_metadata, f)
        logging.info("Metadatos guardados en embeddings/product_metadata.json")
    except Exception as e:
        logging.error(f"Error guardando metadatos: {str(e)}")
        return False
    
    try:
        with open('embeddings/product_ids.json', 'w') as f:
            json.dump(product_ids, f)
        logging.info("IDs guardados en embeddings/product_ids.json")
    except Exception as e:
        logging.error(f"Error guardando IDs: {str(e)}")
        return False
    
    end_time = time.time()
    logging.info(f"Pre-computación completada en {end_time - start_time:.2f} segundos. Archivos generados:")
    logging.info(f"- embeddings/product_embeddings.npy: {embeddings.shape}")
    logging.info(f"- embeddings/product_metadata.json: {len(product_metadata)} productos")
    logging.info(f"- embeddings/product_ids.json: {len(product_ids)} IDs")
    
    return True

if __name__ == "__main__":
    if precompute_embeddings():
        logging.info("✅ Pre-computación completada exitosamente")
    else:
        logging.error("❌ Error en pre-computación")
        exit(1)
