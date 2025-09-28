#!/usr/bin/env python3
"""
SCRIPT PARA APLICAR FALLBACK COMPLETO A REDIS_CLIENT
===================================================

Aplica las modificaciones necesarias a todos los métodos de RedisClient
para que funcionen con el sistema de fallback.
"""

import re

def apply_fallback_to_redis_client():
    """Aplica modificaciones de fallback a todos los métodos de RedisClient"""
    
    # Leer el archivo actual
    with open('src/api/core/redis_client.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Patrón para métodos que necesitan fallback
    methods_to_modify = [
        'set', 'delete', 'health_check', 'exists', 'keys', 
        'hset', 'hget', 'hgetall', 'hdel', 'close'
    ]
    
    # Aplicar fallback pattern a cada método
    for method_name in methods_to_modify:
        # Buscar el método
        method_pattern = f'async def {method_name}\\('
        if method_pattern in content:
            print(f"✅ Applying fallback to method: {method_name}")
            
            # Agregar lógica de fallback al inicio de cada método
            fallback_logic = f'''        # 🔧 SOLUCIÓN: Delegar a fallback si es necesario
        if self.using_fallback:
            try:
                self.stats["operations"] += 1
                return await self.client.{method_name}(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error en MockRedis {method_name}: {{e}}")
                return None if '{method_name}' in ['get', 'hget'] else False
        
        # Redis real - lógica original'''
            
            # Encontrar donde insertar el fallback
            method_start = content.find(f'async def {method_name}(')
            if method_start != -1:
                # Encontrar el final del docstring
                docstring_end = content.find('"""', method_start)
                if docstring_end != -1:
                    docstring_end = content.find('"""', docstring_end + 3) + 3
                    # Insertar fallback después del docstring
                    content = (content[:docstring_end] + '\n' + 
                             fallback_logic + '\n' + 
                             content[docstring_end:])
    
    # Aplicar correcciones específicas adicionales
    content = apply_specific_corrections(content)
    
    # Escribir el archivo modificado
    with open('src/api/core/redis_client.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Fallback aplicado completamente a RedisClient")

def apply_specific_corrections(content):
    """Aplicar correcciones específicas al contenido"""
    
    # Corregir el método ensure_connected que ya modificamos parcialmente
    old_ensure = '''    async def ensure_connected(self) -> bool:
        """
        Asegura que el cliente esté conectado, conectando si es necesario.
        
        Returns:
            bool: True si está conectado, False si la conexión falla
        """
        if self.connected and self.client:
            try:
                # Verificar que la conexión sigue activa
                await self.client.ping()
                return True
            except Exception:
                # La conexión se perdió, reconectar
                self.connected = False
                
        if not self.connected:
            return await self.connect()
        return True'''
    
    new_ensure = '''    async def ensure_connected(self) -> bool:
        """
        Asegura que el cliente esté conectado, conectando si es necesario.
        
        Returns:
            bool: True si está conectado o usando fallback
        """
        # 🔧 SOLUCIÓN: Fallback siempre está "conectado"
        if self.using_fallback:
            return True
            
        # Redis real - lógica original
        if self.connected and self.client:
            try:
                # Verificar que la conexión sigue activa
                await self.client.ping()
                return True
            except Exception:
                # La conexión se perdió, reconectar
                self.connected = False
                
        if not self.connected:
            return await self.connect()
        return True'''
    
    content = content.replace(old_ensure, new_ensure)
    
    return content

if __name__ == "__main__":
    apply_fallback_to_redis_client()
    print("🎉 Modificaciones completadas!")
