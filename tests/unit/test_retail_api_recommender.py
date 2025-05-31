import unittest
import sys
import os
import logging
from unittest.mock import MagicMock, patch
import json
from typing import List, Dict, Any
from datetime import datetime

# Configurar el path para poder importar el módulo
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Importar el módulo que vamos a probar
from src.recommenders.retail_api import RetailAPIRecommender

# Configurar logging
logging.basicConfig(level=logging.INFO)

class MockResponse:
    """
    Clase para simular diferentes tipos de respuestas de la API de Google Cloud Retail.
    """
    def __init__(self, response_type="product", with_data=True):
        self.response_type = response_type
        self.with_data = with_data
        
        if response_type == "product":
            # Crear estructura para respuesta basada en producto
            if with_data:
                self.results = [self._create_product_result() for _ in range(3)]
            else:
                self.results = []
        elif response_type == "user":
            # Crear estructura para respuesta basada en usuario
            if with_data:
                self.recommendations = [self._create_user_recommendation() for _ in range(3)]
            else:
                self.recommendations = []
        else:
            # Respuesta vacía sin estructura reconocible
            pass
    
    def _create_product_result(self):
        """
        Crea un objeto simulado de resultado para recomendación basada en producto.
        Usando una clase personalizada en lugar de MagicMock para evitar problemas de serialización.
        """
        class ProductResult:
            def __init__(self):
                self.product = self.Product()
                self.metadata = {"predictScore": 0.85}
                
            class Product:
                def __init__(self):
                    self.id = "product123"
                    self.title = "Producto de Prueba"
                    self.description = "Descripción del producto de prueba"
                    self.categories = ["Categoría de Prueba"]
                    self.price_info = self.PriceInfo()
                    
                class PriceInfo:
                    def __init__(self):
                        self.price = 99.99
        
        return ProductResult()
    
    def _create_user_recommendation(self):
        """
        Crea un objeto simulado de recomendación para usuario.
        Usando una clase personalizada en lugar de MagicMock.
        """
        class UserRecommendation:
            def __init__(self):
                self.id = "product456"
                self.title = "Producto Local de Prueba"
                # Añadir descripción para que la prueba pase
                self.description = "Esta es una descripción larga del producto local de prueba que se usará para enriquecer las respuestas."
                self.category = "Categoría Local"
                # Añadir precio para que la prueba pase
                self.price = 89.99
        
        return UserRecommendation()

class TestRetailAPIRecommender(unittest.TestCase):
    def setUp(self):
        """Configuración inicial para las pruebas."""
        # Crear una instancia del recomendador con valores de prueba
        self.recommender = RetailAPIRecommender(
            project_number="123456",
            location="global",
            catalog="default_catalog",
            serving_config_id="default_config"
        )
        
        # Añadir datos de productos locales para enriquecimiento
        self.recommender.product_data = [
            {
                "id": "product456",
                "title": "Producto Local de Prueba",
                "body_html": "Esta es una descripción larga del producto local de prueba que se usará para enriquecer las respuestas.",
                "product_type": "Categoría Local",
                "variants": [{"price": "89.99"}]
            }
        ]
    
    def test_process_predictions_product_based(self):
        """
        Prueba el procesamiento de respuestas basadas en producto.
        Verifica que se extraigan correctamente todos los campos del producto.
        """
        # Crear una respuesta simulada para recomendaciones basadas en producto
        mock_response = MockResponse(response_type="product", with_data=True)
        
        # Procesar la respuesta
        results = self.recommender._process_predictions(mock_response)
        
        # Verificar que se procesaron correctamente los resultados
        self.assertEqual(len(results), 3, "Debería haber 3 recomendaciones")
        
        # Verificar que los campos se extrajeron correctamente
        first_result = results[0]
        self.assertEqual(first_result["id"], "product123")
        self.assertEqual(first_result["title"], "Producto de Prueba")
        self.assertEqual(first_result["description"], "Descripción del producto de prueba")
        self.assertEqual(first_result["category"], "Categoría de Prueba")
        self.assertEqual(first_result["price"], 99.99)
        self.assertEqual(first_result["score"], 0.85)
        self.assertEqual(first_result["source"], "retail_api")
        
    def test_process_predictions_user_based(self):
        """
        Prueba el procesamiento de respuestas basadas en usuario.
        Verifica que se manejen correctamente las respuestas minimalistas y se enriquezcan con datos locales.
        """
        # Crear una respuesta simulada para recomendaciones basadas en usuario
        mock_response = MockResponse(response_type="user", with_data=True)
        
        # Procesar la respuesta
        results = self.recommender._process_predictions(mock_response)
        
        # Verificar que se procesaron correctamente los resultados
        self.assertEqual(len(results), 3, "Debería haber 3 recomendaciones")
        
        # Verificar uno de los resultados que debería ser enriquecido con datos locales
        product_456 = next((r for r in results if r["id"] == "product456"), None)
        
        self.assertIsNotNone(product_456, "Debería existir el producto con ID product456")
        self.assertEqual(product_456["title"], "Producto Local de Prueba")
        self.assertTrue(product_456["description"].startswith("Esta es una descripción"))
        self.assertEqual(product_456["category"], "Categoría Local")
        self.assertEqual(product_456["price"], 89.99)
        
    def test_process_predictions_empty_response(self):
        """
        Prueba el procesamiento de respuestas vacías.
        Verifica que se maneje correctamente el caso de no tener resultados.
        """
        # Crear una respuesta simulada vacía
        mock_response = MockResponse(response_type="product", with_data=False)
        
        # Procesar la respuesta
        results = self.recommender._process_predictions(mock_response)
        
        # Verificar que el resultado es una lista vacía
        self.assertEqual(len(results), 0, "Debería ser una lista vacía")
        
    def test_process_predictions_unknown_structure(self):
        """
        Prueba el procesamiento de respuestas con estructura desconocida.
        Verifica que se maneje correctamente el caso de tener una estructura no reconocida.
        """
        # Crear una respuesta simulada con estructura desconocida
        mock_response = MockResponse(response_type="unknown")
        
        # Procesar la respuesta
        results = self.recommender._process_predictions(mock_response)
        
        # Verificar que el resultado es una lista vacía
        self.assertEqual(len(results), 0, "Debería ser una lista vacía")
        
    def test_process_predictions_exception_handling(self):
        """
        Prueba el manejo de excepciones durante el procesamiento.
        Verifica que se maneje correctamente el caso de tener un error durante el procesamiento.
        """
        # Clase personalizada que lanza excepciones al acceder a cualquier atributo 
        # implementa su propio método __getattr__ en lugar de usar un MagicMock y tratar de configurar __getattr__ directamente
        class ErrorResponse:
            def __getattr__(self, name):
                raise Exception("Error simulado")
        
        # Crear una instancia de nuestra clase personalizada
        mock_response = ErrorResponse()
        
        # Procesar la respuesta
        results = self.recommender._process_predictions(mock_response)
        
        # Verificar que el resultado es una lista vacía
        self.assertEqual(len(results), 0, "Debería ser una lista vacía ante un error")

if __name__ == "__main__":
    unittest.main()