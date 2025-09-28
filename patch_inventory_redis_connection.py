#!/usr/bin/env python3
"""
Parche para InventoryService - Conexión Redis automática
"""

import sys
sys.path.append('src')

def patch_inventory_service():
    """
    Aplica el parche para manejar conexiones Redis automáticamente
    en InventoryService
    """
    print("🔧 Aplicando parche para InventoryService...")
    
    # Leer archivo actual
    file_path = "src/api/inventory/inventory_service.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Buscar y reemplazar el método _get_cached_inventory
    old_method = '''    async def _get_cached_inventory(self, product_id: str, market_id: str) -> Optional[InventoryInfo]:
        """Obtener información de inventario desde cache"""
        if not self.redis:
            return None
            
        try:
            cache_key = f"{self.CACHE_PREFIX}:{product_id}:{market_id}"
            cached_data = await self.redis.get(cache_key)'''
    
    new_method = '''    async def _get_cached_inventory(self, product_id: str, market_id: str) -> Optional[InventoryInfo]:
        """Obtener información de inventario desde cache"""
        if not self.redis:
            return None
            
        try:
            # ✅ CORREGIDO: Asegurar conexión antes de operación
            if not await self.redis.ensure_connected():
                logger.debug(f"Redis not available for cache read: {product_id}")
                return None
                
            cache_key = f"{self.CACHE_PREFIX}:{product_id}:{market_id}"
            cached_data = await self.redis.get(cache_key)'''
    
    # Buscar y reemplazar el método _cache_inventory_info
    old_cache_method = '''    async def _cache_inventory_info(self, inventory_info: InventoryInfo, market_id: str):
        """Cachear información de inventario"""
        if not self.redis:
            return
            
        try:
            cache_key = f"{self.CACHE_PREFIX}:{inventory_info.product_id}:{market_id}"'''
    
    new_cache_method = '''    async def _cache_inventory_info(self, inventory_info: InventoryInfo, market_id: str):
        """Cachear información de inventario"""
        if not self.redis:
            return
            
        try:
            # ✅ CORREGIDO: Asegurar conexión antes de operación
            if not await self.redis.ensure_connected():
                logger.debug(f"Redis not available for cache write: {inventory_info.product_id}")
                return
                
            cache_key = f"{self.CACHE_PREFIX}:{inventory_info.product_id}:{market_id}"'''
    
    # Aplicar parches
    if old_method in content:
        content = content.replace(old_method, new_method)
        print("✅ Método _get_cached_inventory parcheado")
    else:
        print("⚠️ Método _get_cached_inventory no encontrado o ya parcheado")
    
    if old_cache_method in content:
        content = content.replace(old_cache_method, new_cache_method)
        print("✅ Método _cache_inventory_info parcheado")
    else:
        print("⚠️ Método _cache_inventory_info no encontrado o ya parcheado")
    
    # Hacer backup del archivo original
    import shutil
    backup_path = f"{file_path}.backup_connection_fix"
    shutil.copy2(file_path, backup_path)
    print(f"✅ Backup creado: {backup_path}")
    
    # Escribir archivo parcheado
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Parche aplicado exitosamente")
    print("\n🔧 Cambios realizados:")
    print("   1. _get_cached_inventory: Agregado ensure_connected() antes de redis.get()")
    print("   2. _cache_inventory_info: Agregado ensure_connected() antes de redis.setex()")
    print("\n📝 Esto debería eliminar los warnings 'Redis client not connected'")

if __name__ == "__main__":
    patch_inventory_service()
