"""
check_missing_images.py
========================
Verifica, con certeza, que productos del catalogo TF-IDF en produccion
carecen de image_url -- y si alguno en particular (por nombre/handle) esta
entre ellos.

Uso:
    1. Descargar el pickle real de produccion (el mismo que usa el servicio):

        gsutil cp gs://retail-recommendations-449216-tfidf-model/tfidf-model/tfidf_model.pkl .

       (requiere estar autenticado: `gcloud auth application-default login`
       o tener las credenciales que ya usas para el resto del proyecto)

    2. Correr este script en la misma carpeta:

        python check_missing_images.py tfidf_model.pkl

Que hace:
    - Carga el pickle (mismo formato que TFIDFRecommender.fit() escribe:
      vectorizer, product_vectors, product_data, product_ids, synced_at,
      product_count -- no requiere sklearn instalado, solo lee product_data).
    - Cuenta cuantos productos tienen / no tienen image_url.
    - Busca por nombre (coincidencia parcial, sin importar mayusculas/tildes)
      los productos que le interesan y muestra su estado exacto.
    - Guarda la lista completa de productos sin imagen en
      productos_sin_imagen.csv, para revisarla en Excel/Sheets si hace falta.
"""
import pickle
import sys
import csv
import unicodedata
import shutil
import subprocess
from pathlib import Path


DEFAULT_BUCKET_PICKLE = "gs://retail-recommendations-449216-tfidf-model/tfidf-model/tfidf_model.pkl"
DEFAULT_LOCAL_PICKLE = "tfidf_model.pkl"


def normalize(s: str) -> str:
    """Minusculas y sin tildes, para buscar por nombre sin depender de acentos exactos."""
    s = s or ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.lower()


def main():
    pickle_path = sys.argv[1] if len(sys.argv) >= 2 else DEFAULT_LOCAL_PICKLE

    # With no local file, download the production pickle from the configured bucket.
    if pickle_path == DEFAULT_LOCAL_PICKLE and not Path(pickle_path).is_file():
        gsutil = shutil.which("gsutil")
        if gsutil is None:
            print(
                f"No existe '{pickle_path}' y no se encontro gsutil. "
                "Pasa la ruta local del pickle o instala/configura Google Cloud CLI."
            )
            sys.exit(1)

        print(f"Descargando el modelo desde {DEFAULT_BUCKET_PICKLE}...")
        result = subprocess.run(
            [gsutil, "cp", DEFAULT_BUCKET_PICKLE, pickle_path],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print("No se pudo descargar el pickle desde el bucket.")
            if result.stderr:
                print(result.stderr.strip())
            sys.exit(result.returncode)

    if not Path(pickle_path).is_file():
        print(f"No existe el archivo pickle: {pickle_path}")
        sys.exit(1)

    with open(pickle_path, "rb") as f:
        data = pickle.load(f)

    product_data = data.get("product_data")
    synced_at = data.get("synced_at")
    product_count = data.get("product_count")

    if product_data is None:
        print("ERROR: el pickle no tiene la clave 'product_data' -- ¿es el archivo correcto?")
        sys.exit(1)

    print(f"synced_at del pickle: {synced_at}")
    print(f"product_count declarado: {product_count}")
    print(f"productos reales en product_data: {len(product_data)}")
    print()

    con_imagen = []
    sin_imagen = []
    for p in product_data:
        img = p.get("image_url") or p.get("imageUrl")
        if img and str(img).startswith("http"):
            con_imagen.append(p)
        else:
            sin_imagen.append(p)

    print(f"Con imagen:  {len(con_imagen)}")
    print(f"Sin imagen:  {len(sin_imagen)}")
    print()

    # Busqueda especifica de los productos en cuestion
    objetivos = [
        "aros dalia gasa blanco",
        "aros dalia gasa crema",
        "aros daniela argolla dorado",
        "Aros Daniela Argolla Dorado",
        "AROS DALIA GASA BLANCO",
    ]

    print("=" * 70)
    print("BUSQUEDA ESPECIFICA")
    print("=" * 70)
    for objetivo in objetivos:
        obj_norm = normalize(objetivo)
        encontrados = [
            p for p in product_data
            if obj_norm in normalize(p.get("title", ""))
        ]
        if not encontrados:
            print(f"\n'{objetivo}': NO ENCONTRADO en el catalogo (ni con ni sin imagen)")
            continue
        for p in encontrados:
            img = p.get("image_url") or p.get("imageUrl")
            tiene_imagen = bool(img and str(img).startswith("http"))
            print(f"\n'{p.get('title')}'")
            print(f"    id: {p.get('id')}")
            print(f"    handle: {p.get('handle', 'N/D')}")
            print(f"    product_type: {p.get('product_type', 'N/D')}")
            print(f"    tiene imagen: {'SI -> ' + str(img) if tiene_imagen else 'NO'}")

    # Guardar el listado completo de productos sin imagen
    out_csv = "productos_sin_imagen.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "title", "handle", "product_type"])
        for p in sin_imagen:
            writer.writerow([
                p.get("id", ""),
                p.get("title", ""),
                p.get("handle", ""),
                p.get("product_type", ""),
            ])
    print(f"\n\nListado completo de los {len(sin_imagen)} productos sin imagen guardado en: {out_csv}")


if __name__ == "__main__":
    main()
