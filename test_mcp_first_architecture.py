#!/usr/bin/env python3
"""
Test completo de la arquitectura MCP-First
"""

import sys
import os
import asyncio
sys.path.append('src')

async def test_mcp_first_architecture():
    print("🧪 Testing MCP-First Architecture...")
    
    try:
        # Test import de la nueva arquitectura
        from api.mcp_services.orchestration.mcp_adapter import MCPMarketAdapter
        from api.mcp_services.models import MCPConversationContext, MarketContext, MarketTier
        
        print("✅ Import de MCP services exitoso")
        
        # Test product
        test_product = {
            "id": "test-123",
            "title": "Blue cotton shirt",
            "price": 50.0,
            "currency": "USD"
        }
        
        # Crear adapter
        adapter = MCPMarketAdapter()
        
        # Test market context
        market_context = await adapter.market_config_service.get_market_context("ES")
        print(f"✅ Market context: {market_context.market_id} - {market_context.currency}")
        
        # Test MCP conversation context
        mcp_context = MCPConversationContext(
            session_id="test-session-123",
            user_intent="looking_for_casual_clothing",
            conversation_history=[],
            market_context=market_context,
            personalization_data={}
        )
        
        # Test adaptación MCP
        result = await adapter.adapt_product_for_mcp_conversation(test_product, mcp_context)
        
        print(f"✅ Adaptación MCP exitosa:")
        print(f"   Original: ${test_product['price']} USD")
        print(f"   Adapted: {result.adapted_product.get('price')} {result.adapted_product.get('currency')}")
        print(f"   Market adapted: {result.adapted_product.get('market_adapted')}")
        print(f"   Adaptations: {result.adaptations_applied}")
        print(f"   Services used: {len(result.adaptation_metadata['service_boundaries_used'])}")
        
        # Test compatibility layer
        from api.utils.market_utils_mcp_first import adapt_product_for_market
        
        legacy_result = adapt_product_for_market(test_product, "ES")
        print(f"✅ Compatibility layer:")
        print(f"   Legacy result market_adapted: {legacy_result.get('market_adapted')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error en testing: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_service_boundaries():
    print("\n🔍 Testing Service Boundaries...")
    
    try:
        from api.mcp_services.market_config.service import MarketConfigService
        from api.mcp_services.currency.service import CurrencyConversionService
        
        # Test Market Config Service
        market_service = MarketConfigService()
        context = await market_service.get_market_context("MX")
        print(f"✅ Market Service: {context.market_id} - Tier {context.tier.value}")
        
        # Test Currency Service
        currency_service = CurrencyConversionService()
        conversion = await currency_service.convert_price(100.0, "USD", "EUR")
        print(f"✅ Currency Service: $100 USD = €{conversion['converted_amount']} EUR")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing service boundaries: {e}")
        return False

if __name__ == "__main__":
    async def run_all_tests():
        success1 = await test_mcp_first_architecture()
        success2 = await test_service_boundaries()
        return success1 and success2
    
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
