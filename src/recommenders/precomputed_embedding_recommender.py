"""
Recomendador basado en embeddings pre-computados.

Este módulo implementa un recomendador que utiliza embeddings pre-calculados
en lugar de cargar modelos completos de ML en tiempo de ejecución, permitiendo
un arranque rápido y eficiente en entornos cloud.
"""

import os
import pickle
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

class PrecomputedEmbeddingRecommender:
    """
    Recomendador que utiliza embeddings pre-computados para generar recomendaciones
    basadas en similitud de contenido, sin necesidad de cargar modelos ML en runtime.
    """
    
    def __init__(self, embeddings_path: str = None, products_path: str = None):
        """
        Inicializar el recomendador con rutas a los archivos de embeddings y productos.
        
        Args:
            embeddings_path: Ruta al archivo de embeddings pre-computados (.pkl)
            products_path: Ruta al archivo de datos de productos (.pkl)
        """
        self.embeddings_path = embeddings_path or "data/embeddings.pkl"
        self.products_path = products_path or "data/product_data.pkl"
        self.product_embeddings = None
        self.product_data = None
        self.product_ids = None
        self.loaded = False
        
        # Variables para fallback
        self.fallback_active = False
    
    def _find_embedding_file(self) -> Optional[str]:
        """Busca el archivo de embeddings en múltiples ubicaciones."""
        possible_paths = [
            self.embeddings_path,
            os.path.join(os.path.dirname(__file__), '..', '..', self.embeddings_path),
            os.path.join('src', 'data', 'embeddings.pkl'),
            os.path.join('data', 'embeddings.pkl')
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def _find_products_file(self) -> Optional[str]:
        """Busca el archivo de datos de productos en múltiples ubicaciones."""
        possible_paths = [
            self.products_path,
            os.path.join(os.path.dirname(__file__), '..', '..', self.products_path),
            os.path.join('src', 'data', 'product_data.pkl'),
            os.path.join('data', 'product_data.pkl')
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    async def load(self) -> bool:
        """
        Carga los embeddings y datos de productos pre-computados.
        
        Returns:
            True si la carga fue exitosa, False en caso contrario
        """
        try:
            # Buscar archivos
            embeddings_file = self._find_embedding_file()
            products_file = self._find_products_file()
            
            if not embeddings_file:
                logger.warning(f"No se encontró archivo de embeddings en {self.embeddings_path} ni en rutas alternativas")
                return False
            
            if not products_file:
                logger.warning(f"No se encontró archivo de productos en {self.products_path} ni en rutas alternativas")
                return False
            
            # Cargar embeddings
            logger.info(f"Cargando embeddings desde {embeddings_file}...")
            with open(embeddings_file, 'rb') as f:
                self.product_embeddings = pickle.load(f)
            
            # Cargar datos de productos
            logger.info(f"Cargando datos de productos desde {products_file}...")
            with open(products_file, 'rb') as f:
                self.product_data = pickle.load(f)
            
            # Extraer IDs de productos
            self.product_ids = [str(p.get('id', i)) for i, p in enumerate(self.product_data)]
            
            # Verificar integridad
            if len(self.product_embeddings) != len(self.product_data):
                logger.error(f"Inconsistencia: {len(self.product_embeddings)} embeddings vs {len(self.product_data)} productos")
                return False
            
            self.loaded = True
            logger.info(f"✓ Recomendador cargado exitosamente con {len(self.product_data)} productos")
            return True
            
        except Exception as e:
            logger.error(f"Error cargando embeddings pre-computados: {e}")
            return False
    
    async def get_recommendations(self, product_id: str, n: int = 5) -> List[Dict[str, Any]]:
        """
        Obtiene recomendaciones basadas en un producto utilizando embeddings pre-computados.
        
        Args:
            product_id: ID del producto para el cual obtener recomendaciones
            n: Número de recomendaciones a devolver
            
        Returns:
            Lista de productos recomendados con scores de similitud
        """
        # Cargar datos si no se han cargado previamente
        if not self.loaded:
            success = await self.load()
            if not success:
                logger.error("No se pudieron cargar los embeddings pre-computados")
                return []
        
        try:
            # Encontrar índice del producto
            if product_id not in self.product_ids:
                logger.warning(f"Producto ID {product_id} no encontrado")
                return []
            
            product_index = self.product_ids.index(product_id)
            
            # Obtener embedding del producto
            product_embedding = self.product_embeddings[product_index]
            
            # Reshape para calcular similitud
            product_embedding_reshaped = product_embedding.reshape(1, -1)
            
            # Calcular similitud con todos los productos
            similarities = cosine_similarity(product_embedding_reshaped, self.product_embeddings)[0]
            
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
        Busca productos por texto utilizando similitud de embeddings pre-computados.
        
        Args:
            query: Texto de búsqueda
            n: Número máximo de resultados
            
        Returns:
            Lista de productos que coinciden con la búsqueda
        """
        # Esta funcionalidad requeriría re-utilizar el modelo para generar
        # el embedding de la consulta, lo cual no está disponible en este recomendador
        # que solo utiliza embeddings pre-computados.
        logger.warning("Búsqueda por texto no disponible en el recomendador pre-computado")
        return []
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Verifica el estado del recomendador.
        
        Returns:
            Diccionario con información de estado
        """
        status = {
            "name": "precomputed_embedding_recommender",
            "status": "operational" if self.loaded else "unavailable",
            "loaded": self.loaded,
            "products_count": len(self.product_data) if self.loaded else 0,
            "embeddings_count": len(self.product_embeddings) if self.loaded else 0,
            "fallback_active": self.fallback_active
        }
        return status
