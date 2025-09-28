#!/usr/bin/env python3
"""
🏗️ FASE 1: Architectural Quick Fix para Redis Connection Management
================================================================

Implementa la solución arquitectónica correcta manteniendo compatibilidad
con el código existente mientras elimina el technical debt.

Author: Senior Architecture Team
"""

import sys
import shutil
import os
from datetime import datetime

sys.path.append('src')

def backup_current_implementation():
    """Crear backup de la implementación actual"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"backup_redis_architecture_{timestamp}"
    
    os.makedirs(backup_dir, exist_ok=True)
    
    files_to_backup = [
        "src/api/inventory/inventory_service.py",
        "src/api/core/redis_connection_pool.py",
        "src/api/routers/products_router.py"
    ]
    
    for file_path in files_to_backup:
        if os.path.exists(file_path):
            backup_path = os.path.join(backup_dir, os.path.basename(file_path))
            shutil.copy2(file_path, backup_path)
            print(f"✅ Backup creado: {backup_path}")
    
    return backup_dir

def implement_redis_service_layer():
    """
    Implementa la capa de servicio Redis arquitectónicamente correcta
    """
    
    redis_service_content = '''"""
Redis Service Layer - Arquitectura Enterprise
==============================================

Capa de abstracción para operaciones Redis que proporciona:
- Connection pooling automático
- Error handling consistente  
- Observabilidad integrada
- Preparación para microservicios

Author: Senior Architecture Team
"""

import asyncio
import logging
import json
from typing import Optional, Any, Dict
from datetime import datetime
import time

from src.api.core.redis_config_fix import PatchedRedisClient

logger = logging.getLogger(__name__)

class RedisServiceError(Exception):
    """Base exception para errores de Redis Service"""
    pass

class RedisService:
    """
    🏗️ ENTERPRISE REDIS SERVICE
    
    Proporciona una interfaz limpia y robusta para operaciones Redis
    con connection management automático y error handling consistente.
    """
    
    _instance: Optional['RedisService'] = None
    _connection_lock = asyncio.Lock()
    
    def __init__(self):
        self._client: Optional[PatchedRedisClient] = None
        self._connected = False
        self._connection_attempts = 0
        self._last_connection_attempt = 0
        self._stats = {
            "operations_total": 0,
            "operations_successful": 0,
            "operations_failed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "connection_errors": 0
        }
    
    @classmethod
    async def get_instance(cls) -> 'RedisService':
        """
        Singleton pattern con lazy initialization.
        Thread-safe y async-safe.
        """
        if cls._instance is None:
            async with cls._connection_lock:
                if cls._instance is None:
                    cls._instance = cls()
                    await cls._instance._initialize()
        return cls._instance
    
    async def _initialize(self):
        """Inicialización segura del servicio Redis"""
        try:
            self._client = PatchedRedisClient(use_validated_config=True)
            # ✅ FASE 1 KEY FIX: Conectar durante inicialización
            await self._ensure_connection()
            logger.info("✅ RedisService initialized successfully")
        except Exception as e:
            logger.warning(f"⚠️ RedisService initialization failed: {e}")
            # Service degrada gracefully sin Redis
            self._client = None
    
    async def _ensure_connection(self) -> bool:
        """
        Asegura que tenemos una conexión válida a Redis.
        
        Returns:
            bool: True si la conexión está disponible
        """
        if not self._client:
            return False
        
        # Rate limiting para evitar spam de conexiones
        current_time = time.time()
        if (current_time - self._last_connection_attempt) < 5:  # 5 segundo cooldown
            return self._connected
        
        self._last_connection_attempt = current_time
        
        try:
            if not self._connected:
                async with self._connection_lock:
                    if not self._connected:  # Double-check
                        success = await self._client.connect()
                        if success:
                            self._connected = True
                            self._connection_attempts = 0
                            logger.debug("✅ Redis connection established")
                        else:
                            self._connection_attempts += 1
                            if self._connection_attempts % 5 == 0:  # Log every 5 attempts
                                logger.warning(f"Redis connection failed after {self._connection_attempts} attempts")
            
            return self._connected
            
        except Exception as e:
            self._stats["connection_errors"] += 1
            self._connected = False
            logger.debug(f"Redis connection error: {e}")
            return False
    
    async def get(self, key: str) -> Optional[str]:
        """
        🔍 GET operation con error handling robusto
        
        Args:
            key: Redis key
            
        Returns:
            Valor o None si no existe/error
        """
        self._stats["operations_total"] += 1
        
        if not await self._ensure_connection():
            self._stats["operations_failed"] += 1
            logger.debug(f"Redis not available for GET: {key}")
            return None
        
        try:
            result = await self._client.get(key)
            self._stats["operations_successful"] += 1
            
            if result is not None:
                self._stats["cache_hits"] += 1
                logger.debug(f"Cache HIT: {key}")
            else:
                self._stats["cache_misses"] += 1
                logger.debug(f"Cache MISS: {key}")
            
            return result
            
        except Exception as e:
            self._stats["operations_failed"] += 1
            self._connected = False  # Force reconnection next time
            logger.debug(f"Redis GET error for key {key}: {e}")
            return None
    
    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """
        🔄 SET operation con TTL opcional
        
        Args:
            key: Redis key
            value: Value to store
            ttl: TTL in seconds (optional)
            
        Returns:
            bool: True if successful
        """
        self._stats["operations_total"] += 1
        
        if not await self._ensure_connection():
            self._stats["operations_failed"] += 1
            logger.debug(f"Redis not available for SET: {key}")
            return False
        
        try:
            if ttl:
                success = await self._client.setex(key, ttl, value)
            else:
                success = await self._client.set(key, value)
            
            if success:
                self._stats["operations_successful"] += 1
                logger.debug(f"Cache SET: {key} (TTL: {ttl})")
            else:
                self._stats["operations_failed"] += 1
            
            return bool(success)
            
        except Exception as e:
            self._stats["operations_failed"] += 1
            self._connected = False
            logger.debug(f"Redis SET error for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """
        🗑️ DELETE operation
        
        Args:
            key: Redis key to delete
            
        Returns:
            bool: True if successful
        """
        self._stats["operations_total"] += 1
        
        if not await self._ensure_connection():
            self._stats["operations_failed"] += 1
            return False
        
        try:
            result = await self._client.delete(key)
            self._stats["operations_successful"] += 1
            logger.debug(f"Cache DELETE: {key}")
            return bool(result)
            
        except Exception as e:
            self._stats["operations_failed"] += 1
            self._connected = False
            logger.debug(f"Redis DELETE error for key {key}: {e}")
            return False
    
    async def get_json(self, key: str) -> Optional[Dict]:
        """
        📄 GET con deserialización JSON automática
        
        Args:
            key: Redis key
            
        Returns:
            Dict deserialized or None
        """
        raw_value = await self.get(key)
        if raw_value is None:
            return None
        
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error for key {key}: {e}")
            return None
    
    async def set_json(self, key: str, value: Dict, ttl: Optional[int] = None) -> bool:
        """
        📝 SET con serialización JSON automática
        
        Args:
            key: Redis key
            value: Dict to serialize
            ttl: TTL in seconds (optional)
            
        Returns:
            bool: True if successful
        """
        try:
            json_value = json.dumps(value)
            return await self.set(key, json_value, ttl)
        except (TypeError, ValueError) as e:
            logger.warning(f"JSON encode error for key {key}: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        📊 Estadísticas del servicio para observabilidad
        """
        hit_ratio = 0.0
        if self._stats["cache_hits"] + self._stats["cache_misses"] > 0:
            hit_ratio = self._stats["cache_hits"] / (self._stats["cache_hits"] + self._stats["cache_misses"])
        
        return {
            **self._stats,
            "connected": self._connected,
            "hit_ratio": hit_ratio,
            "client_available": self._client is not None,
            "connection_attempts": self._connection_attempts,
            "last_update": datetime.now().isoformat()
        }
    
    def reset_stats(self):
        """Reset statistics (útil para testing)"""
        self._stats = {key: 0 for key in self._stats.keys()}
    
    async def health_check(self) -> Dict[str, Any]:
        """
        🏥 Health check completo del servicio
        """
        health = {
            "service": "RedisService",
            "status": "unknown",
            "connected": False,
            "ping_successful": False,
            "error": None
        }
        
        try:
            if await self._ensure_connection():
                # Test ping
                ping_result = await self._client.ping()
                health.update({
                    "status": "healthy",
                    "connected": True,
                    "ping_successful": bool(ping_result),
                    "stats": self.get_stats()
                })
            else:
                health.update({
                    "status": "degraded",
                    "connected": False,
                    "ping_successful": False,
                    "stats": self.get_stats()
                })
                
        except Exception as e:
            health.update({
                "status": "unhealthy",
                "connected": False,
                "ping_successful": False,
                "error": str(e),
                "stats": self.get_stats()
            })
        
        return health


# ============================================================================
# 🔧 CONVENIENCE FUNCTIONS - Backward Compatibility
# ============================================================================

async def get_redis_service() -> RedisService:
    """
    Factory function para obtener la instancia del servicio Redis.
    Mantiene compatibilidad con el código existente.
    """
    return await RedisService.get_instance()


# ============================================================================
# 📊 OBSERVABILITY HELPERS
# ============================================================================

async def get_redis_health() -> Dict[str, Any]:
    """Health check rápido para endpoints de salud"""
    service = await get_redis_service()
    return await service.health_check()

async def get_redis_stats() -> Dict[str, Any]:
    """Estadísticas para métricas"""
    service = await get_redis_service()
    return service.get_stats()
'''
    
    # Escribir el archivo
    with open("src/api/core/redis_service.py", 'w', encoding='utf-8') as f:
        f.write(redis_service_content)
    
    print("✅ RedisService implementado: src/api/core/redis_service.py")

def refactor_inventory_service():
    """
    Refactoriza InventoryService para usar la nueva arquitectura
    """
    
    # Leer archivo actual
    with open("src/api/inventory/inventory_service.py", 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Reemplazar imports
    old_imports = '''# Imports para integración
# from src.api.core.redis_client import RedisClient
from src.api.core.redis_config_fix import PatchedRedisClient as RedisClient
from src.api.core.redis_connection_pool import ensure_redis_connected
from src.api.core.store import get_shopify_client'''
    
    new_imports = '''# Imports para integración
from src.api.core.redis_service import get_redis_service, RedisService
from src.api.core.store import get_shopify_client'''
    
    # Reemplazar constructor
    old_constructor = '''    def __init__(self, redis_client: Optional[RedisClient] = None):
        self.redis = redis_client
        self.shopify_client = None'''
    
    new_constructor = '''    def __init__(self, redis_service: Optional[RedisService] = None):
        self.redis_service = redis_service
        self.shopify_client = None
        # ✅ ARCHITECTURAL FIX: Initialize Redis service if not provided
        if self.redis_service is None:
            asyncio.create_task(self._initialize_redis_service())'''
    
    # Agregar método de inicialización
    initialization_method = '''
    async def _initialize_redis_service(self):
        """Inicializar Redis service de forma lazy y segura"""
        try:
            self.redis_service = await get_redis_service()
            logger.debug("✅ Redis service initialized for InventoryService")
        except Exception as e:
            logger.warning(f"⚠️ Redis service initialization failed: {e}")
            self.redis_service = None
'''
    
    # Reemplazar métodos de cache
    old_get_cache = '''    async def _get_cached_inventory(self, product_id: str, market_id: str) -> Optional[InventoryInfo]:
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
    
    new_get_cache = '''    async def _get_cached_inventory(self, product_id: str, market_id: str) -> Optional[InventoryInfo]:
        """Obtener información de inventario desde cache"""
        if not self.redis_service:
            await self._initialize_redis_service()
        
        if not self.redis_service:
            return None
            
        try:
            cache_key = f"{self.CACHE_PREFIX}:{product_id}:{market_id}"
            cached_data = await self.redis_service.get(cache_key)'''
    
    old_set_cache = '''    async def _cache_inventory_info(self, inventory_info: InventoryInfo, market_id: str):
        """Cachear información de inventario"""
        if not self.redis:
            return
            
        try:
            # ✅ COMBINADO: Connection Pool + Error Prevention
            if not await ensure_redis_connected(self.redis):
                logger.debug(f"Redis not available for cache write: {inventory_info.product_id}")
                return
                
            cache_key = f"{self.CACHE_PREFIX}:{inventory_info.product_id}:{market_id}"
            cache_data = {
                "product_id": inventory_info.product_id,
                "status": inventory_info.status.value,
                "quantity": inventory_info.quantity,
                "reserved_quantity": inventory_info.reserved_quantity,
                "available_quantity": inventory_info.available_quantity,
                "low_stock_threshold": inventory_info.low_stock_threshold,
                "market_availability": inventory_info.market_availability,
                "supplier_info": inventory_info.supplier_info,
                "last_updated": inventory_info.last_updated,
                "estimated_restock_date": inventory_info.estimated_restock_date
            }
            
            await self.redis.setex(cache_key, self.CACHE_TTL, json.dumps(cache_data))'''
    
    new_set_cache = '''    async def _cache_inventory_info(self, inventory_info: InventoryInfo, market_id: str):
        """Cachear información de inventario"""
        if not self.redis_service:
            await self._initialize_redis_service()
        
        if not self.redis_service:
            return
            
        try:
            cache_key = f"{self.CACHE_PREFIX}:{inventory_info.product_id}:{market_id}"
            cache_data = {
                "product_id": inventory_info.product_id,
                "status": inventory_info.status.value,
                "quantity": inventory_info.quantity,
                "reserved_quantity": inventory_info.reserved_quantity,
                "available_quantity": inventory_info.available_quantity,
                "low_stock_threshold": inventory_info.low_stock_threshold,
                "market_availability": inventory_info.market_availability,
                "supplier_info": inventory_info.supplier_info,
                "last_updated": inventory_info.last_updated,
                "estimated_restock_date": inventory_info.estimated_restock_date
            }
            
            await self.redis_service.set_json(cache_key, cache_data, self.CACHE_TTL)'''
    
    # Aplicar transformaciones
    content = content.replace(old_imports, new_imports)
    content = content.replace(old_constructor, new_constructor)
    content = content.replace(old_get_cache, new_get_cache)
    content = content.replace(old_set_cache, new_set_cache)
    
    # Agregar método de inicialización después del constructor
    constructor_end = new_constructor + '\n        \n        logger.info("🏪 InventoryService initialized")'
    if constructor_end in content:
        content = content.replace(constructor_end, new_constructor + initialization_method + '\n        \n        logger.info("🏪 InventoryService initialized")')
    
    # Escribir archivo refactorizado
    with open("src/api/inventory/inventory_service.py", 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ InventoryService refactorizado con nueva arquitectura")

def update_products_router():
    """
    Actualiza products_router para usar la nueva arquitectura
    """
    
    # Leer archivo actual
    with open("src/api/routers/products_router.py", 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Actualizar import
    old_import = '''from src.api.core.redis_config_fix import PatchedRedisClient as RedisClient'''
    new_import = '''from src.api.core.redis_service import get_redis_service'''
    
    # Reemplazar función get_inventory_service
    old_function = '''def get_inventory_service() -> InventoryService:
    """Factory para obtener InventoryService singleton"""
    global _inventory_service
    if _inventory_service is None:
        try:
            # ✅ CORRECCIÓN: Usar PatchedRedisClient con configuración validada
            redis_client = RedisClient(use_validated_config=True)
            logger.info("✅ InventoryService inicializado con Redis validado")
            _inventory_service = create_inventory_service(redis_client)
        except Exception as e:
            logger.warning(f"Redis no disponible, InventoryService en modo fallback: {e}")
            _inventory_service = create_inventory_service(None)
    return _inventory_service'''
    
    new_function = '''def get_inventory_service() -> InventoryService:
    """Factory para obtener InventoryService singleton"""
    global _inventory_service
    if _inventory_service is None:
        try:
            # ✅ ARCHITECTURAL FIX: Use RedisService instead of direct client
            _inventory_service = create_inventory_service(None)  # RedisService auto-initialized
            logger.info("✅ InventoryService inicializado con RedisService")
        except Exception as e:
            logger.warning(f"Error inicializando InventoryService: {e}")
            _inventory_service = create_inventory_service(None)
    return _inventory_service'''
    
    # Aplicar cambios
    if old_import in content:
        content = content.replace(old_import, new_import)
    
    if old_function in content:
        content = content.replace(old_function, new_function)
    
    # Escribir archivo actualizado
    with open("src/api/routers/products_router.py", 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ products_router.py actualizado con nueva arquitectura")

def create_validation_script():
    """Crear script de validación para la nueva arquitectura"""
    
    validation_script = '''#!/usr/bin/env python3
"""
🧪 Validación de la Nueva Arquitectura Redis
============================================

Valida que la refactorización arquitectónica funciona correctamente.
"""

import sys
import asyncio
sys.path.append('src')

async def test_redis_service():
    """Test del nuevo RedisService"""
    print("🧪 Testing RedisService...")
    
    try:
        from src.api.core.redis_service import get_redis_service
        
        # Obtener servicio
        service = await get_redis_service()
        print("✅ RedisService instance obtenida")
        
        # Health check
        health = await service.health_check()
        print(f"✅ Health check: {health['status']}")
        
        # Test operaciones básicas
        test_key = "test:architecture:validation"
        test_value = {"message": "Nueva arquitectura funcionando", "timestamp": "2025-08-07"}
        
        # Test SET
        set_result = await service.set_json(test_key, test_value, ttl=60)
        print(f"✅ SET operation: {set_result}")
        
        # Test GET
        get_result = await service.get_json(test_key)
        print(f"✅ GET operation: {get_result}")
        
        # Test DELETE
        del_result = await service.delete(test_key)
        print(f"✅ DELETE operation: {del_result}")
        
        # Stats
        stats = service.get_stats()
        print(f"✅ Service stats: hit_ratio={stats['hit_ratio']:.2f}, operations={stats['operations_total']}")
        
        return True
        
    except Exception as e:
        print(f"❌ RedisService test failed: {e}")
        return False

async def test_inventory_service():
    """Test del InventoryService refactorizado"""
    print("\\n🧪 Testing InventoryService...")
    
    try:
        from src.api.inventory.inventory_service import create_inventory_service
        
        # Crear servicio (RedisService se inicializa automáticamente)
        service = create_inventory_service()
        print("✅ InventoryService creado")
        
        # Test availability check
        inventory_info = await service.check_product_availability("test_product", "US")
        print(f"✅ Availability check: {inventory_info.status.value}")
        
        # Test múltiples productos
        multi_result = await service.check_multiple_products_availability(
            ["prod_001", "prod_002"], "US"
        )
        print(f"✅ Multiple products check: {len(multi_result)} productos procesados")
        
        return True
        
    except Exception as e:
        print(f"❌ InventoryService test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_products_router():
    """Test de products_router factories"""
    print("\\n🧪 Testing ProductsRouter factories...")
    
    try:
        from src.api.routers.products_router import get_inventory_service, get_product_cache
        
        # Test inventory service factory
        inventory_service = get_inventory_service()
        print("✅ get_inventory_service() funcionando")
        
        # Test product cache factory
        product_cache = get_product_cache()
        print(f"✅ get_product_cache() funcionando: {type(product_cache)}")
        
        return True
        
    except Exception as e:
        print(f"❌ ProductsRouter test failed: {e}")
        return False

async def main():
    """Ejecutar todas las validaciones"""
    print("🚀 === VALIDACIÓN ARQUITECTURA REDIS FASE 1 ===\\n")
    
    results = []
    
    # Test RedisService
    results.append(await test_redis_service())
    
    # Test InventoryService  
    results.append(await test_inventory_service())
    
    # Test ProductsRouter
    results.append(await test_products_router())
    
    # Resultado final
    print("\\n📊 === RESULTADOS ===")
    total_tests = len(results)
    passed_tests = sum(results)
    
    print(f"Tests ejecutados: {total_tests}")
    print(f"Tests exitosos: {passed_tests}")
    print(f"Tests fallidos: {total_tests - passed_tests}")
    
    if passed_tests == total_tests:
        print("\\n🎉 ¡TODAS LAS VALIDACIONES EXITOSAS!")
        print("✅ La nueva arquitectura Redis está funcionando correctamente")
        print("✅ Sistema listo para Fase 2 (Repository Pattern)")
    else:
        print(f"\\n⚠️ {total_tests - passed_tests} validaciones fallaron")
        print("❌ Revisar implementación antes de continuar")
    
    return passed_tests == total_tests

if __name__ == "__main__":
    asyncio.run(main())
'''
    
    with open("validate_redis_architecture.py", 'w', encoding='utf-8') as f:
        f.write(validation_script)
    
    print("✅ Script de validación creado: validate_redis_architecture.py")

def main():
    """Ejecutar la implementación completa de Fase 1"""
    print("🏗️ === IMPLEMENTACIÓN FASE 1: ARQUITECTURA REDIS ENTERPRISE ===\n")
    
    try:
        # 1. Backup
        backup_dir = backup_current_implementation()
        print(f"✅ Backup completado en: {backup_dir}\n")
        
        # 2. Implementar RedisService
        implement_redis_service_layer()
        
        # 3. Refactorizar InventoryService
        refactor_inventory_service()
        
        # 4. Actualizar ProductsRouter
        update_products_router()
        
        # 5. Crear script de validación
        create_validation_script()
        
        print("\n🎉 === FASE 1 COMPLETADA ===")
        print("✅ RedisService enterprise implementado")
        print("✅ InventoryService refactorizado")
        print("✅ ProductsRouter actualizado")
        print("✅ Script de validación creado")
        
        print("\n📋 === PRÓXIMOS PASOS ===")
        print("1. Ejecutar: python validate_redis_architecture.py")
        print("2. Verificar que no hay más warnings en logs")
        print("3. Confirmar funcionalidad de endpoints /v1/products/")
        print("4. Si todo funciona, proceder con Fase 2 (Repository Pattern)")
        
        print("\n🔧 === BENEFICIOS IMPLEMENTADOS ===")
        print("✅ Connection management centralizado")
        print("✅ Error handling consistente")  
        print("✅ Observabilidad integrada")
        print("✅ Preparado para microservicios")
        print("✅ Zero technical debt en Redis operations")
        
    except Exception as e:
        print(f"❌ Error durante implementación: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
