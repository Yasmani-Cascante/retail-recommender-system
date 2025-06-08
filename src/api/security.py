"""
Módulo de seguridad mejorado para el sistema de recomendaciones.

Este módulo proporciona funciones de autenticación y autorización
robustas con manejo mejorado de errores.
"""

from fastapi import Security, HTTPException, Depends
from fastapi.security.api_key import APIKeyHeader
from typing import Optional
import os
import logging
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configurar logging
logger = logging.getLogger(__name__)

# Configurar API Key
API_KEY = os.getenv("API_KEY", "default_key")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """
    Verifica la API Key proporcionada en el header.
    
    Args:
        api_key: API Key del header X-API-Key
        
    Returns:
        str: API Key válida
        
    Raises:
        HTTPException: Si la API Key no es válida o está ausente
    """
    # Verificar si la API Key está presente
    if api_key is None:
        logger.warning("Intento de acceso sin API Key")
        raise HTTPException(
            status_code=403,
            detail="API Key no proporcionada. Incluye el header 'X-API-Key' en tu solicitud."
        )
    
    # Verificar si la API Key es válida
    if api_key != API_KEY:
        logger.warning(f"Intento de acceso con API Key inválida: {api_key[:10]}...")
        raise HTTPException(
            status_code=403,
            detail="API Key inválida. Verifica que estés usando la API Key correcta."
        )
    
    logger.debug("API Key validada correctamente")
    return api_key

async def get_current_user(api_key: str = Depends(get_api_key)) -> str:
    """
    Obtiene el usuario actual basado en la API Key válida.
    
    Args:
        api_key: API Key validada
        
    Returns:
        str: Identificador del usuario autenticado
        
    Raises:
        HTTPException: Si hay un error en la autenticación
    """
    try:
        # En un sistema real, aquí buscarías información del usuario
        # basándote en la API Key en una base de datos
        
        # Para este sistema, simplemente verificamos que la API Key sea válida
        # y devolvemos un usuario genérico
        user_id = "authenticated_user"
        
        logger.debug(f"Usuario autenticado: {user_id}")
        return user_id
        
    except Exception as e:
        logger.error(f"Error en autenticación: {str(e)}")
        raise HTTPException(
            status_code=403,
            detail="Error de autenticación. Por favor, intenta de nuevo."
        )

def verify_api_key(api_key: str) -> bool:
    """
    Función auxiliar para verificar una API Key sin lanzar excepciones.
    
    Args:
        api_key: API Key a verificar
        
    Returns:
        bool: True si la API Key es válida, False en caso contrario
    """
    if not api_key:
        return False
    return api_key == API_KEY

# Función para obtener la API Key válida para el entorno actual
def get_valid_api_key() -> str:
    """
    Obtiene la API Key válida para el entorno actual.
    
    Returns:
        str: API Key válida
    """
    return API_KEY

# Decorador opcional para endpoints que requieren autenticación
def require_authentication(func):
    """
    Decorador que asegura que un endpoint requiere autenticación.
    
    Args:
        func: Función del endpoint a proteger
        
    Returns:
        Función decorada que requiere autenticación
    """
    async def wrapper(*args, **kwargs):
        # El parámetro current_user debe estar presente en los kwargs
        if 'current_user' not in kwargs:
            raise HTTPException(
                status_code=500,
                detail="Error de configuración: endpoint protegido sin autenticación"
            )
        return await func(*args, **kwargs)
    return wrapper

# Función para verificar permisos específicos (para futuro uso)
def check_permission(permission: str):
    """
    Función para verificar permisos específicos.
    
    Args:
        permission: Permiso a verificar
        
    Returns:
        Función que verifica el permiso
    """
    def permission_checker(current_user: str = Depends(get_current_user)):
        # En un sistema real, aquí verificarías los permisos del usuario
        # Por ahora, simplemente verificamos que el usuario esté autenticado
        if not current_user:
            raise HTTPException(
                status_code=403,
                detail=f"No tienes permisos para: {permission}"
            )
        return current_user
    return permission_checker
