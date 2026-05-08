"""
validate_visual_search.py — Test de calidad del índice FAISS fashionSigLIP.

Ejecutar localmente con acceso al embedding-service activo:
  python validate_visual_search.py [SERVICE_URL]

PREREQUISITOS:
  - COLBERT_SERVICE_URL configurado (o URL como primer argumento):
      export COLBERT_SERVICE_URL="https://retail-embedding-service-178362262166.us-central1.run.app"
      python validate_visual_search.py
  - El embedding-service debe tener visual_index_size > 0
  - El catálogo pickle en data/tfidf_model.pkl

MÉTRICAS CALCULADAS:
  - Recall@1   — ¿El primer resultado es el mismo producto?
  - Recall@5   — ¿El producto aparece en los top-5?
  - Intra-category@10 — ¿Los top-10 son del mismo tipo de prenda?
  - Latencia de PROCESAMIENTO del servidor (campo latency_ms de la respuesta JSON)

POR QUÉ SE USA latency_ms DEL SERVIDOR y NO el tiempo del script:
  Este script corre localmente (Ginebra → us-central1). La "latencia" que
  mediría el script incluye:
    1. Descarga de imagen del CDN de Shopify (imágenes de catálogo: 1-11MB)
    2. Upload Ginebra → us-central1 (~100-200ms overhead de red)
    3. Procesamiento del embedding-service (lo que importa)
  El usuario final NO paga los costes 1 y 2 (sube su propia foto desde su
  dispositivo, y el monolito envía los bytes por red interna Cloud Run ~2ms).
  Por eso se usa el campo `latency_ms` que devuelve el servidor: es el tiempo
  PURO de procesamiento (preprocess + ViT forward pass + FAISS search), que
  es exactamente lo que experimenta el usuario final.

UMBRALES (del plan VISUAL_SEARCH_PLAN_OPcionA_22042026.md):
  Recall@1  > 85%   — el modelo reconoce sus propias imágenes
  Recall@5  > 95%   — robustez ante variaciones
  Intra-cat > 70%   — resultados de la misma categoría de prenda
  p50       < 500ms — latencia de procesamiento aceptable
  p95       < 800ms — latencia de procesamiento en el peor caso

VALIDADO EN PRODUCCIÓN (01/05/2026, 83 requests):
  Recall@1:  100%  ✅
  Recall@5:  100%  ✅
  Intra-cat: 78.5% ✅
  p50:       435ms ✅
  p95:       614ms ✅
"""

import asyncio
import os
import pickle
import random
import sys
import time
from pathlib import Path
from typing import List, Optional

import httpx


# ─── Configuración ─────────────────────────────────────────────────────────────

SERVICE_URL = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.environ.get(
        "COLBERT_SERVICE_URL",
        "https://retail-embedding-service-178362262166.us-central1.run.app",
    )
)
CATALOG_PATH = Path("data/tfidf_model.pkl")

SAMPLE_SIZE = 100
TOP_K       = 10

RECALL_1_THRESHOLD  = 0.85
RECALL_5_THRESHOLD  = 0.95
INTRA_CAT_THRESHOLD = 0.70
P50_THRESHOLD_MS    = 500
P95_THRESHOLD_MS    = 800


# ─── Helpers ───────────────────────────────────────────────────────────────────

async def check_service_ready(client: httpx.AsyncClient) -> bool:
    try:
        resp = await client.get("/health", timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        ready = data.get("visual_index_ready", False)
        size  = data.get("visual_index_size", 0)
        print(f"  Health check: visual_index_ready={ready}, visual_index_size={size}")
        return ready
    except Exception as e:
        print(f"  ❌ Health check failed: {e}")
        return False


async def search_image_direct(
    client: httpx.AsyncClient,
    image_bytes: bytes,
    top_k: int = TOP_K,
) -> Optional[dict]:
    """
    Llama al embedding-service y retorna el dict completo de la respuesta.

    La respuesta incluye `latency_ms` — latencia de PROCESAMIENTO puro:
      preprocess(img) + encode_image(ViT) + FAISS.search()
    Esto es lo que el usuario final experimenta (la red interna de Cloud Run
    añade <5ms y no es relevante).

    NO se usa time.time() del script: ese tiempo incluye la descarga
    del CDN de Shopify y la latencia de red Ginebra→us-central1 (~100-200ms),
    que el usuario final no paga.

    Formato multipart correcto (FastAPI UploadFile + Form):
      files={'file': ('query.jpg', bytes, 'image/jpeg')}
      data={'top_k': str(top_k)}
    """
    try:
        resp = await client.post(
            "/v1/embed/search-image",
            files={"file": ("query.jpg", image_bytes, "image/jpeg")},
            data={"top_k": str(top_k)},
            timeout=30.0,  # Generoso para el upload desde local (imagen de catálogo, no del browser)
        )
        resp.raise_for_status()
        return resp.json()   # Incluye: product_ids, latency_ms, visual_index_size
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 413:
            print(f"    413: imagen demasiado grande ({len(image_bytes)//1024}KB > 5MB)")
        elif e.response.status_code == 503:
            print(f"    503: índice no construido")
        else:
            print(f"    HTTP {e.response.status_code}: {e.response.text[:80]}")
        return None
    except Exception as e:
        print(f"    Error: {e}")
        return None


# ─── Test principal ─────────────────────────────────────────────────────────────

async def validate():
    print("=" * 65)
    print("VISUAL SEARCH VALIDATION")
    print("=" * 65)
    print(f"Service URL:  {SERVICE_URL}")
    print(f"Catalog:      {CATALOG_PATH}")
    print(f"Sample size:  {SAMPLE_SIZE} productos")
    print(f"Latencia:     server-side (campo latency_ms de la respuesta)")
    print()

    if not CATALOG_PATH.exists():
        print(f"❌ Catálogo no encontrado en {CATALOG_PATH}")
        print("   Ejecutar desde la raíz del proyecto.")
        sys.exit(1)

    with open(CATALOG_PATH, "rb") as f:
        data = pickle.load(f)

    products = [
        p for p in data.get("product_data", [])
        if p.get("image_url") and str(p.get("image_url", "")).startswith("http")
    ]
    print(f"✅ Catálogo cargado: {len(products)} productos con image_url")

    sample = random.sample(products, min(SAMPLE_SIZE, len(products)))
    print(f"   Muestreo aleatorio: {len(sample)} productos")
    print()

    async with httpx.AsyncClient(base_url=SERVICE_URL) as client:
        print("Verificando servicio...")
        if not await check_service_ready(client):
            print("❌ El índice no está listo. Lanza POST /v1/embed/index-images primero.")
            sys.exit(1)
        print("✅ Servicio listo\n")

        recall_1 = recall_5 = recall_10 = 0
        intra_cat_total = 0.0
        server_latencies: List[float] = []   # latency_ms de la respuesta JSON
        skipped = 0

        id_index = {str(p.get("id","")): p for p in products}

        print(f"{'#':>4}  {'Producto':<40} R@1  Intra  lat(srv)")
        print("-" * 72)

        async with httpx.AsyncClient(base_url=SERVICE_URL) as dl_client:
            for i, product in enumerate(sample):
                pid   = str(product.get("id", ""))
                title = product.get("title", "")[:38]
                ptype = product.get("product_type","") or product.get("category","")

                # Descargar imagen del catálogo para el test
                try:
                    img_resp = await dl_client.get(product["image_url"], timeout=20.0)
                    img_resp.raise_for_status()
                    image_bytes = img_resp.content
                except Exception as e:
                    print(f"{i+1:>4}  {title:<40} SKIP (download: {e})")
                    skipped += 1
                    continue

                # Buscar por imagen — se usa latency_ms del servidor, no time() local
                result = await search_image_direct(dl_client, image_bytes)
                if result is None:
                    skipped += 1
                    continue

                result_ids = result.get("product_ids", [])
                # latency_ms del servidor = tiempo de PROCESAMIENTO PURO
                srv_lat = result.get("latency_ms", 0.0)
                server_latencies.append(srv_lat)

                r1  = 1 if result_ids and result_ids[0] == pid else 0
                r5  = 1 if pid in result_ids[:5] else 0
                r10 = 1 if pid in result_ids[:10] else 0
                recall_1  += r1
                recall_5  += r5
                recall_10 += r10

                # Precisión intra-categoría
                same_cat = sum(
                    1 for rid in result_ids[:10]
                    if id_index.get(rid, {}).get("product_type","") == ptype and ptype
                )
                intra = same_cat / max(len(result_ids[:10]), 1)
                intra_cat_total += intra

                print(f"{i+1:>4}  {title:<40}  {'✅' if r1 else '❌'}   {intra:.0%}  {srv_lat:.0f}ms")

    n = len(server_latencies)
    if n == 0:
        print("\n❌ Ningún producto pudo validarse.")
        sys.exit(1)

    sl     = sorted(server_latencies)
    p50    = sl[int(n * 0.50)]
    p95    = sl[int(n * 0.95)]

    r1_rate     = recall_1  / n
    r5_rate     = recall_5  / n
    r10_rate    = recall_10 / n
    intra_rate  = intra_cat_total / n

    print()
    print("=" * 65)
    print("RESULTADOS")
    print("=" * 65)
    print()
    print(f"  Productos testados:   {n}  ({skipped} omitidos)")
    print()
    print("  CALIDAD DEL ÍNDICE:")

    def chk(label, val, thr, fmt=".1%"):
        icon  = "✅" if val >= thr else "❌"
        v_str = f"{val:{fmt}}" if fmt == ".1%" else f"{val:.0f}ms"
        t_str = f"{thr:{fmt}}" if fmt == ".1%" else f"{thr:.0f}ms"
        print(f"  {icon} {label:<30} {v_str:>7}   (umbral: >{t_str})")

    chk("Recall@1",                  r1_rate,    RECALL_1_THRESHOLD)
    chk("Recall@5",                  r5_rate,    RECALL_5_THRESHOLD)
    chk("Recall@10",                 r10_rate,   0.99)
    chk("Precisión intra-categoría", intra_rate, INTRA_CAT_THRESHOLD)

    print()
    print("  LATENCIA DE PROCESAMIENTO (server-side):")
    print("  (ViT encode + FAISS search — lo que experimenta el usuario final)")

    def chk_lat(label, val, thr):
        icon = "✅" if val <= thr else "❌"
        print(f"  {icon} {label:<30} {val:>7.0f}ms (umbral: <{thr:.0f}ms)")

    chk_lat("p50",  p50,   P50_THRESHOLD_MS)
    chk_lat("p95",  p95,   P95_THRESHOLD_MS)
    chk_lat("min",  sl[0], P50_THRESHOLD_MS)
    chk_lat("max",  sl[-1],P95_THRESHOLD_MS)

    passes = all([
        r1_rate    >= RECALL_1_THRESHOLD,
        r5_rate    >= RECALL_5_THRESHOLD,
        intra_rate >= INTRA_CAT_THRESHOLD,
        p50 <= P50_THRESHOLD_MS,
        p95 <= P95_THRESHOLD_MS,
    ])

    print()
    if passes:
        print("  ✅ TODOS LOS UMBRALES SUPERADOS")
        print("     Sistema listo para VISUAL_SEARCH_ENABLED=true")
    else:
        print("  ❌ ALGÚN UMBRAL NO SUPERADO — investigar antes de activar")
    print()


if __name__ == "__main__":
    asyncio.run(validate())
