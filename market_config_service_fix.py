#!/usr/bin/env python3
"""
CORRECCIÓN 2: MarketConfigService Fix
====================================

Añade el método get_market_currency que falta en MarketConfigService
"""

def fix_market_config_service():
    """Corrige MarketConfigService añadiendo métodos faltantes"""
    
    service_file = "src/api/mcp_services/market_config/service.py"
    
    try:
        # Leer archivo actual
        with open(service_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"📝 Leyendo {service_file}...")
        
        # Verificar si el método ya existe
        if "async def get_market_currency" in content:
            print("✅ get_market_currency ya existe")
            return True
        
        # Buscar el final de la clase MarketConfigService
        class_end_pattern = r'(\s+async def validate_market_availability.*?return True)'
        
        # Método que necesitamos añadir
        new_method = '''
    
    async def get_market_currency(self, market_id: str) -> str:
        """Service boundary: Obtiene la moneda del mercado"""
        context = await self.get_market_context(market_id)
        return context.currency
    
    async def get_market_language(self, market_id: str) -> str:
        """Service boundary: Obtiene el idioma del mercado"""
        context = await self.get_market_context(market_id)
        return context.language
    
    async def get_market_tier_name(self, market_id: str) -> str:
        """Service boundary: Obtiene el tier del mercado como string"""
        context = await self.get_market_context(market_id)
        return context.tier.value'''
        
        # Buscar donde insertar el método
        if "async def validate_market_availability" in content:
            # Insertar antes del último método
            content = content.replace(
                "    async def validate_market_availability",
                new_method + "\n    async def validate_market_availability"
            )
        else:
            # Si no encontramos validate_market_availability, añadir al final de la clase
            # Buscar el final de la clase (antes del último return True o similar)
            lines = content.split('\n')
            class_started = False
            insertion_point = -1
            
            for i, line in enumerate(lines):
                if "class MarketConfigService" in line:
                    class_started = True
                elif class_started and line.strip() and not line.startswith('    ') and not line.startswith('\t'):
                    # Fin de la clase
                    insertion_point = i
                    break
            
            if insertion_point > 0:
                lines.insert(insertion_point, new_method)
                content = '\n'.join(lines)
            else:
                # Último recurso: añadir al final del archivo
                content += new_method
        
        # Escribir archivo actualizado
        with open(service_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ MarketConfigService actualizado con métodos faltantes")
        return True
        
    except Exception as e:
        print(f"❌ Error actualizando MarketConfigService: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_market_config_methods():
    """Verifica que los métodos necesarios existan"""
    
    try:
        import sys
        sys.path.append('src')
        
        from api.mcp_services.market_config.service import MarketConfigService
        
        service = MarketConfigService()
        
        # Verificar métodos
        methods_to_check = [
            'get_market_context',
            'get_market_tier', 
            'validate_market_availability',
            'get_market_currency',  # Nuevo
            'get_market_language',  # Nuevo
            'get_market_tier_name'  # Nuevo
        ]
        
        missing_methods = []
        for method in methods_to_check:
            if not hasattr(service, method):
                missing_methods.append(method)
        
        if missing_methods:
            print(f"❌ Métodos faltantes: {missing_methods}")
            return False
        else:
            print("✅ Todos los métodos necesarios están disponibles")
            return True
            
    except Exception as e:
        print(f"⚠️ No se pudo verificar métodos: {e}")
        return False

if __name__ == "__main__":
    print("🔧 CORRECCIÓN 2: MarketConfigService Fix")
    print("=" * 50)
    
    # Aplicar corrección
    success = fix_market_config_service()
    
    if success:
        # Verificar corrección
        verify_success = verify_market_config_methods()
        if verify_success:
            print("🎉 MarketConfigService fix completed successfully")
        else:
            print("⚠️ Fix applied but verification failed")
    else:
        print("❌ MarketConfigService fix failed")