#!/usr/bin/env python3
"""
Script para validar todas las dependencias necesarias para la implementación
"""
import sys
import importlib
import logging

def validate_dependencies():
    """Valida que todas las dependencias estén disponibles"""
    dependencies = [
        "src.api.main_unified_redis",
        "src.api.mcp.conversation_state_manager",
        "src.api.mcp.engines.mcp_personalization_engine", 
        "src.core.market.adapter"
    ]
    
    results = {"success": [], "failed": []}
    
    for dep in dependencies:
        try:
            module = importlib.import_module(dep)
            results["success"].append(dep)
            print(f"✅ {dep}")
            
            # Validaciones específicas
            if dep == "src.api.main_unified_redis":
                if hasattr(module, 'hybrid_recommender'):
                    print(f"  ✅ hybrid_recommender available")
                else:
                    print(f"  ⚠️ hybrid_recommender NOT available")
                    
        except ImportError as e:
            results["failed"].append({"dep": dep, "error": str(e)})
            print(f"❌ {dep}: {e}")
    
    return results

if __name__ == "__main__":
    print("🔍 Validando dependencias MCP...")
    results = validate_dependencies()
    
    if results["failed"]:
        print(f"\n❌ {len(results['failed'])} dependencias fallaron")
        sys.exit(1)
    else:
        print(f"\n✅ Todas las {len(results['success'])} dependencias están disponibles")
        sys.exit(0)