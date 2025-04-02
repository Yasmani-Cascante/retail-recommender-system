
from sentence_transformers import SentenceTransformer
import numpy as np
import json
import logging
import os
from src.api.core.store import init_shopify
import time

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
        client = init_shopify()
        if client:
            products = client.get_products()
            logging.info(f"Cargados {len(products)} productos desde Shopify")
        else:
            # Si no hay cliente Shopify, usar datos de muestra
            from src.api.core.sample_data import SAMPLE_PRODUCTS
            products = SAMPLE_PRODUCTS
            logging.info(f"Usando {len(products)} productos de muestra")
            
        # Debug: Mostrar estructura del primer producto
        if products and len(products) > 0:
            logging.debug(f"Estructura del primer producto: {list(products[0].keys())}")
    except Exception as e:
        logging.error(f"Error cargando productos: {str(e)}")
        # Fallback a datos de muestra
        from src.api.core.sample_data import SAMPLE_PRODUCTS
        products = SAMPLE_PRODUCTS
        logging.info(f"Fallback a {len(products)} productos de muestra")
    
    # 2. Cargar modelo de embeddings
    logging.info("Cargando modelo sentence-transformers...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    # 3. Preparar datos para embeddings
    product_ids = [str(p.get('id')) for p in products]
    descriptions = [f"{p.get('title', '')}. {p.get('body_html', '')}" for p in products]
    
    logging.info(f"Generando embeddings para {len(descriptions)} productos...")
    
    # 4. Generar embeddings
    embeddings = model.encode(descriptions)
    
    # 5. Guardar embeddings y metadatos
    os.makedirs('embeddings', exist_ok=True)
    np.save('embeddings/product_embeddings.npy', embeddings)
    
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
    
    with open('embeddings/product_metadata.json', 'w') as f:
        json.dump(product_metadata, f)
    
    with open('embeddings/product_ids.json', 'w') as f:
        json.dump(product_ids, f)
    
    end_time = time.time()
    logging.info(f"Pre-computación completada en {end_time - start_time:.2f} segundos. Archivos generados:")
    logging.info(f"- embeddings/product_embeddings.npy: {embeddings.shape}")
    logging.info(f"- embeddings/product_metadata.json: {len(product_metadata)} productos")
    logging.info(f"- embeddings/product_ids.json: {len(product_ids)} IDs")

if __name__ == "__main__":
    precompute_embeddings()
