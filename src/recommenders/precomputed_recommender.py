
import numpy as np
import json
from sklearn.metrics.pairwise import cosine_similarity
import logging
import os

class PrecomputedEmbeddingRecommender:
    """
    Recomendador que utiliza embeddings pre-computados para generar recomendaciones,
    eliminando la necesidad de cargar modelos de ML en runtime.
    """
    
    def __init__(self, embeddings_dir='embeddings'):
        """
        Inicializa el recomendador con embeddings pre-computados.
        
        Args:
            embeddings_dir: Directorio donde se encuentran los archivos de embeddings
        """
        self.embeddings = None
        self.product_ids = None
        self.product_metadata = None
        self.embeddings_path = os.path.join(embeddings_dir, 'product_embeddings.npy')
        self.product_ids_path = os.path.join(embeddings_dir, 'product_ids.json')
        self.metadata_path = os.path.join(embeddings_dir, 'product_metadata.json')
        
    def fit(self, products=None):
        """
        Carga los embeddings pre-computados y datos asociados.
        El parámetro products se mantiene por compatibilidad con el recomendador original.
        
        Args:
            products: Ignorado, se mantiene por compatibilidad
            
        Returns:
            bool: True si se cargaron correctamente los embeddings, False en caso contrario
        """
        try:
            # Cargar embeddings
            if os.path.exists(self.embeddings_path):
                self.embeddings = np.load(self.embeddings_path)
                logging.info(f"Embeddings cargados: {self.embeddings.shape}")
            else:
                logging.error(f"Archivo de embeddings no encontrado: {self.embeddings_path}")
                return False
                
            # Cargar IDs de productos
            if os.path.exists(self.product_ids_path):
                with open(self.product_ids_path, 'r') as f:
                    self.product_ids = json.load(f)
                logging.info(f"IDs de productos cargados: {len(self.product_ids)}")
            else:
                logging.error(f"Archivo de IDs no encontrado: {self.product_ids_path}")
                return False
                
            # Cargar metadatos de productos
            if os.path.exists(self.metadata_path):
                with open(self.metadata_path, 'r') as f:
                    self.product_metadata = json.load(f)
                logging.info(f"Metadatos de productos cargados: {len(self.product_metadata)}")
            else:
                logging.error(f"Archivo de metadatos no encontrado: {self.metadata_path}")
                return False
                
            return True
            
        except Exception as e:
            logging.error(f"Error cargando embeddings pre-computados: {str(e)}")
            return False
            
    def get_product_by_id(self, product_id):
        """
        Obtiene los metadatos de un producto por su ID.
        
        Args:
            product_id: ID del producto
            
        Returns:
            dict: Metadatos del producto, o None si no se encuentra
        """
        if not self.product_metadata:
            return None
            
        for product in self.product_metadata:
            if str(product.get('id')) == str(product_id):
                return product
                
        return None
    
    def recommend(self, product_id, n_recommendations=5):
        """
        Genera recomendaciones basadas en similitud de embeddings pre-computados.
        
        Args:
            product_id: ID del producto base para las recomendaciones
            n_recommendations: Número de recomendaciones a devolver
            
        Returns:
            list: Lista de diccionarios con los productos recomendados
        """
        if not self.embeddings or not self.product_ids or not self.product_metadata:
            logging.error("Recomendador no inicializado correctamente")
            return []
            
        try:
            # Verificar si el producto existe
            if product_id not in self.product_ids:
                logging.warning(f"Producto no encontrado: {product_id}")
                return []
                
            # Obtener índice del producto
            product_idx = self.product_ids.index(product_id)
            
            # Calcular similitud
            similarities = cosine_similarity(
                [self.embeddings[product_idx]], 
                self.embeddings
            )[0]
            
            # Obtener índices de productos más similares (excluyendo el producto actual)
            similar_indices = np.argsort(similarities)[::-1][1:n_recommendations+1]
            
            # Preparar recomendaciones
            recommendations = []
            for idx in similar_indices:
                product = self.product_metadata[idx]
                recommendations.append({
                    **product,
                    'similarity_score': float(similarities[idx])
                })
                
            return recommendations
                
        except Exception as e:
            logging.error(f"Error generando recomendaciones: {str(e)}")
            return []
