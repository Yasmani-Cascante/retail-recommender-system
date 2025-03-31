"""
Implementación simplificada de un recomendador basado en contenido
que no requiere dependencias externas ni modelos preentrenados.
"""
import re
import math
import logging
from typing import List, Dict, Set
from collections import Counter

class SimpleContentRecommender:
    """
    Recomendador basado en contenido simplificado que utiliza TF-IDF 
    y similitud coseno para encontrar productos similares.
    """
    
    def __init__(self):
        self.products = []
        self.product_ids = []
        self.tfidf_vectors = []
        self.corpus_word_counts = Counter()
        self.is_fitted = False
        
    def preprocess_text(self, text: str) -> List[str]:
        """Preprocesa texto para extraer términos significativos."""
        if not text:
            return []
            
        # Convertir a minúsculas y eliminar caracteres no alfanuméricos
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        
        # Tokenizar y filtrar términos cortos
        tokens = [word for word in text.split() if len(word) > 2]
        return tokens
        
    def fit(self, products: List[Dict]):
        """
        Entrena el recomendador con una lista de productos.
        
        Args:
            products: Lista de productos con 'id', 'title', 'description', etc.
        """
        logging.info(f"Entrenando SimpleContentRecommender con {len(products)} productos")
        
        self.products = products
        self.product_ids = [str(p.get('id', '')) for p in products]
        
        # Extraer términos de cada producto
        documents = []
        for product in products:
            title = product.get('title', '')
            description = product.get('description', '')
            text = f"{title} {description}"
            tokens = self.preprocess_text(text)
            documents.append(tokens)
            
            # Actualizar conteo global de términos
            self.corpus_word_counts.update(tokens)
        
        # Número total de documentos
        n_docs = len(documents)
        
        # Calcular vectores TF-IDF
        self.tfidf_vectors = []
        for doc_tokens in documents:
            if not doc_tokens:
                self.tfidf_vectors.append({})
                continue
                
            # Conteo de términos en el documento
            term_counts = Counter(doc_tokens)
            
            # Calcular vector TF-IDF
            tfidf_vector = {}
            for term, count in term_counts.items():
                # Frecuencia de término (TF)
                tf = count / len(doc_tokens)
                
                # Frecuencia inversa de documento (IDF)
                doc_freq = sum(1 for doc in documents if term in doc)
                idf = math.log(n_docs / (1 + doc_freq))
                
                # TF-IDF
                tfidf_vector[term] = tf * idf
                
            self.tfidf_vectors.append(tfidf_vector)
        
        self.is_fitted = True
        logging.info("SimpleContentRecommender entrenado correctamente")
    
    def cosine_similarity(self, vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        """Calcula similitud coseno entre dos vectores."""
        # Asegurar que hay términos en común
        common_terms = set(vec1.keys()) & set(vec2.keys())
        if not common_terms:
            return 0.0
            
        # Calcular productos punto y magnitudes
        dot_product = sum(vec1[term] * vec2[term] for term in common_terms)
        mag1 = math.sqrt(sum(val**2 for val in vec1.values()))
        mag2 = math.sqrt(sum(val**2 for val in vec2.values()))
        
        # Evitar división por cero
        if mag1 == 0 or mag2 == 0:
            return 0.0
            
        return dot_product / (mag1 * mag2)
    
    def recommend(self, product_id: str, n_recommendations: int = 5) -> List[Dict]:
        """
        Genera recomendaciones basadas en un producto.
        
        Args:
            product_id: ID del producto base para recomendaciones
            n_recommendations: Número de recomendaciones a devolver
            
        Returns:
            Lista de productos recomendados
        """
        if not self.is_fitted:
            logging.warning("El recomendador no ha sido entrenado")
            return []
            
        if product_id not in self.product_ids:
            logging.warning(f"Producto {product_id} no encontrado")
            return self.products[:min(n_recommendations, len(self.products))]
            
        # Obtener vector del producto de referencia
        product_idx = self.product_ids.index(product_id)
        product_vector = self.tfidf_vectors[product_idx]
        
        # Calcular similitudes con todos los productos
        similarities = []
        for i, vector in enumerate(self.tfidf_vectors):
            if i == product_idx:  # Saltar el producto de referencia
                continue
                
            sim = self.cosine_similarity(product_vector, vector)
            similarities.append((i, sim))
        
        # Ordenar por similitud (descendente)
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        # Construir lista de recomendaciones
        recommendations = []
        for idx, sim in similarities[:n_recommendations]:
            product = self.products[idx].copy()
            product['similarity_score'] = float(sim)
            recommendations.append(product)
            
        return recommendations
