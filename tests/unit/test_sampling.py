from src.recommenders.improved_fallback_exclude_seen import smart_sample_across_categories

# Mock products
products = []
for i in range(30):
    cat = ["VESTIDOS LARGOS", "VESTIDOS CORTOS", "VESTIDOS MIDIS"][i % 3]
    products.append({
        "id": str(1000 + i),
        "product_type": cat,
        "title": f"Product {i}"
    })

# Test: Distribución equitativa
categories = ["VESTIDOS LARGOS", "VESTIDOS CORTOS", "VESTIDOS MIDIS"]
result = smart_sample_across_categories(products, categories, n=9, exclude_products=set())

print(f"Total products: {len(result)}")
assert len(result) == 9

# Contar por categoría
from collections import Counter
cats = Counter(p["product_type"] for p in result)
print(f"Distribution: {dict(cats)}")
assert len(cats) == 3  # Debe haber de las 3 categorías

# Verificar que no hay duplicados
ids = [p["id"] for p in result]
assert len(ids) == len(set(ids))

print("✅ Sampling tests passed!")