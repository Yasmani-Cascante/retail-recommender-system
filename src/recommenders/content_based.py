from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

class ContentBasedRecommender:
    def __init__(self):
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.product_embeddings = None
        self.product_ids = None
        self.product_data = None
    
    def fit(self, products):
        """
        Entrena el recomendador con los datos de productos.
        
        Args:
            products (list): Lista de diccionarios con información de productos.
                            Cada diccionario debe tener 'id', 'name', 'description'
        """
        self.product_data = products
        self.product_ids = [p['id'] for p in products]
        descriptions = [f"{p['name']}. {p['description']}" for p in products]
        self.product_embeddings = self.model.encode(descriptions)
        
    def recommend(self, product_id, n_recommendations=5):
        """
        Genera recomendaciones basadas en un producto.
        
        Args:
            product_id: ID del producto base para las recomendaciones
            n_recommendations (int): Número de recomendaciones a devolver
            
        Returns:
            list: Lista de diccionarios con los productos recomendados
        """
        if product_id not in self.product_ids:
            raise ValueError(f"Product ID {product_id} not found")
            
        product_idx = self.product_ids.index(product_id)
        similarities = cosine_similarity(
            [self.product_embeddings[product_idx]], 
            self.product_embeddings
        )[0]
        
        # Obtener índices de productos más similares (excluyendo el producto actual)
        similar_indices = np.argsort(similarities)[::-1][1:n_recommendations+1]
        
        # Devolver productos recomendados con sus scores de similitud
        recommendations = [
            {
                **self.product_data[idx],
                'similarity_score': float(similarities[idx])
            }
            for idx in similar_indices
        ]
        
        return recommendations