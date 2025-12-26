# Crear script temporal para validar estructura
from src.recommenders.improved_fallback_exclude_seen import CATEGORY_KEYWORDS, get_concrete_categories, get_parent_categories

# Validar estructura
print("🔍 Validando estructura...")
for category, config in CATEGORY_KEYWORDS.items():
    assert "type" in config, f"Missing 'type' in {category}"
    assert "keywords" in config, f"Missing 'keywords' in {category}"
    assert config["type"] in ["parent", "concrete"], f"Invalid type in {category}"
    
    if config["type"] == "parent":
        assert "subcategories" in config, f"Parent {category} missing subcategories"
        assert len(config["subcategories"]) > 0, f"Parent {category} has empty subcategories"

print(f"✅ Estructura válida")
print(f"✅ Total categorías: {len(CATEGORY_KEYWORDS)}")
print(f"✅ Categorías concretas: {len(get_concrete_categories())}")
print(f"✅ Categorías padre: {len(get_parent_categories())}")

