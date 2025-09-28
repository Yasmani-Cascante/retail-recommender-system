#!/usr/bin/env python3
# validate_enterprise_corrections.py
"""
Script de Validación - Correcciones Redis Enterprise
===================================================

Valida que las correcciones críticas se hayan aplicado correctamente:
1. inventory_service.py - Imports y referencias corregidas
2. products_router.py - Funciones definidas y dependency injection
3. ServiceFactory - Integración enterprise
4. Sintaxis y estructura correcta

Author: Senior Architecture Team
Version: 1.0.0
"""

import sys
import importlib
import traceback
import logging
import inspect

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EnterpriseCorrectionsValidator:
    """Validador de correcciones enterprise implementadas"""
    
    def __init__(self):
        self.results = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "errors": [],
            "warnings": []
        }
    
    def validate_all(self):
        """Ejecutar todas las validaciones"""
        logger.info("🚀 Starting Enterprise Corrections Validation...")
        
        tests = [
            ("InventoryService Import", self.test_inventory_service_import),
            ("InventoryService Structure", self.test_inventory_service_structure),
            ("ProductsRouter Import", self.test_products_router_import),
            ("ProductsRouter Functions", self.test_products_router_functions),
            ("ServiceFactory Import", self.test_service_factory_import),
            ("ServiceFactory Methods", self.test_service_factory_methods),
            ("Dependency Injection", self.test_dependency_injection),
            ("RedisService Integration", self.test_redis_service_integration)
        ]
        
        for test_name, test_func in tests:
            self.run_test(test_name, test_func)
        
        self.print_summary()
        return self.results["failed"] == 0
    
    def run_test(self, test_name: str, test_func):
        """Ejecutar un test individual"""
        self.results["total_tests"] += 1
        try:
            logger.info(f"🔍 Testing: {test_name}")
            result = test_func()
            if result:
                logger.info(f"✅ {test_name}: PASSED")
                self.results["passed"] += 1
            else:
                logger.error(f"❌ {test_name}: FAILED")
                self.results["failed"] += 1
        except Exception as e:
            error_msg = f"Exception in {test_name}: {str(e)}"
            logger.error(f"💥 {test_name}: EXCEPTION - {error_msg}")
            self.results["failed"] += 1
            self.results["errors"].append(error_msg)
    
    def test_inventory_service_import(self) -> bool:
        """Test import de InventoryService"""
        try:
            from src.api.inventory.inventory_service import (
                InventoryService, 
                InventoryInfo, 
                InventoryStatus,
                create_inventory_service
            )
            return True
        except ImportError as e:
            self.results["errors"].append(f"InventoryService import failed: {e}")
            return False
    
    def test_inventory_service_structure(self) -> bool:
        """Test estructura de InventoryService"""
        try:
            from src.api.inventory.inventory_service import InventoryService
            
            # Verificar constructor
            sig = inspect.signature(InventoryService.__init__)
            params = list(sig.parameters.keys())
            
            if 'redis_service' not in params:
                self.results["errors"].append("InventoryService constructor missing redis_service parameter")
                return False
            
            # Verificar métodos enterprise
            required_methods = ['ensure_ready', 'get_stats']
            for method in required_methods:
                if not hasattr(InventoryService, method):
                    self.results["errors"].append(f"InventoryService missing method: {method}")
                    return False
            
            return True
        except Exception as e:
            self.results["errors"].append(f"InventoryService structure test failed: {e}")
            return False
    
    def test_products_router_import(self) -> bool:
        """Test import de products_router"""
        try:
            from src.api.routers import products_router
            return hasattr(products_router, 'router')
        except ImportError as e:
            self.results["errors"].append(f"ProductsRouter import failed: {e}")
            return False
    
    def test_products_router_functions(self) -> bool:
        """Test funciones en products_router"""
        try:
            from src.api.routers.products_router import (
                get_inventory_service_dependency,
                get_product_cache_dependency,
                get_availability_checker_dependency,
                get_inventory_service,  # Legacy
                get_availability_checker,  # Legacy
                get_product_cache  # Legacy
            )
            
            # Verificar que las funciones enterprise son async
            if not inspect.iscoroutinefunction(get_inventory_service_dependency):
                self.results["errors"].append("get_inventory_service_dependency is not async")
                return False
                
            if not inspect.iscoroutinefunction(get_product_cache_dependency):
                self.results["errors"].append("get_product_cache_dependency is not async")
                return False
            
            return True
        except ImportError as e:
            self.results["errors"].append(f"ProductsRouter functions import failed: {e}")
            return False
    
    def test_service_factory_import(self) -> bool:
        """Test import de ServiceFactory"""
        try:
            from src.api.factories.service_factory import (
                ServiceFactory,
                get_inventory_service,
                get_product_cache,
                health_check_services
            )
            return True
        except ImportError as e:
            self.results["errors"].append(f"ServiceFactory import failed: {e}")
            return False
    
    def test_service_factory_methods(self) -> bool:
        """Test métodos de ServiceFactory"""
        try:
            from src.api.factories.service_factory import ServiceFactory
            
            required_methods = [
                'get_redis_service',
                'create_inventory_service',
                'create_product_cache',
                'health_check_all_services'
            ]
            
            for method in required_methods:
                if not hasattr(ServiceFactory, method):
                    self.results["errors"].append(f"ServiceFactory missing method: {method}")
                    return False
                
                # Verificar que métodos de servicio son async
                if method != 'get_redis_service':  # exclude class method
                    method_obj = getattr(ServiceFactory, method)
                    if not inspect.iscoroutinefunction(method_obj):
                        self.results["warnings"].append(f"ServiceFactory.{method} might need to be async")
            
            return True
        except Exception as e:
            self.results["errors"].append(f"ServiceFactory methods test failed: {e}")
            return False
    
    def test_dependency_injection(self) -> bool:
        """Test dependency injection unificada"""
        try:
            from src.api.routers.products_router import get_inventory_service_dependency
            from src.api.inventory.inventory_service import InventoryService
            from src.api.core.redis_service import RedisService
            
            # Verificar signature de dependency functions
            sig = inspect.signature(get_inventory_service_dependency)
            if len(sig.parameters) != 0:
                self.results["warnings"].append("get_inventory_service_dependency should have no parameters")
            
            return True
        except Exception as e:
            self.results["errors"].append(f"Dependency injection test failed: {e}")
            return False
    
    def test_redis_service_integration(self) -> bool:
        """Test integración con RedisService"""
        try:
            from src.api.core.redis_service import RedisService, get_redis_service
            
            # Verificar que get_redis_service es async
            if not inspect.iscoroutinefunction(get_redis_service):
                self.results["errors"].append("get_redis_service is not async")
                return False
            
            # Verificar métodos enterprise de RedisService
            required_methods = ['health_check', 'get_stats']
            for method in required_methods:
                if not hasattr(RedisService, method):
                    self.results["errors"].append(f"RedisService missing method: {method}")
                    return False
            
            return True
        except Exception as e:
            self.results["errors"].append(f"RedisService integration test failed: {e}")
            return False
    
    def print_summary(self):
        """Imprimir resumen de resultados"""
        success_rate = (self.results["passed"] / self.results["total_tests"]) * 100
        
        print("\\n" + "="*60)
        print("🏁 ENTERPRISE CORRECTIONS VALIDATION SUMMARY")
        print("="*60)
        print(f"📊 Total Tests: {self.results['total_tests']}")
        print(f"✅ Passed: {self.results['passed']}")
        print(f"❌ Failed: {self.results['failed']}")
        print(f"📈 Success Rate: {success_rate:.1f}%")
        
        if self.results["errors"]:
            print("\\n🚨 ERRORS:")
            for error in self.results["errors"]:
                print(f"  • {error}")
        
        if self.results["warnings"]:
            print("\\n⚠️ WARNINGS:")
            for warning in self.results["warnings"]:
                print(f"  • {warning}")
        
        if success_rate >= 90:
            print("\\n🎉 VALIDATION SUCCESSFUL - Enterprise corrections properly implemented!")
        elif success_rate >= 70:
            print("\\n⚠️ VALIDATION PARTIAL - Some issues need attention")
        else:
            print("\\n❌ VALIDATION FAILED - Critical issues need to be resolved")
        
        print("="*60)

def main():
    """Main function"""
    validator = EnterpriseCorrectionsValidator()
    success = validator.validate_all()
    
    if success:
        logger.info("🎯 All validations passed - Enterprise corrections successful!")
        sys.exit(0)
    else:
        logger.error("❌ Some validations failed - Review errors above")
        sys.exit(1)

if __name__ == "__main__":
    main()
