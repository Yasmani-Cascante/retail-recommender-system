# test_diverse_smart.py
import asyncio
from src.recommenders.improved_fallback_exclude_seen import ImprovedFallbackStrategies

async def test_smart_diversification():
    # Mock products
    products = []
    for i in range(40):
        cat = ["VESTIDOS LARGOS", "VESTIDOS CORTOS", "ZAPATOS", "CLUTCH"][i % 4]
        products.append({
            "id": str(1000 + i),
            "product_type": cat,
            "title": f"Product {cat} {i}",
            "body_html": f"Description {i}",
            "variants": [{"price": "25.00"}]
        })
    
    # Test 1: Sin query (diversification estándar)
    print("\n🧪 TEST 1: Standard diversification (sin query)")
    result = await ImprovedFallbackStrategies.get_diverse_category_products(
        products=products,
        n=8,
        exclude_products=set()
    )
    
    print(f"   Results: {len(result)}")
    categories = set(p["category"] for p in result)
    print(f"   Categories: {categories}")
    assert len(result) == 8
    assert len(categories) >= 2  # Debe haber diversidad
    print("   ✅ PASSED")
    
    # Test 2: Con query (smart diversification)
    print("\n🧪 TEST 2: Smart diversification (con query 'vestidos elegantes')")
    result = await ImprovedFallbackStrategies.get_diverse_category_products(
        products=products,
        n=8,
        exclude_products=set(),
        user_query="vestidos elegantes"  # Debería priorizar VESTIDOS
    )
    
    print(f"   Results: {len(result)}")
    categories = set(p["category"] for p in result)
    print(f"   Categories: {categories}")
    
    # Contar vestidos vs otros
    vestidos_count = sum(1 for p in result if "VESTIDO" in p["category"])
    print(f"   Vestidos: {vestidos_count}/{len(result)}")
    
    assert len(result) == 8
    assert vestidos_count >= 4  # Al menos mitad deberían ser vestidos
    assert result[0]["recommendation_type"] == "smart_diverse_fallback"
    print("   ✅ PASSED")
    
    # Test 3: Con query de múltiples categorías
    print("\n🧪 TEST 3: Smart diversification (query 'zapatos y bolsos')")
    result = await ImprovedFallbackStrategies.get_diverse_category_products(
        products=products,
        n=6,
        exclude_products=set(),
        user_query="zapatos y bolsos"
    )
    
    print(f"   Results: {len(result)}")
    categories = set(p["category"] for p in result)
    print(f"   Categories: {categories}")
    
    # Verificar que incluye ZAPATOS y CLUTCH
    has_zapatos = any("ZAPATOS" in p["category"] for p in result)
    has_clutch = any("CLUTCH" in p["category"] for p in result)
    
    assert len(result) == 6
    assert has_zapatos, "Debería incluir ZAPATOS"
    assert has_clutch, "Debería incluir CLUTCH"
    print("   ✅ PASSED")
    
    print("\n" + "="*60)
    print("✅ ALL TESTS PASSED - Smart diversification funcionando correctamente")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_smart_diversification())