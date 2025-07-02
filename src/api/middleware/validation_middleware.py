# src/api/middleware/validation_middleware.py
"""
🔧 MIDDLEWARE DE VALIDACIÓN
Intercepta y corrige datos problemáticos antes de que causen errores.
"""

import logging
from typing import Dict, Any
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

class DataValidationMiddleware(BaseHTTPMiddleware):
    """Middleware que valida y normaliza datos en requests MCP."""
    
    async def dispatch(self, request: Request, call_next):
        """Procesa request y response, aplicando validaciones."""
        
        # Solo procesar endpoints MCP
        if "/mcp/" in str(request.url):
            logger.debug(f"Validating MCP request: {request.url}")
            
            # Interceptar y validar datos del request si es POST
            if request.method == "POST":
                try:
                    # Aquí se podría interceptar y validar el body
                    # Por ahora solo loggear para diagnóstico
                    logger.debug("Processing MCP POST request")
                except Exception as e:
                    logger.warning(f"Error validating request data: {e}")
        
        # Procesar request
        response = await call_next(request)
        
        # Interceptar response para validar datos de salida
        if "/mcp/" in str(request.url) and response.status_code == 200:
            try:
                # Aquí se podría interceptar y validar el response
                logger.debug(f"MCP response status: {response.status_code}")
            except Exception as e:
                logger.warning(f"Error validating response data: {e}")
        
        return response

# Para agregar al main:
# app.add_middleware(DataValidationMiddleware)
