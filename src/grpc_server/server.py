
import grpc
import logging
import time
import asyncio
from concurrent import futures
import os
import sys

# Ajustar path para importaciones
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Importar clases generadas por protobuf
import recommendation_service_pb2
import recommendation_service_pb2_grpc

# Importar recomendadores
from src.recommenders.precomputed_recommender import PrecomputedEmbeddingRecommender
from src.recommenders.retail_api import RetailAPIRecommender

class RecommendationServicer(recommendation_service_pb2_grpc.RecommendationServiceServicer):
    """
    Implementación del servicio gRPC para recomendaciones.
    """
    
    def __init__(self):
        # Inicializar el recomendador precomputado
        self.content_recommender = PrecomputedEmbeddingRecommender()
        logging.info("Inicializando recomendador con embeddings precomputados...")
        success = self.content_recommender.fit()
        if success:
            logging.info("✅ Recomendador precomputado inicializado correctamente")
        else:
            logging.error("❌ Error inicializando recomendador precomputado")
        
        # Inicializar Retail API Recommender si hay configuración
        project_number = os.getenv("GCP_PROJECT_NUMBER")
        location = os.getenv("GCP_LOCATION", "global")
        catalog = os.getenv("RETAIL_CATALOG", "default_catalog")
        serving_config = os.getenv("RETAIL_SERVING_CONFIG", "default_config")
        
        # Solo inicializar si hay configuración
        if project_number:
            try:
                self.retail_recommender = RetailAPIRecommender(
                    project_number=project_number,
                    location=location,
                    catalog=catalog,
                    serving_config_id=serving_config
                )
                logging.info("✅ RetailAPIRecommender inicializado correctamente")
            except Exception as e:
                logging.error(f"❌ Error inicializando RetailAPIRecommender: {str(e)}")
                self.retail_recommender = None
        else:
            logging.warning("⚠️ GCP_PROJECT_NUMBER no configurado. RetailAPIRecommender deshabilitado.")
            self.retail_recommender = None
            
        # Estadísticas para monitoreo
        self.stats = {
            "start_time": time.time(),
            "requests": {
                "content": 0,
                "retail": 0,
                "hybrid": 0,
                "events": 0
            },
            "errors": {
                "content": 0,
                "retail": 0,
                "hybrid": 0,
                "events": 0
            }
        }
        
    def _product_to_proto(self, product):
        """
        Convierte un producto en formato de diccionario a mensaje proto.
        
        Args:
            product: Producto en formato de diccionario
            
        Returns:
            Product: Producto en formato proto
        """
        return recommendation_service_pb2.Product(
            id=str(product.get("id", "")),
            title=product.get("title", ""),
            description=product.get("description", ""),
            price=float(product.get("price", 0.0)),
            category=product.get("category", ""),
            score=float(product.get("similarity_score", product.get("score", 0.0))),
            recommendation_type=product.get("recommendation_type", "content")
        )
        
    def GetContentBasedRecommendations(self, request, context):
        """
        Implementación del método RPC para obtener recomendaciones basadas en contenido.
        
        Args:
            request: Solicitud con product_id y count
            context: Contexto gRPC
            
        Returns:
            RecommendationsResponse: Respuesta con recomendaciones
        """
        # Incrementar contador de solicitudes
        self.stats["requests"]["content"] += 1
        
        try:
            product_id = request.product_id
            # Aplicar valor predeterminado si es necesario
            count = request.count if request.count > 0 else 5
            
            # Verificar si el recomendador está inicializado
            if not self.content_recommender.embeddings:
                self.stats["errors"]["content"] += 1
                return recommendation_service_pb2.RecommendationsResponse(
                    product_id=product_id,
                    recommendations=[],
                    count=0,
                    status="error",
                    error="Recomendador no inicializado"
                )
                
            # Obtener recomendaciones
            recommendations = self.content_recommender.recommend(product_id, count)
            
            # Convertir a formato proto
            proto_products = [self._product_to_proto(p) for p in recommendations]
            
            return recommendation_service_pb2.RecommendationsResponse(
                product_id=product_id,
                recommendations=proto_products,
                count=len(proto_products),
                status="success"
            )
        except Exception as e:
            self.stats["errors"]["content"] += 1
            logging.error(f"Error en GetContentBasedRecommendations: {str(e)}")
            return recommendation_service_pb2.RecommendationsResponse(
                product_id=request.product_id,
                recommendations=[],
                count=0,
                status="error",
                error=str(e)
            )
            
    async def get_retail_recommendations(self, user_id, product_id, count):
        """
        Método asíncrono para obtener recomendaciones de Retail API.
        
        Args:
            user_id: ID del usuario
            product_id: ID del producto (opcional)
            count: Número de recomendaciones
            
        Returns:
            list: Lista de productos recomendados
        """
        if not self.retail_recommender:
            return []
            
        try:
            recommendations = await self.retail_recommender.get_recommendations(
                user_id=user_id,
                product_id=product_id if product_id else None,
                n_recommendations=count
            )
            return recommendations
        except Exception as e:
            logging.error(f"Error obteniendo recomendaciones de Retail API: {str(e)}")
            return []
            
    def GetRetailRecommendations(self, request, context):
        """
        Implementación del método RPC para obtener recomendaciones de Retail API.
        
        Args:
            request: Solicitud con user_id, product_id y count
            context: Contexto gRPC
            
        Returns:
            RecommendationsResponse: Respuesta con recomendaciones
        """
        # Incrementar contador de solicitudes
        self.stats["requests"]["retail"] += 1
        
        # Verificar si el recomendador de Retail API está disponible
        if not self.retail_recommender:
            self.stats["errors"]["retail"] += 1
            return recommendation_service_pb2.RecommendationsResponse(
                product_id=request.product_id,
                recommendations=[],
                count=0,
                status="error",
                error="RetailAPIRecommender no disponible"
            )
            
        try:
            # Obtener parámetros de la solicitud
            user_id = request.user_id
            product_id = request.product_id if request.product_id else None
            # Aplicar valor predeterminado si es necesario
            count = request.count if request.count > 0 else 5
            
            # Como gRPC no es asíncrono por defecto, usamos asyncio directamente
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            recommendations = loop.run_until_complete(
                self.get_retail_recommendations(user_id, product_id, count)
            )
            loop.close()
            
            # Convertir a formato proto
            proto_products = [self._product_to_proto(p) for p in recommendations]
            
            return recommendation_service_pb2.RecommendationsResponse(
                product_id=request.product_id,
                recommendations=proto_products,
                count=len(proto_products),
                status="success"
            )
        except Exception as e:
            self.stats["errors"]["retail"] += 1
            logging.error(f"Error en GetRetailRecommendations: {str(e)}")
            return recommendation_service_pb2.RecommendationsResponse(
                product_id=request.product_id,
                recommendations=[],
                count=0,
                status="error",
                error=str(e)
            )
            
    def GetHybridRecommendations(self, request, context):
        """
        Implementación del método RPC para obtener recomendaciones híbridas.
        
        Args:
            request: Solicitud con user_id, product_id, count y content_weight
            context: Contexto gRPC
            
        Returns:
            RecommendationsResponse: Respuesta con recomendaciones
        """
        # Incrementar contador de solicitudes
        self.stats["requests"]["hybrid"] += 1
        
        try:
            # Obtener parámetros de la solicitud
            user_id = request.user_id
            product_id = request.product_id if request.product_id else None
            # Aplicar valores predeterminados si es necesario
            count = request.count if request.count > 0 else 5
            content_weight = request.content_weight if 0 <= request.content_weight <= 1 else 0.5
            
            # Verificar que al menos un recomendador esté disponible
            if not self.content_recommender.embeddings and not self.retail_recommender:
                self.stats["errors"]["hybrid"] += 1
                return recommendation_service_pb2.RecommendationsResponse(
                    product_id=product_id or "",
                    recommendations=[],
                    count=0,
                    status="error",
                    error="Ningún recomendador disponible"
                )
                
            # Si no hay product_id o no hay recomendador de contenido, usar solo Retail API
            if not product_id or not self.content_recommender.embeddings:
                if not self.retail_recommender:
                    self.stats["errors"]["hybrid"] += 1
                    return recommendation_service_pb2.RecommendationsResponse(
                        product_id=product_id or "",
                        recommendations=[],
                        count=0,
                        status="error",
                        error="Se requiere product_id para recomendaciones basadas en contenido"
                    )
                    
                # Usar solo Retail API
                return self.GetRetailRecommendations(request, context)
                
            # Si no hay Retail API, usar solo recomendador de contenido
            if not self.retail_recommender:
                product_request = recommendation_service_pb2.ProductRequest(
                    product_id=product_id,
                    count=count
                )
                return self.GetContentBasedRecommendations(product_request, context)
                
            # Si hay ambos recomendadores, combinar recomendaciones
            
            # 1. Obtener recomendaciones basadas en contenido
            content_recommendations = self.content_recommender.recommend(product_id, count)
            
            # 2. Obtener recomendaciones de Retail API
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            retail_recommendations = loop.run_until_complete(
                self.get_retail_recommendations(user_id, product_id, count)
            )
            loop.close()
            
            # 3. Combinar recomendaciones con el peso especificado
            combined_scores = {}
            
            # Procesar recomendaciones basadas en contenido
            for rec in content_recommendations:
                product_id_rec = rec["id"]
                combined_scores[product_id_rec] = {
                    **rec,
                    "final_score": rec.get("similarity_score", 0) * content_weight,
                    "recommendation_type": "hybrid"
                }
                
            # Procesar recomendaciones de Retail API
            for rec in retail_recommendations:
                product_id_rec = rec["id"]
                if product_id_rec in combined_scores:
                    combined_scores[product_id_rec]["final_score"] += (
                        rec.get("score", 0) * (1 - content_weight)
                    )
                else:
                    combined_scores[product_id_rec] = {
                        **rec,
                        "final_score": rec.get("score", 0) * (1 - content_weight),
                        "recommendation_type": "hybrid"
                    }
                    
            # Ordenar por score final y limitar al número solicitado
            sorted_recs = sorted(
                combined_scores.values(),
                key=lambda x: x.get("final_score", 0),
                reverse=True
            )[:count]
            
            # Convertir a formato proto
            proto_products = [self._product_to_proto(p) for p in sorted_recs]
            
            return recommendation_service_pb2.RecommendationsResponse(
                product_id=product_id or "",
                recommendations=proto_products,
                count=len(proto_products),
                status="success"
            )
            
        except Exception as e:
            self.stats["errors"]["hybrid"] += 1
            logging.error(f"Error en GetHybridRecommendations: {str(e)}")
            return recommendation_service_pb2.RecommendationsResponse(
                product_id=request.product_id or "",
                recommendations=[],
                count=0,
                status="error",
                error=str(e)
            )
            
    async def record_user_event_async(self, user_id, event_type, product_id):
        """
        Método asíncrono para registrar eventos de usuario.
        
        Args:
            user_id: ID del usuario
            event_type: Tipo de evento
            product_id: ID del producto (opcional)
            
        Returns:
            dict: Resultado del registro de evento
        """
        if not self.retail_recommender:
            return {"status": "error", "error": "RetailAPIRecommender no disponible"}
            
        try:
            result = await self.retail_recommender.record_user_event(
                user_id=user_id,
                event_type=event_type,
                product_id=product_id
            )
            return result
        except Exception as e:
            logging.error(f"Error registrando evento de usuario: {str(e)}")
            return {"status": "error", "error": str(e)}
            
    def RecordUserEvent(self, request, context):
        """
        Implementación del método RPC para registrar eventos de usuario.
        
        Args:
            request: Solicitud con user_id, event_type y product_id
            context: Contexto gRPC
            
        Returns:
            StatusResponse: Respuesta con estado de la operación
        """
        # Incrementar contador de solicitudes
        self.stats["requests"]["events"] += 1
        
        # Verificar si el recomendador de Retail API está disponible
        if not self.retail_recommender:
            self.stats["errors"]["events"] += 1
            return recommendation_service_pb2.StatusResponse(
                status="error",
                message="",
                error="RetailAPIRecommender no disponible"
            )
            
        try:
            # Obtener parámetros de la solicitud
            user_id = request.user_id
            event_type = request.event_type
            product_id = request.product_id if request.product_id else None
            
            # Registrar evento de forma asíncrona
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.record_user_event_async(user_id, event_type, product_id)
            )
            loop.close()
            
            if result.get("status") == "error":
                self.stats["errors"]["events"] += 1
                
            return recommendation_service_pb2.StatusResponse(
                status=result.get("status", "error"),
                message=result.get("message", ""),
                error=result.get("error", "")
            )
            
        except Exception as e:
            self.stats["errors"]["events"] += 1
            logging.error(f"Error en RecordUserEvent: {str(e)}")
            return recommendation_service_pb2.StatusResponse(
                status="error",
                message="",
                error=str(e)
            )

def serve():
    """
    Inicia el servidor gRPC.
    """
    # Configurar logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Obtener puerto de variables de entorno o usar valor por defecto
    port = int(os.getenv("GRPC_PORT", "50051"))
    
    # Crear servidor gRPC
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    recommendation_service_pb2_grpc.add_RecommendationServiceServicer_to_server(
        RecommendationServicer(), server
    )
    
    # Añadir puerto de escucha
    server.add_insecure_port(f'[::]:{port}')
    
    # Iniciar servidor
    server.start()
    logging.info(f"Servidor gRPC iniciado en puerto {port}")
    
    try:
        # Mantener servidor en ejecución
        server.wait_for_termination()
    except KeyboardInterrupt:
        # Detener servidor al recibir Ctrl+C
        server.stop(0)
        logging.info("Servidor detenido")

if __name__ == "__main__":
    serve()
