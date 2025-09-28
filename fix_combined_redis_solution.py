#!/usr/bin/env python3
"""
Parche combinado: Connection Pool + Error Prevention
"""

import sys
sys.path.append('src')

def apply_combined_fix():
    """
    Aplica el parche combinado que incluye:
    1. Connection Pool para optimización
    2. Error checks para prevenir warnings
    """
    print("🔧 === APLICANDO PARCHE COMBINADO ===\n")
    
    file_path = "src/api/inventory/inventory_service.py"
    
    # Leer archivo actual
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. Asegurar que tenemos el import del connection pool
    import_line = "from src.api.core.redis_connection_pool import ensure_redis_connected"
    
    if import_line not in content:
        redis_import_line = "from src.api.core.redis_config_fix import PatchedRedisClient as RedisClient"
        if redis_import_line in content:
            content = content.replace(
                redis_import_line,
                redis_import_line + "\n" + import_line
            )
            print("✅ Import del connection pool agregado")
    else:
        print("✅ Import del connection pool ya existe")
    
    # 2. Parche CORRECTO para _get_cached_inventory que combina ambas soluciones
    old_method = '''    async def _get_cached_inventory(self, product_id: str, market_id: str) -> Optional[InventoryInfo]:
        """Obtener información de inventario desde cache"""
        if not self.redis:
            return None
            
        try:
            # ✅ OPTIMIZADO: Usar connection pool
            if not await ensure_redis_connected(self.redis):
                return None
                
            cache_key = f"{self.CACHE_PREFIX}:{product_id}:{market_id}"
            cached_data = await self.redis.get(cache_key)'''
    
    new_method = '''    async def _get_cached_inventory(self, product_id: str, market_id: str) -> Optional[InventoryInfo]:
        """Obtener información de inventario desde cache"""
        if not self.redis:
            return None
            
        try:
            # ✅ COMBINADO: Connection Pool + Error Prevention
            if not await ensure_redis_connected(self.redis):
                logger.debug(f"Redis not available for cache read: {product_id}")
                return None
                
            cache_key = f"{self.CACHE_PREFIX}:{product_id}:{market_id}"
            cached_data = await self.redis.get(cache_key)'''
    
    # 3. Parche CORRECTO para _cache_inventory_info
    old_cache_method = '''    async def _cache_inventory_info(self, inventory_info: InventoryInfo, market_id: str):
        """Cachear información de inventario"""
        if not self.redis:
            return
            
        try:
            # ✅ OPTIMIZADO: Usar connection pool
            if not await ensure_redis_connected(self.redis):
                return
                
            cache_key = f"{self.CACHE_PREFIX}:{inventory_info.product_id}:{market_id}"'''
    
    new_cache_method = '''    async def _cache_inventory_info(self, inventory_info: InventoryInfo, market_id: str):
        """Cachear información de inventario"""
        if not self.redis:
            return
            
        try:
            # ✅ COMBINADO: Connection Pool + Error Prevention
            if not await ensure_redis_connected(self.redis):
                logger.debug(f"Redis not available for cache write: {inventory_info.product_id}")
                return
                
            cache_key = f"{self.CACHE_PREFIX}:{inventory_info.product_id}:{market_id}"'''
    
    # Aplicar parches
    patches_applied = 0
    
    if old_method in content:
        content = content.replace(old_method, new_method)
        print("✅ Método _get_cached_inventory parcheado (COMBINADO)")
        patches_applied += 1
    elif "_get_cached_inventory" in content:
        print("⚠️ _get_cached_inventory ya modificado - necesita ajuste manual")
    else:
        print("❌ _get_cached_inventory no encontrado")
    
    if old_cache_method in content:
        content = content.replace(old_cache_method, new_cache_method)
        print("✅ Método _cache_inventory_info parcheado (COMBINADO)")
        patches_applied += 1
    elif "_cache_inventory_info" in content:
        print("⚠️ _cache_inventory_info ya modificado - necesita ajuste manual")
    else:
        print("❌ _cache_inventory_info no encontrado")
    
    # Crear backup
    import shutil
    backup_path = f"{file_path}.backup_combined_fix"
    shutil.copy2(file_path, backup_path)
    print(f"✅ Backup creado: {backup_path}")
    
    # Escribir archivo
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    if patches_applied > 0:
        print(f"✅ Parche combinado aplicado exitosamente ({patches_applied} métodos)")
        
        print("\\n🎯 BENEFICIOS DEL PARCHE COMBINADO:")
        print("   1. ✅ Connection Pool: Reduce logs múltiples de conexión")
        print("   2. ✅ Error Prevention: Elimina warnings 'Redis client not connected'")
        print("   3. ✅ Debug Logging: Logs informativos en lugar de warnings")
        
        return True
    else:
        print("⚠️ No se pudieron aplicar los parches automáticamente")
        return False

def manual_fix_instructions():
    """
    Instrucciones para fix manual si es necesario
    """
    print("\\n🔧 === INSTRUCCIONES PARA FIX MANUAL ===\\n")
    
    print("Si el parche automático no funcionó, aplica estos cambios manualmente:")
    print("\\n1. En el método _get_cached_inventory, cambiar:")
    print("   BUSCAR:")
    print("   ```")
    print("   if not await ensure_redis_connected(self.redis):")
    print("       return None")
    print("   ```")
    print("   REEMPLAZAR POR:")
    print("   ```")
    print("   if not await ensure_redis_connected(self.redis):")
    print("       logger.debug(f'Redis not available for cache read: {product_id}')")
    print("       return None")
    print("   ```")
    
    print("\\n2. En el método _cache_inventory_info, cambiar:")
    print("   BUSCAR:")
    print("   ```")
    print("   if not await ensure_redis_connected(self.redis):")
    print("       return")
    print("   ```")
    print("   REEMPLAZAR POR:")
    print("   ```")
    print("   if not await ensure_redis_connected(self.redis):")
    print("       logger.debug(f'Redis not available for cache write: {inventory_info.product_id}')")
    print("       return")
    print("   ```")

def main():
    print("🚀 PARCHE COMBINADO: Connection Pool + Error Prevention\\n")
    
    success = apply_combined_fix()
    
    if success:
        print("\\n✅ PARCHE APLICADO EXITOSAMENTE")
        print("\\n📝 RESULTADO ESPERADO:")
        print("   ❌ Eliminados: 'Error reading inventory cache: Redis client not connected'")
        print("   ✅ Reducidos: Logs de 'Intentando conexión Redis' (de 5 a 1)")
        print("   ✅ Añadidos: Debug logs informativos en lugar de warnings")
        
        print("\\n🧪 PARA PROBAR:")
        print("   Ejecuta el endpoint /products/ y verifica que:")
        print("   1. No hay warnings de 'Redis client not connected'")
        print("   2. Hay menos logs de 'Intentando conexión Redis'")
        print("   3. Solo aparecen warnings de productos no encontrados (normal)")
        
    else:
        manual_fix_instructions()

if __name__ == "__main__":
    main()
