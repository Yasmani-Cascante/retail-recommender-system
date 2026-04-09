"""
Recomendador basado en TF-IDF.

Este módulo implementa un recomendador más ligero basado en la técnica
de vectorización TF-IDF (Term Frequency-Inverse Document Frequency),
que no depende de modelos transformer pesados.
"""

import os
import pickle
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import asyncio
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


logger = logging.getLogger(__name__)

class TFIDFRecommender:
    """
    Recomendador que utiliza vectorización TF-IDF para generar recomendaciones
    basadas en similitud de contenido, sin necesidad de cargar modelos ML pesados.
    """
    
    def __init__(self, model_path: str = None):
        """
        Inicializar el recomendador TF-IDF.
        
        Args:
            model_path: Ruta al archivo de modelo TF-IDF pre-entrenado (.pkl), si existe
        """
        self.model_path = model_path
        self.vectorizer = None
        self.product_vectors = None
        self.product_data = None
        self.product_ids = None
        self.loaded = False
        
        # Variables para fallback
        self.fallback_active = False

    @staticmethod
    def _normalize_product_price(product: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aplana el precio de Shopify al nivel raíz del producto.

        FIX (27/03/2026) — Causa raíz del bug de precios en segunda ronda.

        La API REST de Shopify NO devuelve 'price' en el nivel raíz del producto.
        El precio está anidado en:
            product["variants"][0]["price"]  → str, ej. "159.00"

        Al guardar los productos crudos en product_data, product.get("price")
        retorna None. Cuando smart_fallback hace **product en el dict de la
        recomendación, hereda ese None. sanitize_rec_for_frontend lo convierte
        a 0.0, y ProductCard muestra €0.

        Este método crea una copia del producto con 'price' al nivel raíz,
        extrado de variants[0]["price"]. Si el producto ya tiene 'price' con
        un valor válido (>0), lo preserva sin modificar para no pisar datos
        ya normalizados por el MarketAdapter.

        Adicionalmente aplana image_url desde images[0]["src"] si no existe
        como campo directo, para que sanitize_rec_for_frontend también pueda
        encontrarlo sin depender de la lista anidada.
        """
        # Si ya tiene precio válido a nivel raíz, no modificar.
        # Permite que productos ya normalizados por el MarketAdapter pasen sin cambios.
        existing_price = product.get("price")
        try:
            if existing_price is not None and float(existing_price) > 0:
                return product  # Ya normalizado, devolver tal cual
        except (TypeError, ValueError):
            pass  # Valor inválido: continuar con extacción desde variants

        # Extraer precio desde variants[0].price (formato Shopify REST)
        price: float = 0.0
        variants = product.get("variants") or []
        if variants and isinstance(variants, list):
            try:
                price_str = variants[0].get("price") or "0"
                price = float(price_str)
            except (TypeError, ValueError, IndexError, AttributeError):
                price = 0.0

        # Extraer image_url desde images[0]["src"] si no existe como campo directo
        # para evitar que sanitize_rec_for_frontend deba parsear la lista anidada.
        image_url = product.get("image_url") or product.get("imageUrl")
        if not image_url:
            images = product.get("images") or []
            if images and isinstance(images, list):
                first = images[0]
                if isinstance(first, str):
                    image_url = first
                elif isinstance(first, dict):
                    image_url = first.get("src") or first.get("url") or first.get("originalSrc")

        # Devolver copia con campos normalizados al nivel raíz.
        # Usamos {**product, ...} para no mutar el original y mantener
        # todos los demás campos intactos (tags, body_html, variants, etc.).
        return {
            **product,
            "price": price,                   # float al nivel raíz
            **({
                "image_url": image_url,       # str al nivel raíz (si se encontró)
            } if image_url else {}),
        }

    async def fit(self, products: List[Dict[str, Any]]) -> bool:
        """
        Entrena el modelo TF-IDF con los datos de productos.
        
        Args:
            products: Lista de productos (diccionarios)
            
        Returns:
            True si el entrenamiento fue exitoso, False en caso contrario
        """
        try:
            logger.info(f"Entrenando recomendador TF-IDF con {len(products)} productos")
            
            # Guardar datos de productos.
            # FIX (27/03/2026): Aplanar price desde variants[0].price al nivel raíz
            # antes de indexar.  La API REST de Shopify devuelve el precio en:
            #   product["variants"][0]["price"]  (str, ej. "159.00")
            # y NO en product["price"] (campo ausente o None a nivel raíz).
            # Sin este aplano, product_data[i].get("price") retorna None para todos
            # los productos.  El path de diversificación (smart_fallback) hace
            # **product y hereda ese None, por eso ProductCard recibe price=0.
            self.product_data = [self._normalize_product_price(p) for p in products]
            self.product_ids = [str(p.get('id', i)) for i, p in enumerate(self.product_data)]
            
            # Extraer textos para vectorización
            texts = []
            for product in products:
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
                
                text = f"{title}. {description}. Categoría: {category}. Tags: {tags}".strip()
                texts.append(text)
            
            # Crear y entrenar vectorizador TF-IDF
            self.vectorizer = TfidfVectorizer(
                max_features=5000,    # Limitar características para mejorar rendimiento
                stop_words='english',  # Eliminar palabras comunes
                min_df=2,             # Término debe aparecer en al menos 2 documentos
                ngram_range=(1, 2)    # Usar unigramas y bigramas
            )
            
            # Transformar textos a vectores TF-IDF
            self.product_vectors = self.vectorizer.fit_transform(texts)
            
            # Guardar modelo si se especificó ruta
            if self.model_path:
                model_dir = os.path.dirname(self.model_path)
                if model_dir and not os.path.exists(model_dir):
                    os.makedirs(model_dir, exist_ok=True)
                
                # CORRECCIÓN: Guardar también los datos de productos y IDs
                with open(self.model_path, 'wb') as f:
                    pickle.dump({
                        'vectorizer': self.vectorizer,
                        'product_vectors': self.product_vectors,
                        'product_data': self.product_data,  # Añadir datos de productos
                        'product_ids': self.product_ids     # Añadir IDs de productos
                    }, f)
                logger.info(f"Modelo TF-IDF guardado en {self.model_path} con {len(self.product_data)} productos")
            
            self.loaded = True
            await self._build_category_index()
            logger.info(f"Recomendador TF-IDF entrenado exitosamente")
            return True
            
        except Exception as e:
            logger.error(f"Error entrenando recomendador TF-IDF: {e}")
            return False
    
    async def load(self, model_path: str = None) -> bool:
        """
        Carga un modelo TF-IDF pre-entrenado.
        
        Args:
            model_path: Ruta al archivo de modelo TF-IDF (.pkl)
            
        Returns:
            True si la carga fue exitosa, False en caso contrario
        """
        path = model_path or self.model_path
        
        if not path:
            logger.warning("No se especificó ruta para cargar modelo TF-IDF")
            return False
        
        try:
            logger.info(f"Cargando modelo TF-IDF desde {path}")
            
            with open(path, 'rb') as f:
                data = pickle.load(f)
                
            self.vectorizer = data['vectorizer']
            self.product_vectors = data['product_vectors']
            
            # CORRECCIÓN CRITICA: Verificar si hay product_data en el modelo
            if 'product_data' in data:
                self.product_data = data['product_data']
                self.product_ids = data.get('product_ids', [str(p.get('id', i)) for i, p in enumerate(self.product_data)])
                logger.info(f"Datos de productos cargados desde modelo: {len(self.product_data)} productos")
            else:
                logger.warning("El modelo no contiene datos de productos. Necesitará reentrenar o cargar productos.")
                # IMPORTANTE: No marcar como loaded si no hay product_data
                return False
            
            self.loaded = True
            await self._build_category_index()
            logger.info(f"Modelo TF-IDF cargado exitosamente con {len(self.product_data) if self.product_data else 0} productos")
            return True
            
        except Exception as e:
            logger.error(f"Error cargando modelo TF-IDF: {e}")
            return False
    
    async def get_recommendations(self, product_id: str, n: int = 5) -> List[Dict[str, Any]]:
        """
        Obtiene recomendaciones basadas en un producto utilizando TF-IDF.
        
        Args:
            product_id: ID del producto para el cual obtener recomendaciones
            n: Número de recomendaciones a devolver
            
        Returns:
            Lista de productos recomendados con scores de similitud
        """
        # Verificar que el modelo esté listo
        if not self.loaded or self.product_vectors is None:
            logger.error("El recomendador TF-IDF no está cargado o entrenado")
            return []
        
        try:
            # Encontrar índice del producto
            if product_id not in self.product_ids:
                logger.warning(f"Producto ID {product_id} no encontrado")
                return []
            
            product_index = self.product_ids.index(product_id)
            
            # Obtener vector del producto
            product_vector = self.product_vectors[product_index]
            
            # Calcular similitud con todos los productos
            similarities = cosine_similarity(product_vector, self.product_vectors)[0]
            
            # Obtener índices ordenados por similitud (excluyendo el propio producto)
            similar_indices = similarities.argsort()[::-1][1:n+1]
            
            # Construir lista de recomendaciones
            recommendations = []
            for index in similar_indices:
                product = self.product_data[index]
                recommendations.append({
                    "id": self.product_ids[index],
                    "title": product.get("title", ""),
                    "similarity_score": float(similarities[index]),
                    "handle": product.get("handle", ""),
                    "product_data": product
                })
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generando recomendaciones: {e}")
            return []
    
    async def search_products(self, query: str, n: int = 10) -> List[Dict[str, Any]]:
        """
        Busca productos por texto utilizando similitud TF-IDF.
        
        Args:
            query: Texto de búsqueda
            n: Número máximo de resultados
            
        Returns:
            Lista de productos que coinciden con la búsqueda
        """
        # Verificar que el modelo esté listo
        if not self.loaded or self.vectorizer is None:
            logger.error("El recomendador TF-IDF no está cargado o entrenado")
            return []
        
        try:
            # Convertir consulta a vector TF-IDF
            query_vector = self.vectorizer.transform([query])
            
            # Calcular similitud con todos los productos
            similarities = cosine_similarity(query_vector, self.product_vectors)[0]
            
            # Obtener índices ordenados por similitud
            similar_indices = similarities.argsort()[::-1][:n]
            
            # Filtrar resultados con score muy bajo
            threshold = 0.1
            filtered_indices = [i for i in similar_indices if similarities[i] > threshold]
            
            # Construir lista de resultados
            results = []
            for index in filtered_indices:
                product = self.product_data[index]
                results.append({
                    "id": self.product_ids[index],
                    "title": product.get("title", ""),
                    "similarity_score": float(similarities[index]),
                    "product_data": product
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Error en búsqueda de productos: {e}")
            return []
    
    def get_product_by_id(self, product_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene un producto del catálogo local por su ID.

        Usa id_index (O(1)) si está disponible (construido por _build_category_index).
        Fallback al scan lineal O(n) si id_index aún no existe (ej. modelos cargados
        antes de este cambio que no tienen el índice en memoria).

        Args:
            product_id: ID del producto a buscar

        Returns:
            Dict con la información del producto, o None si no se encuentra
        """
        if not self.loaded or not self.product_data:
            logger.warning("El recomendador TF-IDF no está cargado o no tiene datos de productos")
            return None

        try:
            # O(1): usar id_index si está disponible
            if hasattr(self, 'id_index') and self.id_index:
                return self.id_index.get(str(product_id))

            # Fallback O(n): scan lineal para compatibilidad con modelos legacy
            # (solo ocurre en el primer request tras cargar un modelo antiguo;
            # _build_category_index ya corre en fit() y load(), así que este
            # camino solo se activa si id_index no existía en el pickle).
            logger.debug(
                f"id_index not available, falling back to linear scan "
                f"for product_id={product_id}"
            )
            for product in self.product_data:
                if str(product.get('id', '')) == str(product_id):
                    return product

            logger.warning(f"Producto con ID {product_id} no encontrado en el catálogo local")
            return None
        except Exception as e:
            logger.error(f"Error al buscar producto por ID: {e}")
            return None

    async def health_check(self) -> Dict[str, Any]:
        """
        Verifica el estado del recomendador.
        
        Returns:
            Diccionario con información de estado
        """
        # Calcular productos count de forma segura
        products_count = 0
        if self.loaded and self.product_data is not None:
            products_count = len(self.product_data)
        
        # Calcular features count de forma segura
        features_count = 0
        if self.loaded and self.vectorizer is not None:
            try:
                features_count = self.vectorizer.get_feature_names_out().shape[0]
            except:
                features_count = 0
        
        status = {
            "name": "tfidf_recommender",
            "status": "operational" if self.loaded else "unavailable",
            "loaded": self.loaded,
            "products_count": products_count,
            "vectorizer_features": features_count,
            "fallback_active": self.fallback_active,
            "has_product_data": self.product_data is not None,
            "has_vectorizer": self.vectorizer is not None,
            "has_vectors": self.product_vectors is not None
        }
        return status
    

    async def _build_category_index(self):
        """
        Build category index and id index for O(1) lookups.

        Performance: O(n) one-time cost, O(1) lookups después.
        Async: yields control every batch_size products so the event loop
        can serve other requests during indexing.

        id_index (NEW): maps str(product_id) → product dict.
        Used by get_product_by_id() to replace the previous O(n) linear scan,
        which caused the 'product_cache_preload_completed' log to take ~2.2s
        for 8 products x 3062 catalog scan per product.
        After this change: get_product_by_id() is O(1) — instant lookup.
        """
        self.category_index = {}
        # id_index: str(id) -> product dict, para lookup O(1)
        self.id_index: dict = {}

        # Process in batches to yield control to the event loop
        batch_size = 500
        for i in range(0, len(self.product_data), batch_size):
            batch = self.product_data[i:i + batch_size]

            for product in batch:
                # ── Category index ───────────────────────────────────────
                category = product.get("product_type", "").upper()
                if category:
                    if category not in self.category_index:
                        self.category_index[category] = []
                    self.category_index[category].append(product)

                # ── ID index (nuevo) ──────────────────────────────────
                pid = str(product.get("id", ""))
                if pid:
                    self.id_index[pid] = product

            # Yield control to event loop every batch (500 products)
            await asyncio.sleep(0)

        logger.info(f"✅ Category index built: {len(self.category_index)} categories")
        logger.info(f"   Categories: {sorted(self.category_index.keys())}")
        logger.info(f"✅ ID index built: {len(self.id_index)} products (O(1) lookups enabled)")

        return self.category_index
