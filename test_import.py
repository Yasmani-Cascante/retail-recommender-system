from src.recommenders.improved_fallback_exclude_seen import (
    ImprovedFallbackStrategies,
    extract_categories_from_query,
    smart_sample_across_categories,
    get_concrete_categories
)

print("✅ Imports exitosos")
print(f"✅ Categorías concretas: {len(get_concrete_categories())}")