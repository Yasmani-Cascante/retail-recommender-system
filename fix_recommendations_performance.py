"""
Fix crítico para el problema de performance en endpoint de recomendaciones
========================================================================

PROBLEMA: El endpoint /v1/recommendations/{product_id} está haciendo reload
completo del catálogo Shopify (3062 productos) en cada request, causando
16+ segundos de response time.

SOLUCIÓN: Usar el TF-IDF recommender que ya tiene los productos cargados
y solo usar Shopify como fallback para productos específicos.

Author: Senior Architecture Team
"""

# ANTES (PROBLEMÁTICO - LÍNEAS 1673+):
# if client:
#     all_products = client.get_products()  # ❌ 12+ segundos
#     product = next(
#         (p for p in all_products if str(p.get('id')) == str(product_id)),
#         None
#     )

# DESPUÉS (OPTIMIZADO):

def get_product_optimized(product_id: str, tfidf_recommender, shopify_client):
    """
    Obtener producto de forma optimizada:
    1. Primero buscar en TF-IDF recommender (instantáneo)
    2. Solo usar Shopify si no se encuentra (fallback)
    """
    product = None
    
    # ✅ PASO 1: Buscar en TF-IDF recommender (instantáneo, 3062 productos ya cargados)
    if tfidf_recommender and tfidf_recommender.loaded and tfidf_recommender.product_data:
        for p in tfidf_recommender.product_data:
            if str(p.get('id', '')) == str(product_id):
                product = p
                break
                
        if product:
            logger.info(f"✅ Producto {product_id} encontrado en TF-IDF catalog (0ms)")
            return product
    
    # ✅ PASO 2: Solo si no se encuentra, usar Shopify API para producto individual
    if shopify_client:
        try:
            # Usar get_product_by_id si está disponible (más eficiente)
            if hasattr(shopify_client, 'get_product_by_id'):
                product = shopify_client.get_product_by_id(product_id)
                if product:
                    logger.info(f"✅ Producto {product_id} obtenido de Shopify individual API")
                    return product
            else:
                logger.warning("⚠️ Shopify client no tiene get_product_by_id, usando fallback")
                
        except Exception as e:
            logger.error(f"❌ Error obteniendo producto individual de Shopify: {e}")
    
    # ✅ PASO 3: Si todo falla, buscar en ProductCache
    if product_cache:
        try:
            product = await product_cache.get_product(product_id)
            if product:
                logger.info(f"✅ Producto {product_id} obtenido de ProductCache")
                return product
        except Exception as e:
            logger.error(f"❌ Error obteniendo producto de cache: {e}")
            
    return None

# REEMPLAZO COMPLETO DEL ENDPOINT:

@app.get("/v1/recommendations/{product_id}", response_model=Dict)
async def get_recommendations_fixed(
    product_id: str,
    user_id: Optional[str] = Header(None),
    n: Optional[int] = Query(5, gt=0, le=20),
    content_weight: Optional[float] = Query(0.5, ge=0.0, le=1.0),
    current_user: str = Depends(get_current_user)
):
    """
    ✅ VERSIÓN OPTIMIZADA: Obtiene recomendaciones basadas en un producto.
    
    OPTIMIZACIONES APLICADAS:
    - Usa TF-IDF catalog cargado en memoria (instantáneo)
    - Solo usa Shopify para productos individuales si es necesario
    - Elimina el catalog reload completo (16s → <2s)
    """
    start_processing = time.time()
    
    # Verificar estado de carga
    is_healthy, reason = startup_manager.is_healthy()
    if not is_healthy:
        raise HTTPException(status_code=503, detail=f"Servicio no disponible: {reason}")
    
    try:
        # ✅ OPTIMIZACIÓN CRÍTICA: Actualizar peso sin recargar catálogo
        hybrid_recommender.content_weight = content_weight
        
        # ✅ OPTIMIZACIÓN CRÍTICA: Obtener producto de forma eficiente
        logger.info(f"🔍 Buscando producto {product_id} de forma optimizada...")
        
        product = None
        
        # PASO 1: Buscar en TF-IDF recommender (instantáneo)
        if tfidf_recommender and tfidf_recommender.loaded and tfidf_recommender.product_data:
            for p in tfidf_recommender.product_data:
                if str(p.get('id', '')) == str(product_id):
                    product = p
                    logger.info(f"✅ Producto {product_id} encontrado en TF-IDF catalog (0ms)")
                    break
        
        # PASO 2: Solo si no se encuentra, intentar obtener individualmente
        if not product:
            logger.info(f"🔄 Producto {product_id} no en catálogo, buscando individualmente...")
            
            # Intentar con ProductCache primero
            if product_cache:
                try:
                    product = await product_cache.get_product(product_id)
                    if product:
                        logger.info(f"✅ Producto {product_id} obtenido de ProductCache")
                except Exception as e:
                    logger.warning(f"⚠️ ProductCache error: {e}")
            
            # Si ProductCache no tiene el producto, usar Shopify individual
            if not product:
                client = get_shopify_client()
                if client and hasattr(client, 'get_product_by_id'):
                    try:
                        product = client.get_product_by_id(product_id)
                        if product:
                            logger.info(f"✅ Producto {product_id} obtenido de Shopify individual API")
                    except Exception as e:
                        logger.error(f"❌ Error Shopify individual: {e}")
        
        # Verificar si encontramos el producto
        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Product ID {product_id} not found in any source"
            )
            
        # ✅ OBTENER RECOMENDACIONES (esto ya está optimizado)
        recommendations = await hybrid_recommender.get_recommendations(
            user_id=user_id or "anonymous",
            product_id=str(product_id),
            n_recommendations=n
        )
        
        # Calcular tiempo de procesamiento
        processing_time_ms = (time.time() - start_processing) * 1000
        
        logger.info(f"✅ Recomendaciones obtenidas en {processing_time_ms:.1f}ms")
        
        # Registrar métricas si están habilitadas
        if settings.metrics_enabled and 'recommendation_metrics' in globals():
            from src.api.core.metrics import recommendation_metrics
            recommendation_metrics.record_recommendation_request(
                request_data={
                    "product_id": product_id,
                    "user_id": user_id or "anonymous",
                    "n": n,
                    "content_weight": content_weight
                },
                recommendations=recommendations,
                response_time_ms=processing_time_ms,
                user_id=user_id or "anonymous",
                product_id=product_id
            )
        
        return {
            "product": {
                "id": product.get('id'),
                "title": product.get('title')
            },
            "recommendations": recommendations,
            "metadata": {
                "content_weight": content_weight,
                "total_recommendations": len(recommendations),
                "source": "hybrid_tfidf_redis_optimized",
                "took_ms": processing_time_ms,
                "optimization": "no_catalog_reload"  # ✅ Indicador del fix
            }
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error obteniendo recomendaciones: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# INSTRUCCIONES DE APLICACIÓN:
# 1. Reemplazar la función get_recommendations actual (línea ~1673) con get_recommendations_fixed
# 2. Reiniciar el sistema
# 3. Test: curl "http://localhost:8000/v1/recommendations/9978689487157?n=5"
# 4. Verificar que took_ms < 2000ms en el response
