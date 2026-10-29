"""
Tests de LFM2ColBERTClient.search_filtered() -- E5 nivel 2, paso 3 (26/10/2026).
Spec: SPEC_E5_Nivel2_Busqueda_Filtrada_17102026.md, secciones 4 y 6.2.

Sin red ni Google: la autenticacion IAM se desactiva (EMBEDDING_AUTH_DISABLED)
y el cliente HTTP interno se sustituye por uno con un transporte simulado que
REGISTRA cada peticion. Asi se comprueba el contenido exacto que se enviaria
al embedding-service y como se interpreta cada tipo de respuesta.
"""
import json

import httpx
import pytest
import pytest_asyncio

from src.api.services.colbert_client import FilteredVisualResult, LFM2ColBERTClient

URL = "https://embedding.example"


def ok_body(**over):
    body = {"product_ids": ["p1", "p2"], "scores": [0.91, 0.87], "anchor_found": True,
            "eligible_count": 40, "unknown_ids": 1, "latency_ms": 0.6, "visual_index_size": 3041}
    body.update(over)
    return body


# pytest_asyncio.fixture (no pytest.fixture): funciona con asyncio_mode
# 'auto' (pytest.ini del repo) y tambien en modo 'strict'.
@pytest_asyncio.fixture
async def make_client(monkeypatch):
    """Fabrica de clientes con un transporte simulado. Devuelve (cliente, peticiones)."""
    monkeypatch.setenv("COLBERT_SERVICE_URL", URL)
    monkeypatch.setenv("EMBEDDING_AUTH_DISABLED", "true")
    created = []

    async def factory(handler):
        requests = []

        def recording(request):
            requests.append(request)
            return handler(request)

        client = LFM2ColBERTClient()
        await client._http.aclose()  # el real no se usa: se cierra para no dejar recursos abiertos
        client._http = httpx.AsyncClient(base_url=URL, transport=httpx.MockTransport(recording))
        created.append(client)
        return client, requests

    yield factory
    for c in created:
        await c._http.aclose()


@pytest.mark.asyncio
async def test_peticion_y_respuesta_correctas(make_client):
    client, reqs = await make_client(lambda r: httpx.Response(200, json=ok_body()))
    res = await client.search_filtered("123", include_ids=["a", 7], exclude_ids=[5, "6"],
                                       top_k=50, boost_text="chaqueta", alpha=0.4)
    assert isinstance(res, FilteredVisualResult)
    assert res.pairs == [("p1", 0.91), ("p2", 0.87)]
    assert (res.anchor_found, res.eligible_count, res.unknown_ids) == (True, 40, 1)
    assert len(reqs) == 1 and reqs[0].method == "POST"
    assert reqs[0].url.path == "/v1/embed/search-filtered"
    assert json.loads(reqs[0].content) == {
        "product_id": "123", "include_ids": ["a", "7"], "exclude_ids": ["5", "6"],
        "top_k": 50, "alpha": 0.4, "boost_text": "chaqueta"}


@pytest.mark.asyncio
async def test_sin_filtro_de_tipo_ni_texto_no_envia_esos_campos(make_client):
    """include_ids=None significa SIN restriccion: el campo NO debe enviarse
    (una lista vacia significaria 'nada admitido'). Sin boost_text, tampoco."""
    client, reqs = await make_client(lambda r: httpx.Response(200, json=ok_body()))
    await client.search_filtered("123", include_ids=None, exclude_ids=None, boost_text="")
    body = json.loads(reqs[0].content)
    assert "include_ids" not in body and "boost_text" not in body
    assert body["exclude_ids"] == []


@pytest.mark.asyncio
async def test_ancla_no_indexada_no_es_un_fallo(make_client):
    client, _ = await make_client(lambda r: httpx.Response(
        200, json=ok_body(product_ids=[], scores=[], anchor_found=False, eligible_count=0)))
    res = await client.search_filtered("NO")
    assert res.anchor_found is False and res.pairs == []
    assert client._visual_failures == 0


@pytest.mark.asyncio
async def test_respuesta_sin_campos_del_contrato_cuenta_como_fallo(make_client):
    """Sin anchor_found no se puede distinguir 'nada elegible' de 'ancla no
    indexada'. Suponer un valor llevaria a una decision equivocada."""
    body = ok_body(); del body["anchor_found"]
    client, _ = await make_client(lambda r: httpx.Response(200, json=body))
    assert await client.search_filtered("123") is None
    assert client._visual_failures == 1


@pytest.mark.asyncio
async def test_404_devuelve_none_y_cuenta_fallo(make_client):
    """Lo que pasaria con una revision del servicio SIN el endpoint."""
    client, _ = await make_client(lambda r: httpx.Response(404, json={"detail": "Not Found"}))
    assert await client.search_filtered("123") is None
    assert client._visual_failures == 1


@pytest.mark.asyncio
async def test_timeout_devuelve_none(make_client):
    def boom(request):
        raise httpx.ReadTimeout("timeout", request=request)
    client, _ = await make_client(boom)
    assert await client.search_filtered("123") is None
    assert client._visual_failures == 1


@pytest.mark.asyncio
async def test_tres_fallos_abren_el_circuito_y_no_se_hacen_mas_peticiones(make_client):
    """El circuit breaker VISUAL es COMPARTIDO con las demas busquedas
    visuales: por eso importa el orden de marcha atras del flag."""
    client, reqs = await make_client(lambda r: httpx.Response(404))
    for _ in range(3):
        await client.search_filtered("123")
    assert client._visual_circuit_open is True
    assert await client.search_filtered("123") is None
    assert len(reqs) == 3  # la cuarta no llego a enviarse


@pytest.mark.asyncio
async def test_exito_reinicia_el_contador_de_fallos(make_client):
    client, _ = await make_client(lambda r: httpx.Response(200, json=ok_body()))
    client._visual_failures = 2
    await client.search_filtered("123")
    assert client._visual_failures == 0


@pytest.mark.asyncio
async def test_scores_ausentes_degradan_a_none(make_client):
    """Misma degradacion que el resto de busquedas visuales: sin parecido
    medido no se inventa un porcentaje."""
    body = ok_body(); del body["scores"]
    client, _ = await make_client(lambda r: httpx.Response(200, json=body))
    res = await client.search_filtered("123")
    assert res.pairs == [("p1", None), ("p2", None)]
