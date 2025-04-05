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
            
            # Guardar datos de productos
            self.product_data = products
            self.product_ids = [str(p.get('id', i)) for i, p in enumerate(products)]
            
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
                
                with open(self.model_path, 'wb') as f:
                    pickle.dump({
                        'vectorizer': self.vectorizer,
                        'product_vectors': self.product_vectors
                    }, f)
                logger.info(f"Modelo TF-IDF guardado en {self.model_path}")
            
            self.loaded = True
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
            self.loaded = True
            
            logger.info(f"Modelo TF-IDF cargado exitosamente")
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
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Verifica el estado del recomendador.
        
        Returns:
            Diccionario con información de estado
        """
        status = {
            "name": "tfidf_recommender",
            "status": "operational" if self.loaded else "unavailable",
            "loaded": self.loaded,
            "products_count": len(self.product_data) if self.loaded else 0,
            "vectorizer_features": self.vectorizer.get_feature_names_out().shape[0] if self.loaded and self.vectorizer else 0,
            "fallback_active": self.fallback_active
        }
        return status
