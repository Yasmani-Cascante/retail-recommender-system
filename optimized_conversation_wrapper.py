
async def optimized_conversation_wrapper(conversation_request, current_user):
    """Endpoint optimizado dinámico"""
    import time
    from src.api.core.mcp_router_performance_patch import apply_critical_performance_optimization
    
    start_time = time.time()
    
    # Datos mock para testing
    safe_recommendations = [
        {"id": "opt1", "title": "Optimized Product 1", "price": 99.99},
        {"id": "opt2", "title": "Optimized Product 2", "price": 149.99}
    ]
    
    metadata = {"source": "optimized_wrapper", "user": current_user}
    
    # Aplicar optimización crítica
    result = await apply_critical_performance_optimization(
        conversation_request=conversation_request,
        validated_user_id=getattr(conversation_request, 'user_id', 'test_user'),
        validated_product_id=getattr(conversation_request, 'product_id', None),
        safe_recommendations=safe_recommendations,
        metadata=metadata,
        real_session_id=f"opt_session_{int(time.time())}",
        turn_number=1
    )
    
    return result
