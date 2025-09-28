#!/usr/bin/env python3
"""
Quick test script para verificar que se resolvió el circular import
"""

import sys
import os
from pathlib import Path

# Añadir el directorio raíz al Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / 'src'))

print("🧪 Testing circular import resolution...")

try:
    print("1. Testing basic imports...")
    
    print("   - Importing main_unified_redis...")
    from src.api import main_unified_redis
    print("   ✅ main_unified_redis imported successfully")
    
    print("   - Importing ServiceFactory...")
    from src.api.factories.service_factory import ServiceFactory
    print("   ✅ ServiceFactory imported successfully")
    
    print("   - Importing MCPPersonalizationEngine...")
    from src.api.mcp.engines.mcp_personalization_engine import MCPPersonalizationEngine
    print("   ✅ MCPPersonalizationEngine imported successfully")
    
    print("\n✅ ALL IMPORTS SUCCESSFUL - Circular import resolved!")
    
except ImportError as e:
    print(f"\n❌ IMPORT ERROR: {e}")
    print("   Circular import still exists")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ OTHER ERROR: {e}")
    sys.exit(1)

print("\n🎉 Test completed successfully!")
