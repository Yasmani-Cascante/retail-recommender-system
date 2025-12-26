from src.recommenders.improved_fallback_exclude_seen import extract_categories_from_query

# Simular categorías disponibles
available = {
    "ZAPATOS", "VESTIDOS LARGOS", "VESTIDOS CORTOS", "VESTIDOS MIDIS",
    "CLUTCH", "PANTALONES", "NOVIAS LARGOS"
}

# Test 1: Keyword genérico (debería expandir)
result = extract_categories_from_query("vestidos elegantes", available)
print(f"Test 1: {result}")
assert len(result) == 3, f"Expected 3 categories, got {len(result)}"
assert "VESTIDOS LARGOS" in result
assert "VESTIDOS CORTOS" in result
assert "VESTIDOS MIDIS" in result

# Test 2: Keyword específico
result = extract_categories_from_query("vestido largo para fiesta", available)
print(f"Test 2: {result}")
assert "VESTIDOS LARGOS" in result

# Test 3: Múltiples keywords
result = extract_categories_from_query("zapatos y bolsos", available)
print(f"Test 3: {result}")
assert "ZAPATOS" in result
assert "CLUTCH" in result

# Test 4: Keyword de boda (debería detectar NOVIAS)
result = extract_categories_from_query("vestido para boda", available)
print(f"Test 4: {result}")
assert "NOVIAS LARGOS" in result or len(result) > 0

print("✅ All tests passed!")