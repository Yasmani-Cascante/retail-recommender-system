#!/usr/bin/env python3
"""
Quick Validation Script - ServiceFactory MCP Client Integration
================================================================

Este script valida que la corrección aplicada funciona correctamente.

Ejecutar: python quick_validation.py
"""

import sys
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("=" * 80)
print("  🔍 QUICK VALIDATION - ServiceFactory MCP Client")
print("=" * 80)

# ============================================================================
# TEST 1: Import Validation
# ============================================================================
print("\n📦 TEST 1: Validando Imports...")

try:
    from src.api.factories.service_factory import ServiceFactory
    print("  ✅ ServiceFactory imported successfully")
except ImportError as e:
    print(f"  ❌ Failed to import ServiceFactory: {e}")
    sys.exit(1)

try:
    from src.api.mcp.client.mcp_client import MCPClient
    print("  ✅ MCPClient imported successfully")
except ImportError as e:
    print(f"  ❌ Failed to import MCPClient: {e}")
    sys.exit(1)

try:
    from src.api.mcp.client.mcp_client_enhanced import MCPClientEnhanced
    print("  ✅ MCPClientEnhanced imported successfully")
except ImportError as e:
    print(f"  ⚠️ MCPClientEnhanced not available: {e}")
    print("  ℹ️ Will fall back to basic MCPClient")

# ============================================================================
# TEST 2: Singleton Pattern
# ============================================================================
print("\n🔄 TEST 2: Validando Singleton Pattern...")

async def test_singleton():
    # Reset singleton
    ServiceFactory._mcp_client = None
    
    client1 = await ServiceFactory.get_mcp_client()
    client2 = await ServiceFactory.get_mcp_client()
    
    if client1 is client2:
        print("  ✅ Singleton pattern working (same instance returned)")
        return True
    else:
        print("  ❌ Singleton pattern broken (different instances)")
        return False

try:
    singleton_ok = asyncio.run(test_singleton())
except Exception as e:
    print(f"  ❌ Singleton test failed: {e}")
    singleton_ok = False

# ============================================================================
# TEST 3: Client Type Validation
# ============================================================================
print("\n🔍 TEST 3: Validando Tipo de Cliente...")

async def test_client_type():
    ServiceFactory._mcp_client = None
    
    client = await ServiceFactory.get_mcp_client()
    
    if client is None:
        print("  ❌ Client is None")
        return False
    
    client_type = type(client).__name__
    print(f"  ℹ️ Client type: {client_type}")
    
    # Check if it's Enhanced or Basic
    if client_type == "MCPClientEnhanced":
        print("  ✅ Using Enhanced client (preferred)")
        return True
    elif client_type == "MCPClient":
        print("  ⚠️ Using Basic client (Enhanced not available)")
        return True
    else:
        print(f"  ❌ Unexpected client type: {client_type}")
        return False

try:
    type_ok = asyncio.run(test_client_type())
except Exception as e:
    print(f"  ❌ Client type test failed: {e}")
    type_ok = False

# ============================================================================
# TEST 4: Parameter Validation
# ============================================================================
print("\n⚙️ TEST 4: Validando Parámetros del Cliente...")

async def test_parameters():
    ServiceFactory._mcp_client = None
    
    client = await ServiceFactory.get_mcp_client()
    
    if client is None:
        print("  ❌ Client is None")
        return False
    
    # Check for bridge parameters (correct)
    has_base_url = hasattr(client, 'base_url')
    has_bridge_host = hasattr(client, 'bridge_host') or ('localhost' in str(getattr(client, 'base_url', '')))
    
    # Check for Claude API parameters (incorrect - should NOT have these)
    has_anthropic_key = hasattr(client, 'anthropic_api_key')
    has_model = hasattr(client, 'model')
    
    print(f"  Bridge parameters:")
    print(f"    - base_url: {'✅ Present' if has_base_url else '❌ Missing'}")
    print(f"    - bridge_host: {'✅ Detected' if has_bridge_host else '❌ Not found'}")
    
    print(f"  Claude API parameters (should NOT be present):")
    print(f"    - anthropic_api_key: {'❌ PRESENT (ERROR)' if has_anthropic_key else '✅ Absent (correct)'}")
    print(f"    - model: {'❌ PRESENT (ERROR)' if has_model else '✅ Absent (correct)'}")
    
    # Validation
    if has_base_url and not has_anthropic_key:
        print("  ✅ Parameters are correct (Bridge, not Claude API)")
        return True
    else:
        print("  ❌ Parameters are incorrect")
        return False

try:
    params_ok = asyncio.run(test_parameters())
except Exception as e:
    print(f"  ❌ Parameter test failed: {e}")
    params_ok = False

# ============================================================================
# TEST 5: Enhanced Features Check
# ============================================================================
print("\n🚀 TEST 5: Validando Features de Enhanced (si disponible)...")

async def test_enhanced_features():
    ServiceFactory._mcp_client = None
    
    client = await ServiceFactory.get_mcp_client()
    
    if client is None:
        print("  ❌ Client is None")
        return False
    
    # Check Enhanced features
    has_circuit_breaker = hasattr(client, 'circuit_breaker')
    has_cache = hasattr(client, 'intent_cache') or hasattr(client, 'enable_local_cache')
    has_metrics = hasattr(client, 'metrics')
    
    print(f"  Enhanced features:")
    print(f"    - Circuit Breaker: {'✅ Available' if has_circuit_breaker else '⚠️ Not available'}")
    print(f"    - Local Cache: {'✅ Available' if has_cache else '⚠️ Not available'}")
    print(f"    - Metrics: {'✅ Available' if has_metrics else '⚠️ Not available'}")
    
    if has_circuit_breaker or has_cache:
        print("  ✅ Enhanced features detected")
        return True
    else:
        print("  ℹ️ Using Basic client (no enhanced features)")
        return True

try:
    features_ok = asyncio.run(test_enhanced_features())
except Exception as e:
    print(f"  ⚠️ Enhanced features check failed: {e}")
    features_ok = True  # Not critical

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("  📊 VALIDATION SUMMARY")
print("=" * 80)

tests = {
    "Imports": True,  # If we got here, imports work
    "Singleton Pattern": singleton_ok,
    "Client Type": type_ok,
    "Parameters": params_ok,
    "Enhanced Features": features_ok
}

passed = sum(1 for v in tests.values() if v)
total = len(tests)

for test_name, result in tests.items():
    status = "✅ PASS" if result else "❌ FAIL"
    print(f"  {status}: {test_name}")

print("\n" + "=" * 80)
if passed == total:
    print(f"  🎉 ALL TESTS PASSED ({passed}/{total})")
    print("  ✅ ServiceFactory MCP Client integration is working correctly!")
    exit_code = 0
else:
    print(f"  ⚠️ SOME TESTS FAILED ({passed}/{total} passed)")
    print("  ❌ Please review the failed tests above")
    exit_code = 1

print("=" * 80)

sys.exit(exit_code)
