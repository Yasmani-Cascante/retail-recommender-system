"""
Recomendador basado en TF-IDF - Versión corregida.

Este módulo implementa un recomendador TF-IDF con manejo robusto del estado
y carga correcta de todos los componentes necesarios.

CORRECCIÓN PRINCIPAL:
- Guarda y carga product_data y product_ids junto con el modelo
- Validación robusta del estado del recomendador
- Compatibilidad con modelos existentes (migración automática)
"""

import os
import pickle
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class TFIDFRecommender:
    """
    Recomendador que utiliza vectorización TF-IDF para generar recomendaciones
    basadas en similitud de contenido, con manejo robusto del estado.
    
    CORRECCIÓN: Ahora guarda y carga TODOS los datos necesarios.
    """
    
    # Versión del formato de modelo para compatibilidad
    MODEL_VERSION = "1.1.0"
    
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
        
        # Metadatos del modelo
        self.model_metadata = {
            "version": self.MODEL_VERSION,
            "created_at": None,
            "products_count": 0,
            "features_count": 0
        }
    
    def _validate_state(self) -> bool:
        """
        Valida que el recomendador esté en un estado consistente y operativo.
        
        Returns:
            True si el estado es válido, False en caso contrario
        """
        if not self.loaded:
            logger.warning("Recomendador no está marcado como cargado")
            return False
            
        if self.vectorizer is None:
            logger.error("Vectorizador TF-IDF no está disponible")
            return False
            
        if self.product_vectors is None:
            logger.error("Vectores de productos no están disponibles")
            return False
            
        if self.product_data is None:
            logger.error("Datos de productos no están disponibles")
            return False
            
        if self.product_ids is None:
            logger.error("IDs de productos no están disponibles")
            return False
            
        if len(self.product_data) != len(self.product_ids):
            logger.error(f"Inconsistencia: {len(self.product_data)} productos vs {len(self.product_ids)} IDs")
            return False
            
        if self.product_vectors.shape[0] != len(self.product_data):
            logger.error(f"Inconsistencia: {self.product_vectors.shape[0]} vectores vs {len(self.product_data)} productos")
            return False
            
        logger.info("Estado del recomendador validado correctamente")
        return True
    
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
            
            # Actualizar metadatos
            self.model_metadata.update({
                "created_at": datetime.now().isoformat(),
                "products_count": len(products),
                "features_count": self.vectorizer.get_feature_names_out().shape[0]
            })
            
            # Marcar como cargado
            self.loaded = True
            
            # Validar estado
            if not self._validate_state():
                logger.error("El estado del recomendador no es válido después del entrenamiento")
                self.loaded = False
                return False
            
            # Guardar modelo si se especificó ruta
            if self.model_path:
                success = self._save_model()
                if not success:
                    logger.warning("No se pudo guardar el modelo, pero el entrenamiento fue exitoso")
            
            logger.info(f"Recomendador TF-IDF entrenado exitosamente")
            logger.info(f"- Productos: {len(self.product_data)}")
            logger.info(f"- Vectores: {self.product_vectors.shape}")
            logger.info(f"- Características: {self.model_metadata['features_count']}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error entrenando recomendador TF-IDF: {e}")
            self.loaded = False
            return False
    
    def _save_model(self) -> bool:
        """
        Guarda el modelo completo con todos los datos necesarios.
        
        Returns:
            True si se guardó correctamente, False en caso contrario
        """
        try:
            if not self.model_path:
                logger.warning("No se especificó ruta para guardar modelo")
                return False
                
            # Crear directorio si no existe
            model_dir = os.path.dirname(self.model_path)
            if model_dir and not os.path.exists(model_dir):
                os.makedirs(model_dir, exist_ok=True)
            
            # CORRECCIÓN: Guardar TODOS los datos necesarios
            model_data = {
                'version': self.MODEL_VERSION,
                'metadata': self.model_metadata,
                'vectorizer': self.vectorizer,
                'product_vectors': self.product_vectors,
                'product_data': self.product_data,  # ✅ NUEVO: Guardar datos de productos
                'product_ids': self.product_ids,    # ✅ NUEVO: Guardar IDs de productos
                'saved_at': datetime.now().isoformat()
            }
            
            with open(self.model_path, 'wb') as f:
                pickle.dump(model_data, f)
                
            logger.info(f"Modelo TF-IDF completo guardado en {self.model_path}")
            logger.info(f"- Incluye {len(self.product_data)} productos y {len(self.product_ids)} IDs")
            
            return True
            
        except Exception as e:
            logger.error(f"Error guardando modelo TF-IDF: {e}")
            return False
    
    async def load(self, model_path: str = None, force_retrain: bool = False) -> bool:
        """
        Carga un modelo TF-IDF pre-entrenado con validación robusta.
        
        Args:
            model_path: Ruta al archivo de modelo TF-IDF (.pkl)
            force_retrain: Si True, fuerza reentrenamiento incluso si el modelo existe
            
        Returns:
            True si la carga fue exitosa, False en caso contrario
        """
        path = model_path or self.model_path
        
        if not path:
            logger.warning("No se especificó ruta para cargar modelo TF-IDF")
            return False
            
        if force_retrain:
            logger.info("Forzando reentrenamiento del modelo")
            return False
        
        try:
            logger.info(f"Cargando modelo TF-IDF desde {path}")
            
            if not os.path.exists(path):
                logger.info(f"Archivo de modelo no existe: {path}")
                return False
            
            with open(path, 'rb') as f:
                data = pickle.load(f)
            
            # Verificar formato del modelo
            if isinstance(data, dict) and 'version' in data:
                # Formato nuevo (v1.1.0+) con todos los datos
                logger.info(f"Cargando modelo versión {data.get('version', 'unknown')}")
                
                self.vectorizer = data.get('vectorizer')
                self.product_vectors = data.get('product_vectors')
                self.product_data = data.get('product_data')  # ✅ NUEVO: Cargar datos de productos
                self.product_ids = data.get('product_ids')    # ✅ NUEVO: Cargar IDs de productos
                self.model_metadata = data.get('metadata', {})
                
                # Validar que tenemos todos los componentes necesarios
                if self.vectorizer is None or self.product_vectors is None:
                    raise ValueError("Modelo incompleto: faltan vectorizador o vectores")
                    
                if self.product_data is None or self.product_ids is None:
                    raise ValueError("Modelo incompleto: faltan datos de productos o IDs")
                
            else:
                # Formato antiguo (legacy) - solo vectorizador y vectores
                logger.warning("Cargando modelo en formato legacy (sin datos de productos)")
                logger.warning("Se requerirá reentrenamiento para obtener funcionalidad completa")
                
                self.vectorizer = data.get('vectorizer', data) if isinstance(data, dict) else data
                self.product_vectors = data.get('product_vectors') if isinstance(data, dict) else None
                
                if self.product_vectors is None:
                    raise ValueError("Modelo legacy inválido: faltan vectores de productos")
                
                # En formato legacy, no tenemos product_data ni product_ids
                # Marcar para reentrenamiento en próximo uso
                self.product_data = None
                self.product_ids = None
                logger.warning("Modelo legacy cargado - funcionalidad limitada hasta reentrenamiento")
            
            # Marcar como cargado temporalmente para validación
            self.loaded = True
            
            # Validar estado solo si tenemos todos los componentes
            if self.product_data is not None and self.product_ids is not None:
                if not self._validate_state():
                    logger.error("El estado del modelo cargado no es válido")
                    self.loaded = False
                    return False
                    
                logger.info(f"Modelo TF-IDF cargado exitosamente")
                logger.info(f"- Productos: {len(self.product_data)}")
                logger.info(f"- Vectores: {self.product_vectors.shape}")
                logger.info(f"- Características: {self.vectorizer.get_feature_names_out().shape[0]}")
            else:
                logger.warning("Modelo parcialmente cargado - se requiere reentrenamiento para funcionalidad completa")
            
            return True
            
        except Exception as e:
            logger.error(f"Error cargando modelo TF-IDF: {e}")
            logger.info("El modelo será regenerado en el próximo entrenamiento")
            self.loaded = False
            return False
    
    def needs_product_refresh(self) -> bool:
        """
        Determina si se necesita actualizar los datos de productos.
        
        Returns:
            True si se necesita actualización, False en caso contrario
        """
        if not self.loaded:
            return True
            
        if self.product_data is None or self.product_ids is None:
            logger.info("Datos de productos faltantes - se requiere actualización")
            return True
            
        return False
    
    async def refresh_product_data(self, products: List[Dict[str, Any]]) -> bool:
        """
        Actualiza solo los datos de productos manteniendo el modelo TF-IDF entrenado.
        Útil cuando el catálogo de productos cambia pero el modelo sigue siendo válido.
        
        Args:
            products: Nueva lista de productos
            
        Returns:
            True si la actualización fue exitosa, False en caso contrario
        """
        try:
            if not self.loaded or self.vectorizer is None:
                logger.error("No se puede actualizar datos sin un modelo base cargado")
                return False
            
            logger.info(f"Actualizando datos de productos ({len(products)} productos)")
            
            # Verificar si los productos han cambiado significativamente
            new_product_ids = [str(p.get('id', i)) for i, p in enumerate(products)]
            
            if self.product_ids and set(new_product_ids) == set(self.product_ids):
                logger.info("Los productos no han cambiado - manteniendo datos actuales")
                return True
            
            # Actualizar datos de productos
            self.product_data = products
            self.product_ids = new_product_ids
            
            # Verificar consistencia con vectores existentes
            if self.product_vectors is not None and self.product_vectors.shape[0] != len(products):
                logger.warning(f"Inconsistencia detectada: {self.product_vectors.shape[0]} vectores vs {len(products)} productos")
                logger.warning("Se requerirá reentrenamiento completo del modelo")
                return False
            
            # Validar estado después de la actualización
            if not self._validate_state():
                logger.error("El estado no es válido después de actualizar datos de productos")
                return False
            
            # Guardar modelo actualizado
            if self.model_path:
                self._save_model()
            
            logger.info("Datos de productos actualizados exitosamente")
            return True
            
        except Exception as e:
            logger.error(f"Error actualizando datos de productos: {e}")
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
        # Verificar estado completo
        if not self._validate_state():
            logger.error("El recomendador TF-IDF no está en estado válido para generar recomendaciones")
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
                if index < len(self.product_data):  # Verificación adicional
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
        # Verificar estado completo
        if not self._validate_state():
            logger.error("El recomendador TF-IDF no está en estado válido para búsqueda")
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
                if index < len(self.product_data):  # Verificación adicional
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
        
        Args:
            product_id: ID del producto a buscar
            
        Returns:
            Dict con la información del producto, o None si no se encuentra
        """
        if not self.loaded or not self.product_data:
            logger.warning("El recomendador TF-IDF no está cargado o no tiene datos de productos")
            return None
            
        try:
            # Buscar producto por ID
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
        Verifica el estado del recomendador con validación completa.
        
        Returns:
            Diccionario con información detallada de estado
        """
        status = {
            "name": "tfidf_recommender",
            "loaded": self.loaded,
            "fallback_active": self.fallback_active,
            "model_version": self.model_metadata.get("version", "unknown")
        }
        
        # Validación completa del estado
        state_valid = self._validate_state()
        status["state_valid"] = state_valid
        status["status"] = "operational" if state_valid else "unavailable"
        
        if self.loaded:
            status.update({
                "products_count": len(self.product_data) if self.product_data else 0,
                "product_ids_count": len(self.product_ids) if self.product_ids else 0,
                "vectorizer_features": self.vectorizer.get_feature_names_out().shape[0] if self.vectorizer else 0,
                "vectors_shape": list(self.product_vectors.shape) if self.product_vectors is not None else None,
                "model_metadata": self.model_metadata
            })
            
            # Verificar consistencia de datos
            if self.product_data and self.product_ids:
                status["data_consistency"] = {
                    "products_vs_ids": len(self.product_data) == len(self.product_ids),
                    "products_vs_vectors": self.product_vectors.shape[0] == len(self.product_data) if self.product_vectors is not None else False
                }
        
        return status
