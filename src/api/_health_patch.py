            shutdown_at = await _get_shutdown_at()
            return {
                "timestamp": time.time(),
                "service": "enterprise_retail_recommender",
                "version": "2.1.0-FIXED",
                "status": "healthy",
                "startup_phase": "complete",
                "redis_status": "initializing" if not redis_initialized and redis_error is None else ("ready" if redis_initialized else "failed"),
                "redis_error": redis_error,
                "lifespan_pattern": "modern_contextmanager",
                "shutdown_at": shutdown_at,
                # ── VISUAL SEARCH FLAG ─────────────────────────────────────────────
                # Expuesto en /health para que el frontend (ChatWidget) pueda leer
                # el estado del flag en el health check que ya hace al abrir el chat.
                # Esto evita que el botón de cámara aparezca cuando el flag está off.
                # os.environ.get() siempre refleja el valor actual en Cloud Run —
                # no usa lru_cache para evitar el freeze al import time.
                "visual_search_enabled": os.environ.get('VISUAL_SEARCH_ENABLED', 'false').lower() == 'true',
            }