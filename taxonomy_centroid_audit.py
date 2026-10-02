"""
taxonomy_centroid_audit.py
============================
Script de auditoria de taxonomia. Resuelve las tres necesidades identificadas
en DCT_Fase1b_Composite_Embedding_F08B_Cierre_24072026.md (secciones 9.1,
11.3, Addendum 5 del 17/09/2026, y Addendum 6 del 26/09/2026):

  1. COBERTURA: enumera todos los product_type reales del catalogo (via el
     pickle de TF-IDF, que ya tenemos), reemplazando el metodo manual de
     "adivinar nombres de variantes" -- documentado el 26/07/2026 como no
     exhaustivo (NOVIAS LARGOS sola ocupo 3 paginas de 50 productos en
     Shopify Admin sin agotarse).

  2. DESINCRONIZACION DE FUENTES: cruza ese inventario real contra las
     fuentes de taxonomia activas hoy -- product_taxonomy.py (unica fuente
     de tipo->outfit_slot desde la decision de unificacion del 26/09/2026)
     y CATEGORY_KEYWORDS (deteccion de categoria desde texto libre, un
     problema distinto, se mantiene separada a proposito).

  3. MISTAGGING: compara el embedding visual de cada producto contra el
     centroide de su propio product_type declarado (motivado por el caso
     real CARTERAS/vestido, 24/07/2026) -- productos cuya similitud con el
     centroide de su propio tipo cae varias desviaciones estandar por debajo
     del promedio de ese tipo son candidatos a estar mal tipificados en
     Shopify.

     ESTADO (29/09/2026): implementado de punta a punta -- cliente
     (LFM2ColBERTClient.export_embeddings(), colbert_client.py) Y servidor
     (FashionSigLIPRetriever.export_embeddings() + ruta POST
     /v1/embed/export-embeddings, embedding-service/main.py y
     visual_retriever.py, ambos en src/api/services/embedding-service/ --
     el embedding-service vive DENTRO de este mismo repo, no en uno
     separado). Logica de calculo validada con datos sinteticos (impostor
     sembrado deliberadamente, detectado correctamente con z=4.3
     desviaciones, cero falsos positivos entre 24 productos genuinos).
     Contrato completo documentado abajo.

     CONTRATO DEL ENDPOINT (para quien lo implemente del lado del
     embedding-service):

       POST /v1/embed/export-embeddings
       Auth: igual que el resto de /v1/embed/* -- ID token IAM (Authorization:
             Bearer <token>), mismo patron que _auth_headers() en
             colbert_client.py.

       Request (JSON):
         {
           "product_ids": ["123", "456"],   # opcional
           "limit": 500,                     # opcional, solo aplica si
                                              # product_ids esta ausente
           "cursor": "opaco, devuelto por"   # opcional, token de continuacion
         }

         Modo TARGETED (product_ids presente): devuelve exactamente esos
         IDs (los que existan en el indice) -- el llamador controla el
         tamano del lote pasando menos o mas IDs. Sin paginacion.

         Modo BULK (product_ids ausente): pagina sobre TODO el indice
         usando limit + cursor -- necesario porque un catalogo de miles de
         productos como respuesta unica es un payload grande (ej. 3045
         productos x 768 floats ya son ~19MB de datos crudos).

       Response (JSON):
         {
           "embeddings": {"123": [0.0123, -0.0456, ...], "456": [...]},
           "dimension": 768,
           "model": "<nombre/version del modelo visual>",
           "count": 2,
           "not_found": [],           # IDs pedidos (modo targeted) que no
                                       # estan indexados
           "next_cursor": null        # ausente/null si no hay mas paginas
                                       # (modo bulk)
         }

       Notas de implementacion sugeridas (no vinculantes, el equipo del
       embedding-service decide los detalles internos):
         - FAISS IndexFlatIP (el tipo de indice ya usado, ver comentario en
           colbert_client.py) soporta reconstruccion nativa de vectores
           (.reconstruct() / .reconstruct_n()) -- no deberia hacer falta
           mantener una copia separada de los embeddings solo para esto.
         - Es una ruta de solo lectura, pensada para uso de auditoria
           periodica (este script), NO para el flujo de recomendaciones en
           vivo -- no necesita optimizarse para latencia baja como
           search_outfit_by_image().

Uso:
    Correr desde la raiz del repo (para que los imports de src.* resuelvan):
        python taxonomy_centroid_audit.py [ruta_al_pickle]

    FIX (01/10/2026): sin ruta explicita, el script SIEMPRE trae la version
    mas reciente del bucket antes de analizar (sobrescribe tfidf_model.pkl
    en el directorio actual) -- ya no hace falta correr gsutil a mano antes
    de cada corrida. Motivado por un caso real: una correccion hecha en
    Shopify no se reflejo en una corrida porque el pickle local era de
    antes de esa correccion, y nadie lo noto hasta comparar dos corridas a
    mano. Mismo mecanismo (gsutil por subproceso) que ya usa
    check_missing_images.py -- reutilizado aqui a proposito, para no abrir
    un camino de autenticacion nuevo despues de la saga de IAM documentada
    en DCT_Cierre_Fase2_Unificacion_Taxonomia_27092026.md, seccion 7.5 (la
    autenticacion de gsutil para leer un bucket es la misma que ya usas a
    mano hoy, sin relacion con esa saga -- esa fue especifica de mintar ID
    tokens para el embedding-service).

    Si SI se pasa una ruta explicita, se usa tal cual, sin tocar el bucket
    -- para poder probar contra un pickle fijo o sintetico a proposito.

    Si gsutil no esta disponible o la descarga falla, se usa la copia local
    existente como respaldo (con un aviso claro de que puede estar
    desactualizada), o se aborta si tampoco hay copia local.

    El reporte siempre imprime el 'synced_at' del pickle usado (ya viene
    guardado ahi, no se calcula) -- asi, sin importar de donde vino el
    archivo, siempre queda a la vista que tan reciente es lo analizado.

    Motivo 3 (mistagging) necesita COLBERT_SERVICE_URL -- ya esta en .env
    (raiz del repo), pero este script, al correr como proceso independiente
    (no dentro del monolito desplegado), no la hereda automaticamente. Se
    carga aqui con env_loader.ensure_env_loaded() (el mismo utilitario que
    ya usan "todos los scripts de test" del repo, por su propio docstring)
    -- sin esto, LFM2ColBERTClient() lanza ValueError al construirse, ANTES
    de siquiera intentar la conexion HTTP.
"""
import pickle
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path
from collections import Counter

from env_loader import ensure_env_loaded

ensure_env_loaded()


DEFAULT_LOCAL_PICKLE = "tfidf_model.pkl"
DEFAULT_BUCKET_PICKLE = "gs://retail-recommendations-449216-tfidf-model/tfidf-model/tfidf_model.pkl"

# Motivo 3: un tipo con menos productos que esto no tiene suficiente senal
# estadistica para calcular una desviacion estandar confiable (ej. "ALAS DE
# NOVIA" con 1 solo producto -- comparar ese unico producto contra si mismo
# siempre da similitud 1.0, no aporta nada).
MISTAGGING_MIN_SAMPLES = 5

# Motivo 3: candidato a mistagging = mas de esta cantidad de desviaciones
# estandar POR DEBAJO del promedio de similitud de su propio tipo. Es
# relativo al propio tipo (no un umbral fijo de similitud) porque tipos con
# mucha variedad visual natural (ej. VESTIDOS LARGOS, 990 productos) tienen
# mas dispersion normal que tipos chicos y homogeneos -- un umbral fijo
# marcaria falsos positivos en los primeros.
#
# CALIBRACION (29/09/2026): primera corrida real con 2.0 dio 130 candidatos;
# verificados los 130 contra Shopify Admin, 128 resultaron correctamente
# tipificados (variedad visual genuina -- lentejuelas, animal print, etc.),
# 2 hallazgos reales (1 mistagging confirmado y corregido: "Body Renata
# Negro", BRALETTES->LENCERIA; 1 descripcion duplicada entre dos productos
# distintos, sin relacion con la categoria). Subido a 2.5 para reducir el
# volumen de revision manual en la proxima corrida.
#
# ADVERTENCIA: el unico mistagging confirmado hasta ahora tenia z=2.5 EXACTO
# -- con este umbral (z > 2.5, estrictamente mayor), ese caso especifico NO
# se habria marcado. La muestra de calibracion es de un solo caso real, asi
# que esto es un ajuste de volumen mas que una mejora de precision probada;
# si la proxima corrida sale muy limpia (pocos o ningun candidato), vale la
# pena bajarlo de nuevo antes de asumir que el catalogo esta genuinamente
# libre de mistagging.
MISTAGGING_STD_THRESHOLD = 2.5


def normalize(s: str) -> str:
    s = s or ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.upper().strip()


def load_catalog_data(pickle_path: str):
    """
    Lee el pickle UNA vez y devuelve (real_type_counts, id_to_type, id_to_text, synced_at):
      - real_type_counts: {product_type: count} -- motivos 1 y 2.
      - id_to_type: {product_id: product_type} -- motivo 3 (mistagging),
        para poder agrupar embeddings por tipo declarado.
      - id_to_text: {product_id: "title tags"} -- motivo 3, chequeo de texto
        (29/09/2026): el pickle YA trae 'title' y 'tags' por producto (mismos
        campos que ya usa el TF-IDF), confirmado inspeccionando el pickle
        real -- no hace falta ninguna llamada adicional a Shopify.
      - synced_at: marca de tiempo (del propio pickle) de cuando se
        sincronizo el catalogo desde Shopify -- agregado (01/10/2026) para
        que el reporte siempre muestre que tan reciente es lo analizado,
        sin importar de donde vino el archivo.
    """
    with open(pickle_path, "rb") as f:
        data = pickle.load(f)
    product_data = data.get("product_data")
    if product_data is None:
        raise ValueError(
            "El pickle no tiene la clave 'product_data' -- ¿es el archivo correcto?"
        )
    synced_at = data.get("synced_at")
    counts = Counter()
    id_to_type = {}
    id_to_text = {}
    for p in product_data:
        pt = normalize(p.get("product_type", ""))
        pid = str(p.get("id", ""))
        if pt:
            counts[pt] += 1
            if pid:
                id_to_type[pid] = pt
                title = p.get("title", "") or ""
                tags = p.get("tags", "") or ""
                id_to_text[pid] = f"{title} {tags}"
    return dict(counts), id_to_type, id_to_text, synced_at


def run_coverage_and_desync_audit(real_type_counts: dict) -> None:
    """Motivos 1 (cobertura) y 2 (desincronizacion de fuentes)."""
    real_types = set(real_type_counts.keys())

    # Imports reales -- no reimplementaciones. Se hacen aqui (no al tope del
    # archivo) para que el script pueda correr y reportar el resto aunque
    # alguno de estos modulos no este disponible en el path.
    sources = {}
    non_applicable = set()
    try:
        from src.recommenders.product_taxonomy import (
            PRODUCT_TAXONOMY,
            is_non_applicable_type,
        )
        sources["product_taxonomy.py"] = set(PRODUCT_TAXONOMY.keys())
        non_applicable = {t for t in real_types if is_non_applicable_type(t)}
    except ImportError as e:
        print(f"  [AVISO] no se pudo importar product_taxonomy.py: {e}")

    try:
        from src.recommenders.improved_fallback_exclude_seen import get_concrete_categories
        sources["CATEGORY_KEYWORDS (via get_concrete_categories)"] = get_concrete_categories()
    except ImportError as e:
        print(f"  [AVISO] no se pudo importar improved_fallback_exclude_seen.py: {e}")

    print("\n" + "=" * 78)
    print("MOTIVO 1 -- COBERTURA")
    print("=" * 78)
    print(f"Tipos reales distintos en el catalogo: {len(real_types)}")
    for t in sorted(real_types):
        print(f"  {t:30s} ({real_type_counts[t]} productos)")

    print("\n" + "=" * 78)
    print("MOTIVO 2 -- DESINCRONIZACION DE FUENTES")
    print("=" * 78)
    if non_applicable:
        print(
            f"Excluidos del analisis de product_taxonomy.py (marcados "
            f"NON_APPLICABLE_TYPES -- no son prendas combinables en el "
            f"sentido de outfit completion): {sorted(non_applicable)}"
        )
    for name, known_types in sources.items():
        faltantes = real_types - known_types
        # NON_APPLICABLE_TYPES solo aplica al analisis de product_taxonomy.py
        # (tipo->outfit_slot) -- CATEGORY_KEYWORDS resuelve un problema
        # distinto (deteccion por texto libre), donde SI tiene sentido que
        # AROMAS/PACK sean buscables aunque no combinen visualmente.
        if name == "product_taxonomy.py":
            faltantes -= non_applicable
        huerfanos = known_types - real_types
        print(f"\n-- {name} --")
        if faltantes:
            print(f"  [GAP] tipos reales AUSENTES de esta fuente ({len(faltantes)}):")
            for t in sorted(faltantes):
                print(f"    {t}  ({real_type_counts[t]} productos afectados)")
        else:
            print("  OK: cubre todos los tipos reales del catalogo (aplicables).")
        if huerfanos:
            print(f"  [INFO] tipos en esta fuente sin productos reales hoy ({len(huerfanos)}): {sorted(huerfanos)}")


def _cosine_similarity(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _compute_centroid(vectors):
    n = len(vectors)
    dim = len(vectors[0])
    return [sum(v[i] for v in vectors) / n for i in range(dim)]


def run_mistagging_audit(id_to_type: dict, id_to_text: dict) -> None:
    """
    Motivo 3 -- MISTAGGING. Requiere el endpoint documentado en el docstring
    del modulo. Si no esta disponible, se salta con un aviso claro.

    FIX (30/09/2026): chequeo de texto automatizado, antes de escalar cada
    candidato a revision manual. Motivado por la primera corrida real
    (29/09/2026): 130 candidatos, 128 resultaron ser variedad visual
    genuina (lentejuelas, animal print) confirmable con solo leer
    titulo/tags -- exactamente el chequeo que se automatiza aqui. Reusa
    extract_categories_from_query() / get_concrete_categories()
    (improved_fallback_exclude_seen.py), la misma fuente ya validada de
    deteccion de categoria por texto -- no se crea una sexta fuente de
    taxonomia paralela. Validado contra los 53 candidatos reales de la
    corrida del 30/09/2026 antes de integrarse: 52/53 confirmados por texto
    correctamente, 1 escalado a revision -- coincide exactamente con el
    unico caso ambiguo detectado en la revision manual de esa misma corrida
    ("Vestido Midi" declarado VESTIDOS LARGOS).
    """
    print("\n" + "=" * 78)
    print("MOTIVO 3 -- MISTAGGING (embeddings visuales vs. centroide del tipo)")
    print("=" * 78)
    try:
        import asyncio
        from src.api.services.colbert_client import LFM2ColBERTClient
        client = LFM2ColBERTClient()
        if not hasattr(client, "export_embeddings"):
            raise AttributeError("export_embeddings")
        embeddings = asyncio.run(client.export_embeddings())
    except (ImportError, AttributeError):
        print(
            "  [OMITIDO] El embedding-service todavia no expone un endpoint "
            "para exportar embeddings crudos (POST /v1/embed/export-embeddings, "
            "ver docstring de este script para el contrato completo). "
            "Cobertura y desincronizacion (motivos 1 y 2) no se ven afectados."
        )
        return
    except Exception as e:
        print(f"  [OMITIDO] Fallo inesperado consultando el embedding-service: {e}")
        return

    if not embeddings:
        print("  [OMITIDO] El embedding-service no devolvio ningun embedding.")
        return

    # Chequeo de texto -- import lazy, mismo patron que el resto del script.
    # Se degrada con gracia si el modulo no esta disponible: todo candidato
    # queda sin confirmar por texto, y se escala a revision igual que antes
    # de este fix (ningun candidato se pierde por un fallo de import).
    text_check_available = False
    try:
        from src.recommenders.improved_fallback_exclude_seen import (
            extract_categories_from_query,
            get_concrete_categories,
        )
        available_categories = get_concrete_categories()
        text_check_available = True
    except ImportError as e:
        print(f"  [AVISO] chequeo de texto no disponible (todo candidato se escala a revision): {e}")

    # Agrupar embeddings por tipo DECLARADO (el dato de Shopify, potencialmente
    # incorrecto -- es justo lo que este motivo intenta verificar).
    by_type = {}
    for pid, vec in embeddings.items():
        ptype = id_to_type.get(str(pid))
        if ptype:
            by_type.setdefault(ptype, []).append((pid, vec))

    analizados = {t: items for t, items in by_type.items() if len(items) >= MISTAGGING_MIN_SAMPLES}
    omitidos = sorted(t for t in by_type if t not in analizados)
    print(
        f"Tipos analizados (>= {MISTAGGING_MIN_SAMPLES} productos con embedding): "
        f"{len(analizados)}"
    )
    if omitidos:
        print(
            f"  [INFO] tipos con muy pocos productos para un analisis "
            f"estadistico confiable, omitidos: {omitidos}"
        )

    candidates = []
    for ptype, items in analizados.items():
        vectors = [v for _, v in items]
        centroid = _compute_centroid(vectors)
        sims = [_cosine_similarity(v, centroid) for _, v in items]
        mean_sim = sum(sims) / len(sims)
        variance = sum((s - mean_sim) ** 2 for s in sims) / len(sims)
        std_sim = variance ** 0.5
        if std_sim == 0:
            continue  # tipo perfectamente homogeneo -- nada que senalar
        for (pid, _), sim in zip(items, sims):
            z = (mean_sim - sim) / std_sim
            if z > MISTAGGING_STD_THRESHOLD:
                candidates.append((pid, ptype, sim, mean_sim, z))

    if not candidates:
        print("\n  Ningun candidato a mistagging detectado con el umbral actual "
              f"(MISTAGGING_STD_THRESHOLD={MISTAGGING_STD_THRESHOLD}).")
        return

    candidates.sort(key=lambda c: -c[4])

    needs_review = []
    confirmed_by_text = []
    for pid, ptype, sim, mean_sim, z in candidates:
        text_confirms = None
        if text_check_available:
            text = id_to_text.get(str(pid), "")
            detected = extract_categories_from_query(text, available_categories)
            text_confirms = ptype.upper() in {d.upper() for d in detected}
        if text_confirms:
            confirmed_by_text.append((pid, ptype, sim, mean_sim, z))
        else:
            needs_review.append((pid, ptype, sim, mean_sim, z, text_confirms))

    if needs_review:
        print(
            f"\n  [REQUIERE REVISION MANUAL] {len(needs_review)} producto(s) -- "
            f"el titulo/tags NO confirma el tipo declarado (o el chequeo de "
            f"texto no estaba disponible):"
        )
        for pid, ptype, sim, mean_sim, z, text_confirms in needs_review:
            nota = "chequeo de texto no disponible" if text_confirms is None else "texto tampoco coincide"
            print(
                f"    id={pid}  tipo_declarado={ptype}  similitud={sim:.3f} "
                f"(promedio del tipo: {mean_sim:.3f}, {z:.1f} desviaciones por "
                f"debajo)  [{nota}] -- revisar en Shopify Admin"
            )

    if confirmed_by_text:
        print(
            f"\n  [OUTLIER VISUAL, CONFIRMADO POR TEXTO] {len(confirmed_by_text)} "
            f"producto(s) -- titulo/tags SI coinciden con el tipo declarado, "
            f"probablemente solo variedad visual (baja prioridad de revision):"
        )
        for pid, ptype, sim, mean_sim, z in confirmed_by_text:
            print(
                f"    id={pid}  tipo_declarado={ptype}  similitud={sim:.3f}  "
                f"z={z:.1f}"
            )


def ensure_fresh_pickle(pickle_path: str) -> None:
    """
    Descarga SIEMPRE la copia mas reciente del bucket a pickle_path,
    sobrescribiendo lo que haya ahi -- mismo mecanismo (gsutil por
    subproceso) que check_missing_images.py ya usa, reutilizado aqui para
    no abrir un camino de autenticacion nuevo (la autenticacion de gsutil
    para LEER un bucket es un caso simple y ya probado -- sin relacion con
    la saga de mintar ID tokens para el embedding-service, documentada en
    DCT_Cierre_Fase2_Unificacion_Taxonomia_27092026.md, seccion 7.5).

    FIX (01/10/2026): antes, el script simplemente fallaba si no encontraba
    el pickle local, y si lo encontraba -- sin importar su antiguedad -- lo
    usaba tal cual. Esto causo un caso real de confusion: una correccion
    hecha en Shopify no se reflejo en una corrida porque el pickle local
    era de antes de esa correccion, y nadie se dio cuenta hasta comparar
    manualmente dos corridas. Llamada SOLO cuando no se paso una ruta
    explicita (ver main()) -- una ruta explicita se respeta tal cual, sin
    tocar el bucket, para poder probar contra un pickle fijo o sintetico.

    Se degrada con gracia: si gsutil no esta instalado o la descarga falla
    por cualquier motivo, se usa la copia local existente como respaldo
    (con un aviso claro de que puede estar desactualizada) en vez de
    abortar de inmediato.
    """
    gsutil = shutil.which("gsutil")
    if gsutil is None:
        print(
            "  [AVISO] no se encontro 'gsutil' en el PATH -- no se pudo "
            f"refrescar '{pickle_path}' desde el bucket. Se usara la copia "
            "local, si existe (puede estar desactualizada)."
        )
        return

    print(f"Descargando la version mas reciente desde {DEFAULT_BUCKET_PICKLE}...")
    result = subprocess.run(
        [gsutil, "cp", DEFAULT_BUCKET_PICKLE, pickle_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"  [AVISO] no se pudo descargar desde el bucket (codigo "
            f"{result.returncode})."
        )
        if result.stderr:
            print(f"  {result.stderr.strip()}")
        if Path(pickle_path).is_file():
            print(
                f"  Se usara la copia local existente de '{pickle_path}' -- "
                "puede estar desactualizada."
            )
        else:
            print("  No hay copia local de respaldo.")


def main():
    explicit_path = len(sys.argv) >= 2
    pickle_path = sys.argv[1] if explicit_path else DEFAULT_LOCAL_PICKLE

    if explicit_path:
        # FIX (01/10/2026): una ruta explicita se respeta tal cual, sin
        # tocar el bucket -- permite probar contra un pickle fijo o
        # sintetico a proposito (ej. durante desarrollo de este script).
        if not Path(pickle_path).is_file():
            print(f"No se encontro '{pickle_path}'.")
            sys.exit(1)
    else:
        # FIX (01/10/2026): sin ruta explicita, siempre refrescar desde el
        # bucket antes de analizar -- ver ensure_fresh_pickle().
        ensure_fresh_pickle(pickle_path)
        if not Path(pickle_path).is_file():
            print(
                f"No se pudo obtener '{pickle_path}' ni del bucket ni "
                "localmente. Descargalo manualmente, ej.:"
            )
            print(f"  gsutil cp {DEFAULT_BUCKET_PICKLE} .")
            sys.exit(1)

    real_type_counts, id_to_type, id_to_text, synced_at = load_catalog_data(pickle_path)

    # FIX (01/10/2026): el 'synced_at' se imprime SIEMPRE, sin importar de
    # donde vino el pickle -- defensa adicional para que la antiguedad de
    # los datos analizados nunca quede oculta, incluso si alguien pasa una
    # ruta explicita a un archivo viejo a proposito.
    print("\n" + "=" * 78)
    print(f"Fuente: '{pickle_path}'  |  Catalogo sincronizado desde Shopify: {synced_at}")
    print("=" * 78)

    run_coverage_and_desync_audit(real_type_counts)
    run_mistagging_audit(id_to_type, id_to_text)


if __name__ == "__main__":
    main()
