"""
Tests de la busqueda visual filtrada -- E5 nivel 2, paso 1
(SPEC_E5_Nivel2_Busqueda_Filtrada_17102026.md, secciones 4, 5 y 8.1).

Ejecutar desde la carpeta del servicio (src/api/services/embedding-service),
con el entorno del servicio (faiss-cpu igual a produccion + pytest):
    python -m pytest tests -q

QUE SE PRUEBA Y POR QUE
-----------------------
1. EXACTITUD (la propiedad central de la spec, P2): para cualquier filtro,
   search_filtered(k) == "busqueda COMPLETA del indice, filtrada despues"[:k].
   La referencia usa la propia busqueda de FAISS con k = n (no un calculo con
   numpy): misma aritmetica, asi que no puede haber falsos fallos por empates
   de redondeo entre implementaciones.
2. RAMAS: ancla no indexada, nada elegible (sin llamar a FAISS), ids
   desconocidos, ancla dentro de include, k mayor que los elegibles, solo
   exclusiones (IDSelectorNot).
3. CACHE id -> posicion: se invalida en los 3 puntos donde cambia _id_map
   (reasignacion por carga/indexacion completa y extend incremental) y
   conserva la PRIMERA aparicion, como list.index().
4. PARIDAD DEL VECTOR COMPUESTO: _composite_query() se extrajo del metodo
   search_by_product_id_with_text_boost(); el resultado debe ser identico al
   del bloque original, copiado LITERALMENTE aqui como referencia.
5. ENDPOINT POST /v1/embed/search-filtered: 503 sin indice, forma de la
   respuesta y validacion de limites.

Ningun test carga el modelo FashionSigLIP: la instancia se crea sin pasar por
__init__ y se le inyectan un indice FAISS pequeno y un modelo simulado.
"""
import contextlib
import sys
import types
from pathlib import Path

import numpy as np
import pytest

# Import DIRECTO (no importorskip): si el entorno no tiene faiss, estos tests
# deben FALLAR de forma visible, no omitirse en silencio.
import faiss  # noqa: E402

# La carpeta del servicio se llama "embedding-service" (con guion): no es un
# paquete importable, asi que se anade al path para importar sus modulos.
SERVICE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))
import visual_retriever as vr  # noqa: E402

D = 32  # dimension pequena: la exactitud no depende de la dimension


# ════════════════════════════════════════════════════════════════════
# Modelo simulado (sin torch real si no esta instalado)
# ════════════════════════════════════════════════════════════════════

class FakeTensor:
    """Lo minimo que usa el codigo real sobre el tensor de texto:
    .norm(dim, keepdim), division, .float(), .cpu(), .numpy()."""

    def __init__(self, a):
        self.a = np.asarray(a, dtype=np.float32)

    def norm(self, dim=-1, keepdim=False):
        return FakeTensor(np.linalg.norm(self.a, axis=dim, keepdims=keepdim))

    def __truediv__(self, other):
        return FakeTensor(self.a / (other.a if isinstance(other, FakeTensor) else other))

    def float(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self.a


class FakeModel:
    """encode_text devuelve un vector determinista por texto (sin normalizar,
    para comprobar que el codigo normaliza)."""

    def __init__(self):
        self.calls = 0

    def encode_text(self, tokens):
        self.calls += 1
        seed = sum(ord(c) for c in tokens[0]) % (2**31)
        return FakeTensor(np.random.default_rng(seed).standard_normal((1, D)) * 3.0)


@pytest.fixture
def torch_available(monkeypatch):
    """Garantiza que `import torch` funcione dentro del codigo bajo prueba.
    Si torch real esta instalado (entorno del servicio), no se toca nada.
    Si no lo esta, se inyecta un modulo minimo con no_grad() SOLO durante el
    test (monkeypatch lo retira al terminar)."""
    import importlib.util
    if importlib.util.find_spec("torch") is None:  # comprueba sin importar
        fake = types.ModuleType("torch")
        fake.no_grad = contextlib.nullcontext
        monkeypatch.setitem(sys.modules, "torch", fake)


def make_retriever(n=300, seed=0, ids=None):
    """Instancia real de FashionSigLIPRetriever SIN __init__ (no carga el
    modelo), con un IndexFlatIP normalizado como el de produccion."""
    r = vr.FashionSigLIPRetriever.__new__(vr.FashionSigLIPRetriever)
    rng = np.random.default_rng(seed)
    x = rng.standard_normal((n, D)).astype(np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    index = faiss.IndexFlatIP(D)
    index.add(x)
    r._faiss_index = index
    r._id_map = list(ids) if ids is not None else [f"p{i}" for i in range(n)]
    r._category_map = []
    r._text_boost_cache = {}
    r._model = FakeModel()
    r._tokenizer = lambda texts: list(texts)
    return r


def reference(r, query_vec, anchor, include, exclude, k):
    """Verdad de referencia: ranking COMPLETO de FAISS, filtrado despues.
    Misma semantica que el filtro del monolito (spec, seccion 3)."""
    n = r._faiss_index.ntotal
    scores, idx = r._faiss_index.search(query_vec, n)
    excl = set(exclude) | {anchor}
    out = []
    for i, s in zip(idx[0], scores[0]):
        pid = r._id_map[i]
        if pid in excl:
            continue
        if include is not None and pid not in include:
            continue
        out.append((pid, float(s)))
    return out[:k]


def anchor_vec(r, pid):
    return r._faiss_index.reconstruct(r._id_map.index(pid)).reshape(1, -1)


# ════════════════════════════════════════════════════════════════════
# 1. Exactitud (propiedad P2 de la spec)
# ════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("seed", range(40))
@pytest.mark.asyncio
async def test_exactitud_frente_a_busqueda_completa_filtrada(seed):
    r = make_retriever(seed=seed)
    rng = np.random.default_rng(1000 + seed)
    anchor = f"p{rng.integers(300)}"
    mode = seed % 3  # 0: include, 1: solo exclusiones, 2: include vacio de verdad
    include = None if mode == 1 else [f"p{i}" for i in rng.choice(300, size=rng.integers(1, 120), replace=False)]
    exclude = [f"p{i}" for i in rng.choice(300, size=rng.integers(0, 60), replace=False)]
    k = int(rng.integers(1, 150))

    res = await r.search_filtered(anchor, include_ids=include, exclude_ids=exclude, top_k=k)

    expected = reference(r, anchor_vec(r, anchor), anchor,
                         set(include) if include is not None else None, exclude, k)
    assert res.anchor_found is True
    assert [p for p, _ in res.pairs] == [p for p, _ in expected]
    assert [s for _, s in res.pairs] == pytest.approx([s for _, s in expected], abs=1e-6)


# ════════════════════════════════════════════════════════════════════
# 2. Ramas
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ancla_no_indexada():
    r = make_retriever()
    res = await r.search_filtered("NO_EXISTE", include_ids=["p1"], exclude_ids=[], top_k=5)
    assert res.anchor_found is False
    assert res.pairs == []


@pytest.mark.asyncio
async def test_nada_elegible_no_llama_a_faiss(monkeypatch):
    """Rama vacia (hallazgo F7): el ancla existe pero todo lo permitido esta
    excluido. Debe responder anchor_found=True con 0 resultados, y no
    gastar una busqueda FAISS."""
    r = make_retriever()
    calls = []
    real_search = r._faiss_index.search
    monkeypatch.setattr(r._faiss_index, "search", lambda *a, **k: calls.append(1) or real_search(*a, **k))
    res = await r.search_filtered("p0", include_ids=["p1", "p2"], exclude_ids=["p1", "p2"], top_k=5)
    assert res.anchor_found is True
    assert res.pairs == []
    assert res.eligible_count == 0
    assert calls == []


@pytest.mark.asyncio
async def test_ids_desconocidos_se_cuentan_y_se_ignoran():
    r = make_retriever()
    res = await r.search_filtered("p0", include_ids=["p1", "X1", "X2"], exclude_ids=[], top_k=5)
    assert res.unknown_ids == 2
    assert [p for p, _ in res.pairs] == ["p1"]
    assert res.eligible_count == 1


@pytest.mark.asyncio
async def test_el_ancla_nunca_se_devuelve_aunque_este_en_include():
    r = make_retriever()
    res = await r.search_filtered("p0", include_ids=["p0", "p1", "p2"], exclude_ids=[], top_k=10)
    assert "p0" not in [p for p, _ in res.pairs]
    assert res.eligible_count == 2


@pytest.mark.asyncio
async def test_k_mayor_que_elegibles_no_devuelve_relleno():
    """FAISS rellena con -1 cuando hay menos resultados que k; no deben
    filtrarse como ids validos."""
    r = make_retriever()
    res = await r.search_filtered("p0", include_ids=["p1", "p2", "p3"], exclude_ids=[], top_k=50)
    assert len(res.pairs) == 3
    assert sorted(p for p, _ in res.pairs) == ["p1", "p2", "p3"]


@pytest.mark.asyncio
async def test_solo_exclusiones_usa_todo_el_indice_menos_lo_excluido():
    r = make_retriever(n=50)
    excl = [f"p{i}" for i in range(1, 50, 2)]  # impares
    res = await r.search_filtered("p0", include_ids=None, exclude_ids=excl, top_k=100)
    got = [p for p, _ in res.pairs]
    assert set(got) == {f"p{i}" for i in range(2, 50, 2)}
    assert res.eligible_count == 24  # 50 - 25 excluidos - el ancla


@pytest.mark.asyncio
async def test_sin_filtro_equivale_a_search_by_product_id():
    """Con include=None y sin exclusiones debe dar lo mismo que el endpoint
    existente (criterio de validacion del paso 1 en la spec, seccion 9)."""
    r = make_retriever()
    base = await r.search_by_product_id("p7", top_k=20, with_scores=True)
    res = await r.search_filtered("p7", include_ids=None, exclude_ids=[], top_k=20)
    assert [p for p, _ in res.pairs] == [p for p, _ in base]
    assert [s for _, s in res.pairs] == pytest.approx([s for _, s in base], abs=1e-6)


@pytest.mark.asyncio
async def test_duplicados_de_un_id_excluido_no_se_cuelan():
    """El selector excluye por POSICION (primera aparicion). Si un id excluido
    tiene un vector duplicado en otra posicion, el filtro por ID lo descarta.
    Se fuerza el duplicado copiando el vector del ancla al final del indice."""
    r = make_retriever(n=30)
    dup = r._faiss_index.reconstruct(0).reshape(1, -1)
    r._faiss_index.add(dup)               # posicion 30 = mismo vector que p0
    r._id_map.append("p0")                # ... y mismo id: duplicado del ancla
    res = await r.search_filtered("p0", include_ids=None, exclude_ids=[], top_k=40)
    assert "p0" not in [p for p, _ in res.pairs]


@pytest.mark.asyncio
async def test_eligible_count_ignora_exclusiones_desconocidas():
    """Excluir ids que el indice no conoce no debe restar elegibles."""
    r = make_retriever(n=20)
    res = await r.search_filtered("p0", include_ids=None, exclude_ids=["p1", "NO1", "NO2"], top_k=50)
    assert res.eligible_count == 18          # 20 - p0 (ancla) - p1
    assert len(res.pairs) == 18


@pytest.mark.asyncio
async def test_guarda_durante_el_intercambio_de_indice():
    """La indexacion completa asigna _faiss_index ANTES que _id_map
    (visual_retriever.py, ~674-675). En ese instante conviven un indice NUEVO
    mas pequeno y el mapa ANTIGUO mas largo: el selector admite posiciones
    que el indice ya no tiene y FAISS rellena con -1. Sin la guarda
    `0 <= idx`, id_map[-1] devolveria el ULTIMO id de la lista (aqui p9),
    un producto que nadie pidio."""
    r = make_retriever(n=10)
    small = faiss.IndexFlatIP(D)
    small.add(np.stack([r._faiss_index.reconstruct(i) for i in range(5)]))
    r._faiss_index = small                 # indice nuevo: 5 vectores; _id_map sigue con 10
    res = await r.search_filtered("p0", include_ids=[f"p{i}" for i in range(10)], exclude_ids=[], top_k=9)
    got = [p for p, _ in res.pairs]
    assert set(got) == {"p1", "p2", "p3", "p4"}
    assert "p9" not in got


# ════════════════════════════════════════════════════════════════════
# 3. Cache id -> posicion
# ════════════════════════════════════════════════════════════════════

def test_cache_conserva_la_primera_aparicion_como_list_index():
    r = make_retriever(n=5, ids=["a", "b", "a", "c", "b"])
    pos = r._positions()
    assert pos == {"a": 0, "b": 1, "c": 3}
    assert all(pos[k] == r._id_map.index(k) for k in pos)


def test_cache_se_invalida_al_reasignar_id_map():
    """Carga desde disco e indexacion completa REASIGNAN la lista."""
    r = make_retriever(n=3, ids=["a", "b", "c"])
    assert r._positions() == {"a": 0, "b": 1, "c": 2}
    r._id_map = ["c", "b", "a"]  # misma longitud, objeto nuevo
    assert r._positions() == {"c": 0, "b": 1, "a": 2}


def test_cache_se_invalida_al_extender_id_map():
    """La indexacion incremental EXTIENDE la misma lista."""
    r = make_retriever(n=3, ids=["a", "b", "c"])
    assert "d" not in r._positions()
    r._id_map.extend(["d"])
    assert r._positions()["d"] == 3


# ════════════════════════════════════════════════════════════════════
# 4. Paridad del vector compuesto (extraccion sin cambio de comportamiento)
# ════════════════════════════════════════════════════════════════════

def composite_original(r, pos, boost_text, alpha):
    """Copia LITERAL del bloque original de _reconstruct_text_boost_and_search
    (visual_retriever.py, ~lineas 1015-1034 al 20/10/2026), sin la busqueda."""
    import numpy as _np
    image_vec = r._faiss_index.reconstruct(pos)
    image_np  = _np.array(image_vec, dtype=_np.float32).reshape(1, -1)

    cached_text_np = r._text_boost_cache.get(boost_text)
    if cached_text_np is not None:
        text_np = cached_text_np
    else:
        import torch as _torch
        tokens = r._tokenizer([boost_text])
        with _torch.no_grad():
            text_embed = r._model.encode_text(tokens)
            text_embed = text_embed / text_embed.norm(dim=-1, keepdim=True)
        text_np = text_embed.float().cpu().numpy()
        r._text_boost_cache[boost_text] = text_np

    composite = alpha * image_np + (1.0 - alpha) * text_np
    norm      = _np.linalg.norm(composite, axis=-1, keepdims=True)
    composite = (composite / norm).astype(_np.float32)
    return composite


@pytest.mark.parametrize("alpha", [0.0, 0.3, 0.5, 0.85, 1.0])
def test_composite_identico_al_original_cache_miss_y_hit(torch_available, alpha):
    ref, new = make_retriever(seed=3), make_retriever(seed=3)
    for text in ["vestido corto elegante", "aros dorados"]:  # 1a vez: miss; 2a: hit
        for _ in range(2):
            a = composite_original(ref, 11, text, alpha)
            b = new._composite_query(11, text, alpha)
            assert b.dtype == np.float32 and b.shape == (1, D)
            np.testing.assert_array_equal(a, b)
    assert new._model.calls == 2  # una codificacion por texto: la cache funciona


@pytest.mark.asyncio
async def test_text_boost_existente_no_cambia(torch_available):
    """El metodo existente, ahora apoyado en _composite_query, devuelve lo
    mismo que el calculo original."""
    r = make_retriever(seed=5)
    got = await r.search_by_product_id_with_text_boost("p9", "falda", alpha=0.4, top_k=15, with_scores=True)
    q = composite_original(make_retriever(seed=5), 9, "falda", 0.4)
    expected = reference(r, q, "p9", None, [], 15)
    assert [p for p, _ in got] == [p for p, _ in expected]


@pytest.mark.parametrize("seed", range(10))
@pytest.mark.asyncio
async def test_exactitud_con_texto_de_refuerzo(torch_available, seed):
    r = make_retriever(seed=seed)
    rng = np.random.default_rng(seed)
    include = [f"p{i}" for i in rng.choice(300, size=80, replace=False)]
    res = await r.search_filtered("p4", include_ids=include, exclude_ids=["p5"], top_k=30,
                                  boost_text="chaqueta", alpha=0.6)
    q = composite_original(make_retriever(seed=seed), 4, "chaqueta", 0.6)
    expected = reference(r, q, "p4", set(include), ["p5"], 30)
    assert [p for p, _ in res.pairs] == [p for p, _ in expected]


# ════════════════════════════════════════════════════════════════════
# 5. Endpoint POST /v1/embed/search-filtered
# ════════════════════════════════════════════════════════════════════

@pytest.fixture
def client(monkeypatch):
    """Cliente HTTP SIN lifespan (no carga ColBERT ni FashionSigLIP): se
    sustituye el retriever global por uno de prueba."""
    from fastapi.testclient import TestClient
    import main
    monkeypatch.setattr(main, "visual_retriever", make_retriever())
    return TestClient(main.app), main


def test_endpoint_responde_con_los_campos_del_contrato(client):
    c, _ = client
    r = c.post("/v1/embed/search-filtered",
               json={"product_id": "p0", "include_ids": ["p1", "p2", "ZZ"], "exclude_ids": ["p2"], "top_k": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["anchor_found"] is True
    assert body["product_ids"] == ["p1"]
    assert len(body["scores"]) == 1
    assert body["eligible_count"] == 1
    assert body["unknown_ids"] == 1
    assert body["visual_index_size"] == 300


def test_endpoint_ancla_desconocida_no_es_error(client):
    c, _ = client
    r = c.post("/v1/embed/search-filtered", json={"product_id": "NO", "include_ids": ["p1"], "top_k": 5})
    assert r.status_code == 200
    assert r.json()["anchor_found"] is False and r.json()["product_ids"] == []


def test_endpoint_503_si_el_indice_no_esta_listo(client, monkeypatch):
    c, main = client
    monkeypatch.setattr(main, "visual_retriever", None)
    r = c.post("/v1/embed/search-filtered", json={"product_id": "p0", "top_k": 5})
    assert r.status_code == 503


@pytest.mark.parametrize("payload", [
    {"product_id": "p0", "top_k": 0},
    {"product_id": "p0", "top_k": 100000},
    {"product_id": "p0", "include_ids": [f"x{i}" for i in range(20001)]},
    {"product_id": "p0", "exclude_ids": [f"x{i}" for i in range(20001)]},
    {"product_id": "p0", "alpha": 1.5},
])
def test_endpoint_valida_limites(client, payload):
    c, _ = client
    assert c.post("/v1/embed/search-filtered", json=payload).status_code == 422
