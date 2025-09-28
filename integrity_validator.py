#!/usr/bin/env python3
"""
VALIDADOR DE INTEGRIDAD EN TIEMPO REAL
====================================

Verifica que las correcciones están realmente activas y funcionando.
"""

import sys
import asyncio
import time
import inspect
sys.path.append('src')

class IntegrityValidator:
    """Validador que verifica integridad real del sistema"""
    
    def __init__(self):
        self.results = {}
    
    async def validate_market_config_service(self):
        """Valida que MarketConfigService tiene métodos requeridos y funcionan"""
        print("🔍 Validating MarketConfigService...")
        
        try:
            from api.mcp_services.market_config.service import MarketConfigService
            
            service = MarketConfigService()
            
            # Verificar métodos existen
            required_methods = [
                'get_market_context',
                'get_market_currency',
                'get_market_language', 
                'get_market_tier_name'
            ]
            
            missing_methods = []
            for method in required_methods:
                if not hasattr(service, method):
                    missing_methods.append(method)
            
            if missing_methods:
                self.results['market_config'] = {
                    'status': 'FAIL',
                    'issue': f'Missing methods: {missing_methods}'
                }
                return False
            
            # Test funcional
            currency = await service.get_market_currency("ES")
            language = await service.get_market_language("ES") 
            tier = await service.get_market_tier_name("ES")
            
            expected = {"currency": "EUR", "language": "es", "tier": "tier_2"}
            actual = {"currency": currency, "language": language, "tier": tier}
            
            if actual == expected:
                self.results['market_config'] = {
                    'status': 'SUCCESS',
                    'details': 'All methods working correctly'
                }
                print("   ✅ MarketConfigService: WORKING")
                return True
            else:
                self.results['market_config'] = {
                    'status': 'FAIL',
                    'issue': f'Expected {expected}, got {actual}'
                }
                return False
                
        except Exception as e:
            self.results['market_config'] = {
                'status': 'ERROR',
                'issue': str(e)
            }
            print(f"   ❌ MarketConfigService: ERROR - {e}")
            return False
    
    async def validate_market_utils_async(self):
        """Valida que market_utils funciones async están activas"""
        print("🔍 Validating market_utils async functions...")
        
        try:
            from api.utils.market_utils import (
                convert_price_to_market_currency_async,
                adapt_product_for_market_async,
                _execute_async_safely
            )
            
            # Test convert_price_to_market_currency_async
            start = time.time()
            result1 = await convert_price_to_market_currency_async(100.0, "USD", "ES")
            end = time.time()
            
            if not result1.get("conversion_successful"):
                self.results['market_utils_async'] = {
                    'status': 'FAIL',
                    'issue': 'Currency conversion failed'
                }
                return False
            
            # Test adapt_product_for_market_async
            product = {"id": "integrity_test", "price": 50.0, "currency": "USD"}
            result2 = await adapt_product_for_market_async(product, "ES")
            
            if not result2.get("market_adapted"):
                self.results['market_utils_async'] = {
                    'status': 'FAIL',
                    'issue': 'Product adaptation failed'
                }
                return False
            
            # Verificar que usa versión async (debe tener metadata específica)
            async_indicators = [
                'async_first' in str(result1.get('service_used', '')),
                'async_first' in str(result2.get('architecture', '')),
                result1.get('performance_optimized', False)
            ]
            
            if any(async_indicators):
                self.results['market_utils_async'] = {
                    'status': 'SUCCESS',
                    'details': 'Async functions working with correct metadata',
                    'execution_time_ms': (end - start) * 1000
                }
                print("   ✅ market_utils async: WORKING")
                return True
            else:
                self.results['market_utils_async'] = {
                    'status': 'PARTIAL',
                    'issue': 'Functions work but may be using fallbacks'
                }
                return False
                
        except Exception as e:
            self.results['market_utils_async'] = {
                'status': 'ERROR',
                'issue': str(e)
            }
            print(f"   ❌ market_utils async: ERROR - {e}")
            return False
    
    def validate_sync_wrappers(self):
        """Valida que sync wrappers funcionan sin event loop issues"""
        print("🔍 Validating sync wrappers...")
        
        try:
            from api.utils.market_utils import (
                convert_price_to_market_currency,
                adapt_product_for_market
            )
            
            # Test sync wrapper
            result1 = convert_price_to_market_currency(100.0, "USD", "ES")
            
            if not result1.get("conversion_successful"):
                self.results['sync_wrappers'] = {
                    'status': 'FAIL',
                    'issue': 'Sync wrapper conversion failed'
                }
                return False
            
            product = {"id": "sync_test", "price": 50.0, "currency": "USD"}
            result2 = adapt_product_for_market(product, "ES")
            
            if not result2.get("market_adapted"):
                self.results['sync_wrappers'] = {
                    'status': 'FAIL',
                    'issue': 'Sync wrapper adaptation failed'
                }
                return False
            
            # Verificar que no hay errores de event loop
            has_errors = (
                'error' in result1 or 
                'error' in result2 or
                'emergency_fallback' in str(result1.get('service_used', '')) or
                'emergency_fallback' in str(result2.get('adapter_used', ''))
            )
            
            if not has_errors:
                self.results['sync_wrappers'] = {
                    'status': 'SUCCESS',
                    'details': 'Sync wrappers working without event loop issues'
                }
                print("   ✅ sync wrappers: WORKING")
                return True
            else:
                self.results['sync_wrappers'] = {
                    'status': 'FAIL',
                    'issue': 'Event loop or fallback issues detected'
                }
                return False
                
        except Exception as e:
            self.results['sync_wrappers'] = {
                'status': 'ERROR', 
                'issue': str(e)
            }
            print(f"   ❌ sync wrappers: ERROR - {e}")
            return False
    
    def validate_mcp_router_imports(self):
        """Valida que mcp_router tiene imports correctos"""
        print("🔍 Validating mcp_router imports...")
        
        try:
            router_file = "src/api/routers/mcp_router.py"
            
            with open(router_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Verificar imports críticos
            required_imports = [
                'adapt_product_for_market_async',
                'convert_price_to_market_currency_async'
            ]
            
            missing_imports = []
            for imp in required_imports:
                if imp not in content:
                    missing_imports.append(imp)
            
            # Verificar que no usa imports problemáticos
            problematic_imports = [
                'from src.core.market.adapter import get_market_adapter, adapt_product_for_market'
            ]
            
            has_problematic = any(prob in content for prob in problematic_imports)
            
            if missing_imports or has_problematic:
                self.results['router_imports'] = {
                    'status': 'FAIL',
                    'missing_imports': missing_imports,
                    'has_problematic': has_problematic
                }
                print(f"   ❌ mcp_router imports: FAIL")
                return False
            else:
                self.results['router_imports'] = {
                    'status': 'SUCCESS',
                    'details': 'All required imports present'
                }
                print("   ✅ mcp_router imports: WORKING")
                return True
                
        except Exception as e:
            self.results['router_imports'] = {
                'status': 'ERROR',
                'issue': str(e)
            }
            print(f"   ❌ mcp_router imports: ERROR - {e}")
            return False
    
    async def run_full_validation(self):
        """Ejecuta validación completa"""
        print("🚀 INICIANDO VALIDACIÓN DE INTEGRIDAD COMPLETA")
        print("=" * 60)
        
        validations = [
            ('MarketConfigService', self.validate_market_config_service()),
            ('market_utils async', self.validate_market_utils_async()),
            ('sync wrappers', self.validate_sync_wrappers),
            ('router imports', self.validate_mcp_router_imports)
        ]
        
        results = []
        for name, validation in validations:
            print(f"\n📋 Validating {name}...")
            if asyncio.iscoroutine(validation):
                result = await validation
            else:
                result = validation()
            results.append(result)
        
        # Summary
        print("\n📊 INTEGRITY VALIDATION SUMMARY")
        print("=" * 40)
        
        success_count = sum(results)
        total_count = len(results)
        
        for component, result in self.results.items():
            status = result['status']
            emoji = "✅" if status == "SUCCESS" else "⚠️" if status == "PARTIAL" else "❌"
            print(f"{emoji} {component}: {status}")
            if 'issue' in result:
                print(f"   Issue: {result['issue']}")
        
        print(f"\n🎯 OVERALL: {success_count}/{total_count} components working correctly")
        
        if success_count == total_count:
            print("🎉 SISTEMA COMPLETAMENTE ÍNTEGRO")
            return True
        elif success_count >= total_count * 0.75:
            print("✅ SISTEMA MAYORMENTE ÍNTEGRO")
            return True
        else:
            print("❌ SISTEMA REQUIERE CORRECCIONES ADICIONALES")
            return False

async def main():
    """Función principal"""
    validator = IntegrityValidator()
    return await validator.run_full_validation()

if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
