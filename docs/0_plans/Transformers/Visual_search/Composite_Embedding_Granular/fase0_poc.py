#!/usr/bin/env python3
"""
FASE 0 — Prueba de concepto aislada: Composite Embedding Granular (Gap C)
===========================================================================

Que hace: para un producto ancla de la familia ACCESSORIES (ej. un Collar),
compara 3 busquedas visuales:

  1. PLANA         -- search_by_product_id() ya existente, sin cambios.
  2. COMPOSITE 0.6 -- vector imagen + vector texto especifico del tipo
                      (ej. "AROS": "earrings aros pendientes...") con
                      alpha=0.6 (60% imagen, 40% texto).
  3. COMPOSITE 0.4 -- igual que arriba pero alpha=0.4 (40% imagen, 60%
                      texto) -- mas peso semantico, menos peso visual.

Y cuenta cuantos de los primeros 10 resultados de cada busqueda son
REALMENTE del tipo del ancla (ej. cuantos son AROS de verdad), usando el
propio product_type de Shopify como fuente de verdad (via Admin API).

IMPORTANTE -- que NO hace este script:
  - No modifica visual_retriever.py ni ningun archivo de produccion.
  - No modifica el indice FAISS ni sube nada a GCS.
  - No toca el embedding-service desplegado -- corre 100% localmente,
    cargando el mismo modelo e indice que usa produccion, en modo lectura.

Como correrlo (desde la raiz del repo, con el entorno del embedding-service
activo -- mismas dependencias que requirements.txt de ese servicio):

    cd src/api/services/embedding-service
    python /ruta/a/fase0_poc.py --product-id 9978485440821 --boost-category COLLARES

Requiere:
  - Acceso a Hugging Face Hub (para descargar marqo-fashionSigLIP la
    primera vez -- se cachea localmente despues).
  - Credenciales GCP (ADC: `gcloud auth application-default login`) con
    permiso de lectura sobre el bucket VISUAL_INDEX_BUCKET, para descargar
    el indice FAISS si no existe ya en /tmp/visual-index.
  - Opcional: SHOPIFY_ACCESS_TOKEN + SHOPIFY_SHOP_URL en el entorno, para
    resolver titulos/tipos reales de los productos via Admin API. Sin
    esto, el script igual funciona pero solo imprime IDs crudos.

Variables de entorno relevantes (mismas que usa el servicio real):
    VISUAL_INDEX_BUCKET   -- bucket GCS del indice (confirmar el nombre
                             real antes de correr -- se recuerda como
                             "retail-recommendations-449216-visual-index"
                             pero no se verifico en esta sesion)
    SHOPIFY_ACCESS_TOKEN  -- opcional, para lookup de tipo/titulo real
    SHOPIFY_SHOP_URL      -- opcional, default "ai-shoppings.myshopify.com"
"""
import argparse
import asyncio
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np

# ─────────────────────────────────────────────────────────────────────────
# Import del modulo REAL del embedding-service -- no se reimplementa nada
# de la carga del modelo/indice, para evitar cualquier desvio respecto a
# como funciona en produccion. Asume que este script corre desde un
# directorio desde el cual visual_retriever.py es importable (ver
# docstring de arriba -- correrlo con cwd en
# src/api/services/embedding-service/, o ajustar sys.path abajo).
# ─────────────────────────────────────────────────────────────────────────
_THIS_DIR = Path(__file__).resolve().parent
_THIS_DIR = Path(__file__).resolve().parent

# Try multiple candidate locations for `visual_retriever.py` so the script
# can be executed from different working directories (repo root, service
# folder, or the docs folder). We walk up parent folders looking for the
# real `src/api/services/embedding-service/visual_retriever.py` file and
# insert that directory into `sys.path` when found.
_found = False
for parent in [_THIS_DIR] + list(_THIS_DIR.parents)[:8]:
    candidate = parent / "src" / "api" / "services" / "embedding-service"
    if (candidate / "visual_retriever.py").exists():
        sys.path.insert(0, str(candidate))
        _found = True
        break

# If not found above, check common runtime locations (current working
# directory) which is helpful when the user runs the script with a
# different cwd.
if not _found:
    cwd_candidate = Path.cwd() / "src" / "api" / "services" / "embedding-service"
    if (cwd_candidate / "visual_retriever.py").exists():
        sys.path.insert(0, str(cwd_candidate))
        _found = True

if not _found and (Path.cwd() / "visual_retriever.py").exists():
    sys.path.insert(0, str(Path.cwd()))
    _found = True

# As a last resort, keep the original behavior of checking the docs
# folder itself (useful if a copy of the module is colocated with the
# plan file).
if not _found and (_THIS_DIR / "visual_retriever.py").exists():
    sys.path.insert(0, str(_THIS_DIR))
    _found = True

try:
    import visual_retriever
    from visual_retriever import FashionSigLIPRetriever
except ImportError:
    print(
        "ERROR: no se pudo importar visual_retriever.py. Corre este script\n"
        "desde la raiz del repo o desde\n"
        "src/api/services/embedding-service/, o ajusta _CANDIDATE_PATHS\n"
        "arriba con la ruta correcta en tu maquina."
    )
    sys.exit(1)


def _load_dotenv_if_present() -> None:
    """
    Carga variables desde .env (raiz del repo) SIN depender de
    python-dotenv -- este es un script de prueba puntual, no vale la pena
    anadir una dependencia nueva solo para esto. Parseo simple KEY=VALUE
    por linea, ignorando comentarios (#) y lineas vacias.

    Sube desde la carpeta de este script (docs/0_plans/.../
    Composite_Embedding_Granular/) por cada nivel de carpeta padre hasta
    encontrar un .env -- deberia encontrar el de la raiz del repo sin
    necesidad de configurar nada mas.

    NO sobreescribe variables que ya esten exportadas en el entorno --
    si corriste `export SHOPIFY_ACCESS_TOKEN=...` a mano, eso tiene
    prioridad sobre el .env.
    """
    search_dirs = [_THIS_DIR] + list(_THIS_DIR.parents)
    for candidate_dir in search_dirs:
        env_path = candidate_dir / ".env"
        if not env_path.exists():
            continue
        loaded = 0
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
                    loaded += 1
        print(f"  (.env encontrado en {env_path} -- {loaded} variables cargadas)")
        return
    print(
        "  (no se encontro .env en ninguna carpeta padre -- usando solo "
        "variables ya exportadas en el entorno, si las hay)"
    )


# ─────────────────────────────────────────────────────────────────────────
# PIEZA 1 del plan (version de PRUEBA, NO se escribe en visual_retriever.py
# todavia -- eso es Fase 1, solo despues de validar aqui con datos reales).
# Mismo patron que CATEGORY_TEXT_PROMPTS, pero por tipo Shopify especifico
# en vez de por bucket generico.
# ─────────────────────────────────────────────────────────────────────────
SHOPIFY_TYPE_TEXT_PROMPTS_POC = {
    "AROS":          "earrings aros pendientes arete jewelry mujer",
    "COLLARES":      "necklace collar cadena gargantilla chain jewelry mujer",
    "BRAZALETES":    "bracelet brazalete pulsera jewelry mujer",
    "BRAZALETE":     "bracelet brazalete pulsera jewelry mujer",
    "CINTURONES":    "belt cinturon correa mujer",
    "TOCADOS":       "headpiece tocado diadema corona hair accessory mujer",
    "ALAS DE NOVIA": "bridal wings alas de novia veil wedding mujer",
    "CARTERAS":      "handbag cartera bolso purse mujer",
    "CLUTCH":        "clutch bag purse mujer",
    # AGREGADO (19/07/2026): caso nuevo -- boost cruzado desde prendas
    # (vestidos) hacia calzado, mucho mas lejos visualmente que los pares
    # ya probados (joyeria-joyeria, joyeria-bolso). ZAPATOS es un tipo
    # unico dentro de su propio bucket "shoes" (sin variantes de subtipo
    # como BRAZALETES/BRAZALETE), asi que el prompt puede ser simple.
    "ZAPATOS":       "shoes zapatos calzado footwear heels tacones mujer",
    # AGREGADO (19/07/2026): idea de estilista -- probar Zapatos como
    # ancla, boost hacia TAPADOS (abrigo/prenda de vestir exterior).
    # CINTURONES ya estaba arriba, reusado tal cual.
    "TAPADOS":       "coat outerwear tapado abrigo chaqueta mujer",
    # AGREGADO (19/07/2026): CORRECCION -- "TAPADOS" resulto NO ser un
    # product_type real en este catalogo (confirmado: 0 apariciones en 40
    # candidatos revisados, pese a que varios TITULOS literalmente dicen
    # "TAPADO"). El product_type real para esas prendas es KIMONOS o
    # CHAQUETAS -- se agregan ambos con prompts propios para repetir la
    # prueba correctamente. TAPADOS se deja arriba de todas formas (no
    # hace dano tenerlo disponible, y podria existir en otra parte del
    # catalogo no explorada todavia).
    "KIMONOS":       "kimono cardigan cover-up light coat mujer",
    "CHAQUETAS":     "jacket chaqueta abrigo coat mujer",
}


async def search_composite_poc(retriever, product_id: str, boost_category: str,
                                alpha: float, top_k: int = 30):
    """
    Version de PRUEBA de search_by_product_id_with_category_boost() (Pieza 2
    del plan) -- implementada aqui inline, NO en visual_retriever.py, para
    no tocar codigo de produccion antes de validar la hipotesis con datos
    reales (principio central de la Fase 0).

    Logica identica a la que se documento en el plan: reconstruye el vector
    de imagen ya indexado del producto ancla, lo combina con el vector de
    texto de su tipo especifico, y busca en el mismo indice FAISS.
    """
    prompt = SHOPIFY_TYPE_TEXT_PROMPTS_POC.get(boost_category.upper())
    if not prompt:
        raise ValueError(
            f"No hay prompt de prueba para boost_category={boost_category!r}. "
            f"Tipos disponibles: {list(SHOPIFY_TYPE_TEXT_PROMPTS_POC.keys())}"
        )

    pid = str(product_id)
    try:
        pos = retriever._id_map.index(pid)
    except ValueError:
        raise ValueError(
            f"product_id={pid!r} no esta en el indice FAISS -- confirma que "
            f"el ID es correcto y que el producto ya fue indexado."
        )

    loop = asyncio.get_running_loop()

    def _compute():
        import torch

        # Vector de imagen ya indexado (mismo mecanismo que search_by_product_id).
        image_vec = retriever._faiss_index.reconstruct(pos)
        image_vec = np.array(image_vec, dtype=np.float32).reshape(1, -1)

        # Vector de texto del tipo especifico -- encodeado en vivo (no esta
        # pre-cacheado, porque SHOPIFY_TYPE_TEXT_PROMPTS_POC todavia no existe
        # en produccion). Esto es intencional para esta prueba: en Fase 1,
        # este prompt se precomputaria en warmup como los demas.
        tokens = retriever._tokenizer([prompt])
        with torch.no_grad():
            text_embed = retriever._model.encode_text(tokens)
            text_embed = text_embed / text_embed.norm(dim=-1, keepdim=True)
        text_vec = text_embed.float().cpu().numpy()

        composite = alpha * image_vec + (1.0 - alpha) * text_vec
        norm = np.linalg.norm(composite, axis=-1, keepdims=True)
        composite = (composite / norm).astype(np.float32)

        _, indices = retriever._faiss_index.search(composite, top_k + 1)
        return [
            retriever._id_map[idx]
            for idx in indices[0]
            if 0 <= idx < len(retriever._id_map) and retriever._id_map[idx] != pid
        ][:top_k]

    return await loop.run_in_executor(None, _compute)


def compute_visual_similarity_scores(retriever, anchor_id: str, ids: list) -> dict:
    """
    NUEVO (26/07/2026, duda de Yasmani): similitud visual PURA (coseno entre
    vectores de imagen, SIN ningun componente de texto) entre el ancla y
    cada candidato -- independiente de que alpha se haya usado para
    ENCONTRARLO.

    Responde la pregunta: "al bajar alpha para corregir el tipo, ¿estamos
    perdiendo similitud visual real con el ancla, o solo estamos corrigiendo
    el tipo sin sacrificar semejanza?" -- el criterio de exito original
    (cuantos resultados son del tipo correcto) no mide esto en absoluto; un
    resultado podria ser del tipo correcto y aun asi no parecerse en nada al
    ancla especifico.

    Reutiliza los vectores YA indexados en FAISS (reconstruct) -- no
    reencodea ninguna imagen, no requiere descargar fotos. Rapido: son
    operaciones vectoriales puras, sin llamadas al modelo.
    """
    anchor_pos = retriever._id_map.index(str(anchor_id))
    anchor_vec = np.array(retriever._faiss_index.reconstruct(anchor_pos), dtype=np.float32)
    anchor_vec = anchor_vec / np.linalg.norm(anchor_vec)

    scores = {}
    for pid in ids:
        try:
            pos = retriever._id_map.index(str(pid))
        except ValueError:
            continue
        vec = np.array(retriever._faiss_index.reconstruct(pos), dtype=np.float32)
        vec = vec / np.linalg.norm(vec)
        scores[str(pid)] = float(np.dot(anchor_vec, vec))
    return scores


def compute_anchor_type_affinities(retriever, anchor_id: str) -> dict:
    """
    NUEVO (26/07/2026, duda de Yasmani -- Opcion Cuantitativa): similitud
    coseno entre el vector de imagen PURO del ancla (sin busqueda de por
    medio) y CADA UNO de los prompts de tipo disponibles en
    SHOPIFY_TYPE_TEXT_PROMPTS_POC -- no solo el tipo declarado del ancla.

    Responde la pregunta: "¿la imagen del ancla ya esta, en el espacio de
    embeddings puro, mas cerca del texto de OTRO tipo que del texto de su
    propio tipo?" Si el tipo declarado no queda primero, es evidencia
    numerica directa de un atractor visual hacia otro tipo -- exista o no
    una causa visible en la foto (ej. un segundo accesorio visible en la
    imagen vs. una cercania aprendida por el modelo sin causa visible).

    Esto se calcula ANTES de cualquier busqueda o mezcla -- es una
    propiedad pura del vector de imagen ya indexado del ancla, comparado
    contra cada prompt de texto, uno a la vez.
    """
    import torch

    anchor_pos = retriever._id_map.index(str(anchor_id))
    anchor_vec = np.array(retriever._faiss_index.reconstruct(anchor_pos), dtype=np.float32).reshape(1, -1)
    anchor_vec = anchor_vec / np.linalg.norm(anchor_vec)

    affinities = {}
    seen_prompts = {}
    for type_name, prompt in SHOPIFY_TYPE_TEXT_PROMPTS_POC.items():
        if prompt in seen_prompts:
            # BRAZALETES y BRAZALETE (entre otros) comparten el mismo texto --
            # no reencodear, reusar el score ya calculado para ese prompt.
            affinities[type_name] = seen_prompts[prompt]
            continue
        tokens = retriever._tokenizer([prompt])
        with torch.no_grad():
            text_embed = retriever._model.encode_text(tokens)
            text_embed = text_embed / text_embed.norm(dim=-1, keepdim=True)
        text_vec = text_embed.float().cpu().numpy()
        score = float(np.dot(anchor_vec[0], text_vec[0]))
        affinities[type_name] = score
        seen_prompts[prompt] = score
    return affinities


def print_anchor_type_affinities(affinities: dict, boost_category: str):
    """Imprime el ranking de afinidad del ancla contra cada tipo, resaltando
    donde queda el tipo declarado -- ver compute_anchor_type_affinities()."""
    print("\n" + "=" * 78)
    print("¿A QUE TIPO SE PARECE MAS LA FOTO DEL ANCLA, EN TEXTO PURO?")
    print("(duda de Yasmani, 26/07/2026 -- Opcion Cuantitativa)")
    print("=" * 78)
    print("Similitud coseno entre el vector de imagen PURO del ancla (sin")
    print("ninguna busqueda de por medio) y cada prompt de tipo. Si el tipo")
    print("declarado del ancla NO queda primero, es evidencia numerica directa")
    print("de un atractor visual hacia otro tipo.")
    print()
    ranked = sorted(affinities.items(), key=lambda kv: kv[1], reverse=True)
    own_type = boost_category.upper()
    own_rank = None
    for i, (type_name, score) in enumerate(ranked, 1):
        marker = "  <-- TIPO DECLARADO DEL ANCLA" if type_name == own_type else ""
        if type_name == own_type:
            own_rank = i
        print(f"    {i}. {type_name:15} {score:.4f}{marker}")
    if own_rank and own_rank > 1:
        print(f"\n  ATENCION: el tipo declarado ({own_type}) queda en el puesto "
              f"#{own_rank}, no primero -- la foto del ancla, en el espacio de "
              f"embeddings puro, se parece MAS a otro tipo que al suyo propio. "
              f"Esto confirma numericamente el atractor, independiente de si "
              f"se puede ver a simple vista en la foto.")
    elif own_rank == 1:
        print(f"\n  El tipo declarado ({own_type}) es el mas cercano -- no hay "
              f"evidencia de un atractor hacia otro tipo en el embedding puro "
              f"para este ancla especifico.")


def fetch_product_types_shopify(product_ids: list) -> dict:
    """
    Best-effort: resuelve title/product_type reales via Shopify Admin API,
    usando las mismas credenciales que ya usa el sistema en produccion
    (SHOPIFY_ACCESS_TOKEN + SHOPIFY_SHOP_URL). Si no estan configuradas,
    devuelve un dict vacio y el script sigue funcionando solo con IDs.

    Usa el parametro batch ?ids=1,2,3 (hasta 250 por llamada) en vez de una
    llamada por producto, para no golpear el rate limit de la Admin API.
    """
    token = os.environ.get("SHOPIFY_ACCESS_TOKEN", "")
    shop = os.environ.get("SHOPIFY_SHOP_URL", "ai-shoppings.myshopify.com")
    if not token:
        print(
            "  (SHOPIFY_ACCESS_TOKEN no configurado -- se omite el lookup de "
            "tipo/titulo real; solo se muestran IDs)"
        )
        return {}

    import httpx

    ids_param = ",".join(str(pid) for pid in product_ids)
    url = f"https://{shop}/admin/api/2025-01/products.json"
    try:
        resp = httpx.get(
            url,
            params={"ids": ids_param, "fields": "id,title,product_type"},
            headers={"X-Shopify-Access-Token": token},
            timeout=15.0,
        )
        resp.raise_for_status()
        products = resp.json().get("products", [])
        return {
            str(p["id"]): (p.get("title", ""), p.get("product_type", "").upper())
            for p in products
        }
    except Exception as e:
        print(f"  (lookup de Shopify fallo, se omite: {e})")
        return {}


def resolve_product_by_handle(handle: str) -> tuple:
    """
    Resuelve un handle (el slug de la URL, ej.
    'bolso-indio-riva-rombos-gris-oscuro-dorado') a (product_id,
    product_type) via Shopify Admin API. Mucho mas dificil de teclear mal
    que un product_id numerico de 13 digitos -- y de paso confirma el
    tipo real, para poder auto-sugerir --boost-category si no se dio.

    Requiere SHOPIFY_ACCESS_TOKEN -- si no esta configurado, no hay forma
    de resolver un handle (a diferencia de --product-id, que no depende
    de Shopify para funcionar, solo del indice FAISS).
    """
    token = os.environ.get("SHOPIFY_ACCESS_TOKEN", "")
    shop = os.environ.get("SHOPIFY_SHOP_URL", "ai-shoppings.myshopify.com")
    if not token:
        print(
            "ERROR: --product-handle requiere SHOPIFY_ACCESS_TOKEN configurado "
            "(deberia venir del .env). Usa --product-id en su lugar, o "
            "configura el token."
        )
        sys.exit(1)

    import httpx

    url = f"https://{shop}/admin/api/2025-01/products.json"
    try:
        resp = httpx.get(
            url,
            params={"handle": handle, "fields": "id,title,product_type"},
            headers={"X-Shopify-Access-Token": token},
            timeout=15.0,
        )
        resp.raise_for_status()
        products = resp.json().get("products", [])
        if not products:
            print(f"ERROR: no se encontro ningun producto con handle={handle!r} "
                  f"en Shopify. Revisa el slug (copialo directo de la URL del "
                  f"producto en el admin de Shopify).")
            sys.exit(1)
        p = products[0]
        pid, title, ptype = str(p["id"]), p.get("title", ""), p.get("product_type", "").upper()
        print(f"  (handle {handle!r} resuelto: id={pid}, titulo={title!r}, tipo={ptype!r})")
        return pid, ptype
    except SystemExit:
        raise
    except Exception as e:
        print(f"ERROR: fallo la resolucion del handle via Shopify: {e}")
        sys.exit(1)


def print_result_breakdown(label: str, ids: list, boost_category: str,
                            type_lookup: dict, visual_scores: dict = None):
    """
    Imprime el desglose por tipo real de los primeros 10 resultados.

    visual_scores (NUEVO 26/07/2026, opcional): dict pid->similitud visual
    pura (ver compute_visual_similarity_scores). Si se pasa, tambien
    imprime el promedio del top-10 y el score individual de cada item.
    """
    top10 = ids[:10]
    types = [type_lookup.get(str(pid), ("?", "UNKNOWN"))[1] for pid in top10]
    own_type_count = sum(1 for t in types if t == boost_category.upper())
    breakdown = Counter(types)

    print(f"\n--- {label} ---")
    print(f"Total candidatos: {len(ids)} | Top-10 desglose: {dict(breakdown)}")
    print(f"  -> {own_type_count}/10 son del tipo {boost_category.upper()} "
          f"(el que estamos buscando)")

    avg_visual_score = None
    if visual_scores:
        top10_scores = [visual_scores[str(pid)] for pid in top10 if str(pid) in visual_scores]
        if top10_scores:
            avg_visual_score = sum(top10_scores) / len(top10_scores)
            print(f"  -> similitud visual PURA promedio del top-10 (coseno "
                  f"imagen-imagen, sin texto): {avg_visual_score:.3f}")

    if type_lookup:
        print("  Top-10 detalle:")
        for i, pid in enumerate(top10, 1):
            title, ptype = type_lookup.get(str(pid), ("(desconocido)", "?"))
            marker = "  <-- MISMO TIPO" if ptype == boost_category.upper() else ""
            score_str = ""
            if visual_scores and str(pid) in visual_scores:
                score_str = f" [sim.visual={visual_scores[str(pid)]:.3f}]"
            print(f"    {i}. [{ptype:12}] {title} (id={pid}){score_str}{marker}")
    return own_type_count, avg_visual_score


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-id", default=None,
                         help="product_id numerico del ancla (ej. 9978485440821 "
                              "para Collar Paula Piedras Plateado). Usa esto O "
                              "--product-handle, no ambos.")
    parser.add_argument("--product-handle", default=None,
                         help="handle/slug del ancla (el texto de la URL del "
                              "producto, ej. 'bolso-indio-riva-rombos-gris-"
                              "oscuro-dorado') -- mas facil de copiar sin "
                              "errores que un ID numerico de 13 digitos. "
                              "Requiere SHOPIFY_ACCESS_TOKEN. Si se usa esto, "
                              "--boost-category se auto-detecta del "
                              "product_type real (se puede sobreescribir).")
    parser.add_argument("--boost-category", default=None,
                         help="Tipo Shopify exacto a priorizar, en mayusculas "
                              "(ej. COLLARES, AROS, CARTERAS). Requerido si "
                              "usas --product-id; opcional (auto-detectado) "
                              "si usas --product-handle.")
    parser.add_argument("--top-k", type=int, default=30,
                         help="Candidatos a traer por busqueda (default: 30, "
                              "igual al pool actual de F-08/F-08C)")
    parser.add_argument("--alphas", default="0.6,0.4",
                         help="Lista de valores alpha a probar, separados por "
                              "coma (ej. '0.6,0.4,0.2'). alpha=peso de imagen "
                              "(1-alpha=peso de texto). Default: '0.6,0.4'. "
                              "Util para explorar valores mas bajos cuando el "
                              "boost es hacia un tipo DISTINTO al del ancla "
                              "(caso F-08B), que necesita mas peso de texto "
                              "que reforzar el propio tipo (caso F-08C).")
    args = parser.parse_args()

    try:
        alphas = [float(a.strip()) for a in args.alphas.split(",") if a.strip()]
    except ValueError:
        print(f"ERROR: --alphas={args.alphas!r} no es una lista valida de "
              f"numeros separados por coma (ej. '0.6,0.4,0.2').")
        sys.exit(1)
    if not alphas:
        print("ERROR: --alphas no puede estar vacio.")
        sys.exit(1)

    if not args.product_id and not args.product_handle:
        print("ERROR: pasa --product-id O --product-handle (uno de los dos, "
              "requerido).")
        sys.exit(1)
    if args.product_id and args.product_handle:
        print("ERROR: pasa solo uno de --product-id / --product-handle, no "
              "ambos.")
        sys.exit(1)

    _load_dotenv_if_present()

    # FIX (18/07/2026): VISUAL_INDEX_BUCKET no vino en el .env local (solo
    # esta configurado como variable de entorno del deploy en Cloud Run,
    # no duplicado en .env para desarrollo local) -- confirmado por
    # Yasmani en la sesion: "retail-recommendations-449216-visual-index".
    # visual_retriever.GCS_BUCKET se lee UNA VEZ al importar el modulo (a
    # nivel de modulo, no dentro de una funcion) -- por eso no basta con
    # setear os.environ despues del import, hay que parchear el atributo
    # del modulo directamente para que _download_from_gcs() lo vea.
    if not os.environ.get("VISUAL_INDEX_BUCKET"):
        _fallback_bucket = "retail-recommendations-449216-visual-index"
        os.environ["VISUAL_INDEX_BUCKET"] = _fallback_bucket
        visual_retriever.GCS_BUCKET = _fallback_bucket
        print(f"  (VISUAL_INDEX_BUCKET no estaba en el entorno -- usando "
              f"el valor confirmado: {_fallback_bucket})")

    # FIX (18/07/2026): en produccion (Dockerfile) el modelo corre 100%
    # offline (HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1,
    # HF_DATASETS_OFFLINE=1) porque los pesos ya estan pre-horneados en la
    # imagen Docker. Si el .env local llegara a copiar esas mismas
    # variables (para mantener paridad con el deploy), este script
    # fallaria intentando cargar el modelo desde un cache local que no
    # existe en esta maquina. Fase 0 SI necesita acceso real a internet
    # para descargar el modelo la primera vez -- se fuerzan estas
    # variables a ausentes para esta corrida puntual.
    _offline_vars = ["HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"]
    _were_set = [v for v in _offline_vars if os.environ.get(v)]
    if _were_set:
        print(f"  (ATENCION: {_were_set} estaban configuradas -- se "
              f"desactivan para esta corrida, Fase 0 necesita descargar "
              f"el modelo online la primera vez)")
        for v in _offline_vars:
            os.environ.pop(v, None)

    print("=" * 78)
    print("FASE 0 -- Prueba de concepto: Composite Embedding Granular")
    print("=" * 78)

    # Resolucion del ancla: por handle (mas facil de copiar sin errores) o
    # por product_id directo. Si es por handle, tambien auto-detecta
    # --boost-category del product_type real (a menos que se haya dado uno
    # explicito, que tiene prioridad).
    if args.product_handle:
        print(f"Resolviendo handle {args.product_handle!r} via Shopify...")
        resolved_id, resolved_type = resolve_product_by_handle(args.product_handle)
        args.product_id = resolved_id
        if not args.boost_category:
            args.boost_category = resolved_type
            print(f"  (--boost-category auto-detectado: {resolved_type!r})")

    if not args.boost_category:
        print(
            "ERROR: falta --boost-category. Con --product-id es obligatorio "
            "pasarlo a mano; con --product-handle deberia haberse "
            "auto-detectado -- si llegaste aqui es que Shopify no devolvio "
            "un product_type para ese producto."
        )
        sys.exit(1)

    print(f"Producto ancla: {args.product_id}")
    print(f"Tipo a priorizar: {args.boost_category}")
    print(f"VISUAL_INDEX_BUCKET: {os.environ.get('VISUAL_INDEX_BUCKET', '(no configurado)')}")
    print(f"SHOPIFY_ACCESS_TOKEN: {'configurado' if os.environ.get('SHOPIFY_ACCESS_TOKEN') else 'NO configurado'}")
    print()

    print("Cargando FashionSigLIP (primera vez puede tardar varios minutos "
          "por la descarga del modelo desde Hugging Face)...")
    retriever = FashionSigLIPRetriever()

    print("Cargando indice FAISS (local /tmp o descarga desde GCS)...")
    if not retriever.try_load_from_disk():
        print(
            "ERROR: no se pudo cargar el indice FAISS. Verifica:\n"
            "  - Que VISUAL_INDEX_BUCKET este configurado correctamente\n"
            "    (nombre recordado, no verificado en esta sesion: "
            "retail-recommendations-449216-visual-index)\n"
            "  - Que tengas credenciales GCP validas "
            "(gcloud auth application-default login)\n"
            "  - Que el bucket tenga permiso de lectura para tu cuenta"
        )
        sys.exit(1)

    print(f"Indice cargado: {retriever.index_size()} productos, "
          f"{retriever.category_map_size()} categorizados")

    # FIX (18/07/2026): validar el ID contra el indice ANTES de correr
    # ninguna busqueda -- antes, un ID invalido/no indexado hacia que la
    # busqueda PLANA fallara en silencio (search_by_product_id() degrada
    # graciosamente en produccion, sin avisar) y recien la busqueda
    # COMPOSITE (que no tiene ese manejo) explotaba con un traceback
    # confuso, sin decir claramente si el problema era "ID mal escrito" o
    # "producto real pero sin indexar". Ahora se valida una sola vez, al
    # principio, con un mensaje claro para cada caso.
    if args.product_id not in retriever._id_map:
        print(f"\nERROR: product_id={args.product_id!r} NO esta en el indice "
              f"FAISS ({retriever.index_size()} productos indexados).")
        _diag = fetch_product_types_shopify([args.product_id])
        if args.product_id in _diag:
            _title, _ptype = _diag[args.product_id]
            print(f"  Si es un producto REAL en Shopify (titulo={_title!r}, "
                  f"tipo={_ptype!r}) pero simplemente no fue indexado "
                  f"visualmente todavia -- eso es un hallazgo real de "
                  f"cobertura del indice, no un error de tipeo.")
        else:
            print(f"  Este ID tampoco se encontro en Shopify -- muy probable "
                  f"que sea un ID incorrecto (revisa el formato: los IDs "
                  f"reales de este catalogo tienen 13 digitos). Usa "
                  f"--product-handle en su lugar para evitar este tipo de "
                  f"error.")
        sys.exit(1)

    await retriever.warmup()

    # NUEVO (26/07/2026, Opcion Cuantitativa): afinidad del ancla contra
    # cada tipo, ANTES de correr ninguna busqueda -- ver
    # compute_anchor_type_affinities().
    anchor_affinities = compute_anchor_type_affinities(retriever, args.product_id)
    print_anchor_type_affinities(anchor_affinities, args.boost_category)

    # ── 1. Busqueda PLANA (comportamiento actual, sin cambios) ─────────────
    print("\nEjecutando busqueda PLANA (search_by_product_id, sin cambios)...")
    plain_ids = await retriever.search_by_product_id(
        args.product_id, top_k=args.top_k
    )

    # ── 2. Busqueda(s) COMPOSITE, una por cada alpha en --alphas ────────────
    composite_results = {}  # alpha -> lista de ids
    for alpha in alphas:
        print(f"Ejecutando busqueda COMPOSITE alpha={alpha} "
              f"({int(alpha*100)}% imagen, {int((1-alpha)*100)}% texto)...")
        composite_results[alpha] = await search_composite_poc(
            retriever, args.product_id, args.boost_category,
            alpha=alpha, top_k=args.top_k
        )

    # ── Resolver tipos reales para comparar (best-effort via Shopify) ──────
    all_ids = list(set(
        plain_ids[:10]
        + [pid for ids in composite_results.values() for pid in ids[:10]]
    ))
    print(f"\nResolviendo tipo/titulo real de {len(all_ids)} productos via "
          f"Shopify Admin API...")
    type_lookup = fetch_product_types_shopify(all_ids)

    # NUEVO (26/07/2026, duda de Yasmani): similitud visual PURA de cada
    # candidato contra el ancla, independiente del alpha que lo encontro --
    # ver compute_visual_similarity_scores() para el razonamiento completo.
    print("Calculando similitud visual pura (coseno imagen-imagen, sin "
          "texto) de cada candidato contra el ancla...")
    visual_scores = compute_visual_similarity_scores(retriever, args.product_id, all_ids)

    print("\n" + "=" * 78)
    print("RESULTADOS")
    print("=" * 78)
    n_plain, sim_plain = print_result_breakdown(
        "PLANA (baseline actual)", plain_ids, args.boost_category, type_lookup,
        visual_scores,
    )
    n_by_alpha = {}
    sim_by_alpha = {}
    for alpha in alphas:
        n_by_alpha[alpha], sim_by_alpha[alpha] = print_result_breakdown(
            f"COMPOSITE alpha={alpha}", composite_results[alpha],
            args.boost_category, type_lookup, visual_scores,
        )

    print("\n" + "=" * 78)
    print("VEREDICTO (criterio de exito del plan: el composite debe traer")
    print("sensiblemente MAS productos del tipo del ancla que la busqueda plana)")
    print("=" * 78)
    print(f"  Plana:            {n_plain}/10")
    for alpha in alphas:
        print(f"  Composite a={alpha}:  {n_by_alpha[alpha]}/10")

    # NUEVO (26/07/2026): responder directamente la duda de Yasmani con
    # numeros, no con intuicion -- ver compute_visual_similarity_scores().
    if visual_scores and sim_plain is not None and sim_by_alpha:
        print("\n" + "=" * 78)
        print("¿SE PIERDE SIMILITUD VISUAL AL BAJAR ALPHA? (duda de Yasmani, 26/07/2026)")
        print("=" * 78)
        print("  Similitud visual PURA promedio del top-10 (coseno imagen-imagen,")
        print("  SIN ningun componente de texto -- 1.0 = identico, 0.0 = sin relacion):")
        print(f"    Plana (referencia, 100% imagen):    {sim_plain:.3f}")
        for alpha in sorted(alphas, reverse=True):
            if sim_by_alpha[alpha] is not None:
                delta = sim_by_alpha[alpha] - sim_plain
                print(f"    Composite alpha={alpha}:              "
                      f"{sim_by_alpha[alpha]:.3f}  ({delta:+.3f} vs. plana)")
        print("\n  No hay un umbral establecido de 'cuanto es aceptable perder' -- estos")
        print("  numeros son para evaluarlos con criterio de stylist junto a los")
        print("  titulos/detalle listados arriba, no para que el script decida solo.")

    if not type_lookup:
        print(
            "\n  ATENCION: no se pudo resolver tipo real (falta "
            "SHOPIFY_ACCESS_TOKEN) -- revisa manualmente los IDs impresos "
            "arriba contra el catalogo antes de sacar conclusiones."
        )
    else:
        mejor_alpha = max(alphas, key=lambda a: n_by_alpha[a])
        if n_by_alpha[mejor_alpha] > n_plain:
            print(f"\n  MEJORA CONFIRMADA con datos reales. Mejor alpha "
                  f"probado: {mejor_alpha} ({n_by_alpha[mejor_alpha]}/10 vs "
                  f"{n_plain}/10 de la busqueda plana).")
        else:
            print(
                "\n  SIN MEJORA CLARA -- ningun alpha probado supero a la "
                "busqueda plana para este producto especifico. Antes de "
                "descartar la tecnica, probar con otro producto ancla o "
                "con valores de alpha mas bajos (--alphas '0.3,0.2') antes "
                "de decidir si seguir a Fase 1."
            )


if __name__ == "__main__":
    asyncio.run(main())
