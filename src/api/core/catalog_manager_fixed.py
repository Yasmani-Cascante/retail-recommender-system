# src/api/core/catalog_manager_fixed.py
"""
Stub implementation de CatalogManager para compatibilidad legacy.
Este archivo resuelve los warnings de CatalogManager no disponible.
"""

import logging

logger = logging.getLogger(__name__)

class CatalogManager:
    """
    Implementación stub de CatalogManager para compatibilidad.
    En el futuro, esto debería ser refactorizado completamente.
    """
    
    def __init__(self, retail_api_client=None):
        self.retail_api_client = retail_api_client
        self.initialized = True
        logger.info("CatalogManager stub inicializado para compatibilidad")
    
    async def ensure_catalog_structure(self):
        """Stub method para asegurar estructura del catálogo"""
        logger.info("CatalogManager stub: ensure_catalog_structure called")
        if self.retail_api_client:
            try:
                await self.retail_api_client.ensure_catalog_branches()
                return True
            except Exception as e:
                logger.warning(f"Error en ensure_catalog_structure: {e}")
                return False
        return True
    
    async def verify_branches(self):
        """Stub method para verificar ramas"""
        logger.info("CatalogManager stub: verify_branches called")
        return True
    
    async def create_branch_if_needed(self, branch_name):
        """Stub method para crear rama si es necesario"""
        logger.info(f"CatalogManager stub: create_branch_if_needed called for {branch_name}")
        return True

# Factory function para crear CatalogManager
def create_catalog_manager(retail_api_client=None):
    """
    Factory para crear CatalogManager con el cliente de retail API.
    
    Args:
        retail_api_client: Cliente de Retail API (opcional)
        
    Returns:
        CatalogManager: Instancia configurada
    """
    try:
        return CatalogManager(retail_api_client)
    except Exception as e:
        logger.error(f"Error creando CatalogManager: {e}")
        return None

# Función de compatibilidad para imports legacy
def get_catalog_manager():
    """Función de compatibilidad para código legacy"""
    return create_catalog_manager()
