
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import logging
import json
import os
from typing import List, Dict, Optional

class SimpleTFIDFRecommender:
    """
    Recomendador simple basado en TF-IDF, que no requiere modelos pre-entrenados.
    Esta implementación es más ligera y evita problemas de incompatibilidad con NumPy
    y otras dependencias.
    """
    
    def __init__(self):
        """Inicializa el recomendador con valores por defecto."""
        self.vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words='english',
            ngram_range=(1, 2),
            min_df=2,
            max_df=0.85
        )
        self.tfidf_matrix = None
        self.product_ids = None
        self.product_data = None
    
    def fit(self, products: List[Dict]):
        """
        Entrena el recomendador con datos de productos.
        
        Args:
            products: Lista de productos (diccionarios)
        
        Returns:
            bool: True si el entrenamiento fue exitoso, False en caso contrario
        """
        try:
            logging.info(f"Entrenando recomendador TF-IDF con {len(products)} productos")
            
            # Guardar productos e IDs
            self.product_data = products
            self.product_ids = [str(p.get('id', '')) for p in products]
            
            # Preparar textos para vectorizar
            texts = []
            for product in products:
                # Combinar título y descripción
                title = product.get('title', '')
                description = product.get('body_html', product.get('description', ''))
                
                # Limpiar HTML básico (simplificado)
                description = description.replace('<p>', ' ').replace('</p>', ' ')
                description = description.replace('<br>', ' ').replace('<br/>', ' ')
                
                # Combinar texto
                text = f"{title}. {description}"
                texts.append(text)
            
            # Vectorizar textos
            self.tfidf_matrix = self.vectorizer.fit_transform(texts)
            
            logging.info(f"Recomendador TF-IDF entrenado correctamente. Matriz: {self.tfidf_matrix.shape}")
            return True
            
        except Exception as e:
            logging.error(f"Error entrenando recomendador TF-IDF: {str(e)}")
            return False
    
    def get_product_by_id(self, product_id: str) -> Optional[Dict]:
        """
        Obtiene un producto por su ID.
        
        Args:
            product_id: ID del producto
            
        Returns:
            Dict o None: Diccionario con datos del producto, o None si no se encuentra
        """
        if not self.product_data or not self.product_ids:
            return None
            
        try:
            idx = self.product_ids.index(str(product_id))
            return self.product_data[idx]
        except (ValueError, IndexError):
            return None
    
    def recommend(self, product_id: str, n_recommendations: int = 5) -> List[Dict]:
        """
        Genera recomendaciones basadas en un producto usando similitud TF-IDF.
        
        Args:
            product_id: ID del producto base
            n_recommendations: Número de recomendaciones a devolver
            
        Returns:
            List[Dict]: Lista de productos recomendados
        """
        if not self.tfidf_matrix or not self.product_ids or not self.product_data:
            logging.error("Recomendador no inicializado correctamente")
            return []
            
        try:
            # Verificar si existe el producto
            if product_id not in self.product_ids:
                logging.warning(f"Producto no encontrado: {product_id}")
                return []
                
            # Obtener índice del producto
            product_idx = self.product_ids.index(product_id)
            
            # Calcular similitud coseno
            product_vector = self.tfidf_matrix[product_idx:product_idx+1]
            similarities = cosine_similarity(product_vector, self.tfidf_matrix)[0]
            
            # Obtener índices de productos más similares (excluyendo el producto actual)
            similar_indices = np.argsort(similarities)[::-1][1:n_recommendations+1]
            
            # Preparar recomendaciones
            recommendations = []
            for idx in similar_indices:
                product = self.product_data[idx]
                
                # Extraer precio si está disponible
                price = 0.0
                if product.get("variants") and len(product["variants"]) > 0:
                    price_str = product["variants"][0].get("price", "0")
                    try:
                        price = float(price_str)
                    except (ValueError, TypeError):
                        price = 0.0
                
                # Crear objeto de recomendación
                recommendations.append({
                    "id": str(product.get("id", "")),
                    "title": product.get("title", ""),
                    "description": product.get("body_html", product.get("description", "")),
                    "price": price,
                    "category": product.get("product_type", ""),
                    "similarity_score": float(similarities[idx]),
                    "recommendation_type": "tfidf"
                })
                
            return recommendations
                
        except Exception as e:
            logging.error(f"Error generando recomendaciones: {str(e)}")
            return []
    
    def save(self, directory: str = 'models'):
        """
        Guarda el modelo para uso posterior (no implementado).
        Esta función está aquí para mantener la compatibilidad con la interfaz,
        pero en esta versión simplificada no se implementa la persistencia.
        """
        logging.warning("La función save() no está implementada en esta versión simplificada")
        return False
    
    def load(self, directory: str = 'models'):
        """
        Carga el modelo guardado (no implementado).
        Esta función está aquí para mantener la compatibilidad con la interfaz,
        pero en esta versión simplificada no se implementa la persistencia.
        """
        logging.warning("La función load() no está implementada en esta versión simplificada")
        return False
