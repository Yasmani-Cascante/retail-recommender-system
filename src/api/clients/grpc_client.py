
import grpc
import os
import logging
import asyncio
import time
from typing import List, Dict, Optional

# Importar clases generadas por protobuf
# Nota: Asumimos que los archivos generados están en la raíz del proyecto
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import recommendation_service_pb2
import recommendation_service_pb2_grpc

class RecommendationClient:
    """
    Cliente gRPC para el servicio de recomendaciones.
    Implementa el patrón Singleton para asegurar una única instancia en toda la aplicación.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RecommendationClient, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance
    
    def __init__(self):
        if not self.initialized:
            # Inicialización diferida para permitir que sea creado antes de uso
            self.server_address = None
            self.channel = None
            self.stub = None
            self.initialized = True
            self.is_connected = False
            self.connection_errors = 0
            self.last_connection_attempt = 0
            self.stats = {
                "requests": 0,
                "errors": 0,
                "last_error": None
            }
            logging.info("Cliente gRPC inicializado (conexión diferida)")
            
    async def connect(self, force=False):
        """
        Conecta al servidor gRPC si no está conectado o si force=True.
        
        Args:
            force: Forzar nueva conexión incluso si ya está conectado
            
        Returns:
            bool: True si la conexión fue exitosa, False en caso contrario
        """
        # Si ya está conectado y no se fuerza nueva conexión, no hacer nada
        if self.is_connected and not force:
            return True
            
        # Si ha habido muchos errores recientemente, limitar los reintentos
        current_time = time.time()
        if self.connection_errors > 3 and current_time - self.last_connection_attempt < 60:
            logging.warning("Demasiados errores de conexión recientes, esperando antes de reintentar")
            return False
            
        # Obtener dirección del servidor
        self.server_address = os.getenv("GRPC_SERVER", "localhost:50051")
        
        try:
            # Cerrar canal existente si lo hay
            if self.channel:
                await self.channel.close()
                
            # Crear nuevo canal y stub
            self.channel = grpc.aio.insecure_channel(self.server_address)
            self.stub = recommendation_service_pb2_grpc.RecommendationServiceStub(self.channel)
            
            # Verificar conexión con una solicitud simple y timeout bajo
            request = recommendation_service_pb2.ProductRequest(
                product_id="test",
                count=1
            )
            
            # Usar un timeout corto para no bloquear demasiado tiempo
            await self.stub.GetContentBasedRecommendations(
                request, timeout=2
            )
            
            self.is_connected = True
            self.connection_errors = 0
            logging.info(f"✅ Cliente gRPC conectado a {self.server_address}")
            return True
            
        except Exception as e:
            self.is_connected = False
            self.connection_errors += 1
            self.last_connection_attempt = current_time
            self.stats["last_error"] = str(e)
            logging.error(f"❌ Error conectando al servidor gRPC ({self.server_address}): {str(e)}")
            return False
    
    def _proto_to_dict(self, product):
        """
        Convierte un producto proto a diccionario.
        
        Args:
            product: Producto en formato proto
            
        Returns:
            dict: Producto en formato diccionario
        """
        return {
            "id": product.id,
            "title": product.title,
            "description": product.description,
            "price": product.price,
            "category": product.category,
            "score": product.score,
            "recommendation_type": product.recommendation_type
        }
    
    async def get_content_recommendations(self, product_id: str, count: int = 5) -> Dict:
        """
        Obtiene recomendaciones basadas en contenido a través de gRPC.
        
        Args:
            product_id: ID del producto base para recomendaciones
            count: Número de recomendaciones a devolver
            
        Returns:
            Dict: Resultado con recomendaciones o error
        """
        self.stats["requests"] += 1
        
        # Intentar conectar si no está conectado
        if not self.is_connected:
            connected = await self.connect()
            if not connected:
                self.stats["errors"] += 1
                return {
                    "product_id": product_id,
                    "recommendations": [],
                    "count": 0,
                    "status": "error",
                    "error": "No se pudo conectar al servidor gRPC"
                }
        
        try:
            # Aplicar valor predeterminado si es necesario
            if count <= 0:
                count = 5
                
            request = recommendation_service_pb2.ProductRequest(
                product_id=product_id,
                count=count
            )
            
            response = await self.stub.GetContentBasedRecommendations(request)
            
            return {
                "product_id": response.product_id,
                "recommendations": [self._proto_to_dict(p) for p in response.recommendations],
                "count": response.count,
                "status": response.status,
                "error": response.error,
                "source": "grpc"
            }
        except Exception as e:
            self.stats["errors"] += 1
            self.is_connected = False  # Marcar como desconectado para reintentar en la próxima solicitud
            logging.error(f"Error en get_content_recommendations via gRPC: {str(e)}")
            return {
                "product_id": product_id,
                "recommendations": [],
                "count": 0,
                "status": "error",
                "error": str(e),
                "source": "error"
            }
            
    async def get_retail_recommendations(
        self, user_id: str, product_id: Optional[str] = None, count: int = 5
    ) -> Dict:
        """
        Obtiene recomendaciones de Retail API a través de gRPC.
        
        Args:
            user_id: ID del usuario
            product_id: ID del producto (opcional)
            count: Número de recomendaciones a devolver
            
        Returns:
            Dict: Resultado con recomendaciones o error
        """
        self.stats["requests"] += 1
        
        # Intentar conectar si no está conectado
        if not self.is_connected:
            connected = await self.connect()
            if not connected:
                self.stats["errors"] += 1
                return {
                    "product_id": product_id if product_id else "",
                    "recommendations": [],
                    "count": 0,
                    "status": "error",
                    "error": "No se pudo conectar al servidor gRPC"
                }
        
        try:
            # Aplicar valor predeterminado si es necesario
            if count <= 0:
                count = 5
                
            request = recommendation_service_pb2.UserProductRequest(
                user_id=user_id,
                product_id=product_id if product_id else "",
                count=count
            )
            
            response = await self.stub.GetRetailRecommendations(request)
            
            return {
                "product_id": response.product_id,
                "recommendations": [self._proto_to_dict(p) for p in response.recommendations],
                "count": response.count,
                "status": response.status,
                "error": response.error,
                "source": "grpc"
            }
        except Exception as e:
            self.stats["errors"] += 1
            self.is_connected = False  # Marcar como desconectado para reintentar en la próxima solicitud
            logging.error(f"Error en get_retail_recommendations via gRPC: {str(e)}")
            return {
                "product_id": product_id if product_id else "",
                "recommendations": [],
                "count": 0,
                "status": "error",
                "error": str(e),
                "source": "error"
            }
            
    async def get_hybrid_recommendations(
        self, user_id: str, product_id: Optional[str] = None, 
        count: int = 5, content_weight: float = 0.5
    ) -> Dict:
        """
        Obtiene recomendaciones híbridas a través de gRPC.
        
        Args:
            user_id: ID del usuario
            product_id: ID del producto (opcional)
            count: Número de recomendaciones a devolver
            content_weight: Peso para recomendaciones basadas en contenido (0-1)
            
        Returns:
            Dict: Resultado con recomendaciones o error
        """
        self.stats["requests"] += 1
        
        # Intentar conectar si no está conectado
        if not self.is_connected:
            connected = await self.connect()
            if not connected:
                self.stats["errors"] += 1
                return {
                    "product_id": product_id if product_id else "",
                    "recommendations": [],
                    "count": 0,
                    "status": "error",
                    "error": "No se pudo conectar al servidor gRPC"
                }
        
        try:
            # Aplicar valores predeterminados si es necesario
            if count <= 0:
                count = 5
            if content_weight < 0 or content_weight > 1:
                content_weight = 0.5
                
            request = recommendation_service_pb2.UserProductRequest(
                user_id=user_id,
                product_id=product_id if product_id else "",
                count=count,
                content_weight=content_weight
            )
            
            response = await self.stub.GetHybridRecommendations(request)
            
            return {
                "product_id": response.product_id,
                "recommendations": [self._proto_to_dict(p) for p in response.recommendations],
                "count": response.count,
                "status": response.status,
                "error": response.error,
                "source": "grpc"
            }
        except Exception as e:
            self.stats["errors"] += 1
            self.is_connected = False  # Marcar como desconectado para reintentar en la próxima solicitud
            logging.error(f"Error en get_hybrid_recommendations via gRPC: {str(e)}")
            return {
                "product_id": product_id if product_id else "",
                "recommendations": [],
                "count": 0,
                "status": "error",
                "error": str(e),
                "source": "error"
            }
            
    async def record_user_event(
        self, user_id: str, event_type: str, product_id: Optional[str] = None
    ) -> Dict:
        """
        Registra eventos de usuario a través de gRPC.
        
        Args:
            user_id: ID del usuario
            event_type: Tipo de evento
            product_id: ID del producto (opcional)
            
        Returns:
            Dict: Resultado del registro de evento
        """
        self.stats["requests"] += 1
        
        # Intentar conectar si no está conectado
        if not self.is_connected:
            connected = await self.connect()
            if not connected:
                self.stats["errors"] += 1
                return {
                    "status": "error",
                    "message": "",
                    "error": "No se pudo conectar al servidor gRPC"
                }
        
        try:
            request = recommendation_service_pb2.UserEventRequest(
                user_id=user_id,
                event_type=event_type,
                product_id=product_id if product_id else ""
            )
            
            response = await self.stub.RecordUserEvent(request)
            
            return {
                "status": response.status,
                "message": response.message,
                "error": response.error
            }
        except Exception as e:
            self.stats["errors"] += 1
            self.is_connected = False  # Marcar como desconectado para reintentar en la próxima solicitud
            logging.error(f"Error en record_user_event via gRPC: {str(e)}")
            return {
                "status": "error",
                "message": "",
                "error": str(e)
            }
    
    async def get_stats(self) -> Dict:
        """
        Obtiene estadísticas del cliente gRPC.
        
        Returns:
            Dict: Estadísticas de uso del cliente
        """
        return {
            **self.stats,
            "is_connected": self.is_connected,
            "server_address": self.server_address,
            "connection_errors": self.connection_errors,
            "hit_ratio": (self.stats["requests"] - self.stats["errors"]) / self.stats["requests"] * 100 if self.stats["requests"] > 0 else 0
        }
