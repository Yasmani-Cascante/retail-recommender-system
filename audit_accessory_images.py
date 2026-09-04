import pickle
from collections import defaultdict

ACCESSORY_DETAIL_TYPES = {
    "BRAZALETE", "BRAZALETES", "ALAS DE NOVIA", "AROMAS", "AROS",
    "COLLARES", "CINTURONES", "TOCADOS", "CARTERAS", "CLUTCH",
}

with open("data/tfidf_model.pkl", "rb") as f:
    data = pickle.load(f)
products = data["product_data"]

by_type = defaultdict(list)
for p in products:
    ptype = str(p.get("product_type", "")).upper().strip()
    if ptype in ACCESSORY_DETAIL_TYPES:
        images = p.get("images") or []
        by_type[ptype].append({
            "title": p.get("title", ""),
            "n_images": len(images),
            "image_0": images[0].get("src") if images and len(images) > 0 else None,
            "image_1": images[1].get("src") if images and len(images) > 1 else None,
        })

for ptype, items in sorted(by_type.items()):
    n_with_2plus = sum(1 for i in items if i["n_images"] >= 2)
    print(f"\n=== {ptype} ({len(items)} productos, {n_with_2plus} con ≥2 imágenes) ===")
    for item in items[:3]:  # muestra de 3 por tipo
        print(f"  {item['title']}")
        print(f"    [0] {item['image_0']}")
        print(f"    [1] {item['image_1']}")