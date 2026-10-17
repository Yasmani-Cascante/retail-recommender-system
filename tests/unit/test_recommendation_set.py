"""
Tests del contrato de recomendaciones (principal / alternatives).

Spec: SPEC_Contrato_Recomendaciones_06102026.md

A diferencia de los tests de f08_similarity_resolution, estos NO son de
caracterizacion: el modulo es nuevo, asi que fijan el comportamiento
DESEADO, no el heredado. Cada test cita la decision de producto o el
defecto de produccion que lo motiva.

Ejecutar:
    pytest tests/unit/test_recommendation_set.py -v
"""
import pytest

from src.recommenders.recommendation_set import (
    INTENT_CATEGORY_QUERY,
    INTENT_GENERIC,
    INTENT_OUTFIT_COMPLEMENT,
    INTENT_SIMILARITY,
    MAX_ALTERNATIVES,
    MAX_ALTERNATIVES_TARGET,
    ORIGIN_BEHAVIORAL,
    ORIGIN_CATALOG,
    ORIGIN_VISUAL,
    Block,
    RecommendationSet,
    RequestSpec,
    _read_max_alternatives,
    belongs_to_principal,
    reorder_by_collection,
    reorder_within_blocks,
    tag_origin,
)


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def item(pid, ptype, **product_data):
    """Item con el esquema de normalize_recommendation_dict (lo relevante)."""
    return {
        "id": str(pid),
        "title": f"Producto {pid}",
        "score": 1.0,
        "product_data": {"id": str(pid), "product_type": ptype, **product_data},
    }


def type_of(it):
    return (it.get("product_data") or {}).get("product_type", "")


def collections_of(it):
    raw = (it.get("product_data") or {}).get("collections", []) or []
    if isinstance(raw, str):
        raw = [c.strip() for c in raw.split(",") if c.strip()]
    return {c.lower() for c in raw}


BAGS = RequestSpec(categories={"CARTERAS"})


# ════════════════════════════════════════════════════════════════════
# Particion: cada intencion define que es "lo pedido"
# ════════════════════════════════════════════════════════════════════

class TestParticionPorIntencion:
    """
    Decision de producto (Yasmani, 06/10/2026): `principal` se define por la
    INTENCION, no por la categoria. Asi las cuatro rutas usan la misma
    funcion sin casos especiales.
    """

    def test_similitud_principal_es_el_tipo_del_ancla(self):
        items = [item(1, "CARTERAS"), item(2, "CINTURONES"), item(3, "CARTERAS")]
        r = RecommendationSet.build(
            INTENT_SIMILARITY, items, BAGS, 8, type_of, anchor_type="CARTERAS")
        assert [i["id"] for i in r.principal.items] == ["1", "3"]
        assert [i["id"] for i in r.alternatives.items] == ["2"]

    def test_outfit_mezclar_categorias_ES_lo_pedido(self):
        """
        Bajo outfit, un collar que completa un vestido va en PRINCIPAL:
        bajo esa intencion el collar ES lo pedido. No es un defecto.
        """
        req = RequestSpec(categories={"COLLARES", "AROS"})
        items = [item(1, "COLLARES"), item(2, "AROS"), item(3, "VESTIDOS CORTOS")]
        r = RecommendationSet.build(INTENT_OUTFIT_COMPLEMENT, items, req, 8, type_of)
        assert len(r.principal) == 2
        assert [i["id"] for i in r.alternatives.items] == ["3"]

    def test_category_query_principal_es_lo_detectado_en_el_texto(self):
        req = RequestSpec(categories={"CLUTCH", "CARTERAS"})
        items = [item(1, "CLUTCH"), item(2, "AROS"), item(3, "CARTERAS")]
        r = RecommendationSet.build(INTENT_CATEGORY_QUERY, items, req, 8, type_of)
        assert [i["id"] for i in r.principal.items] == ["1", "3"]

    def test_generic_todo_es_principal(self):
        items = [item(1, "CARTERAS"), item(2, "AROS")]
        r = RecommendationSet.build(INTENT_GENERIC, items, RequestSpec(), 8, type_of)
        assert len(r.principal) == 2
        assert len(r.alternatives) == 0

    def test_intent_invalido_falla_pronto(self):
        with pytest.raises(ValueError):
            RecommendationSet.build("loquesea", [], BAGS, 8, type_of)


class TestPredicadoDePertenencia:

    def test_categoria_insensible_a_mayusculas(self):
        assert belongs_to_principal(item(1, "carteras"), BAGS, type_of)

    def test_sin_categorias_todo_pertenece(self):
        assert belongs_to_principal(item(1, "AROS"), RequestSpec(), type_of)

    def test_producto_sin_tipo_no_pertenece_si_se_pidio_una(self):
        assert not belongs_to_principal(item(1, ""), BAGS, type_of)

    def test_atributo_duro_filtra(self):
        """
        Preparado para la busqueda por color (BACKLOG_Busqueda_por_Atributos).
        Hoy `attributes` llega siempre vacio en las cuatro rutas.
        """
        req = RequestSpec(categories={"VESTIDOS CORTOS"}, attributes={"color": "verde"})
        verde = item(1, "VESTIDOS CORTOS", color="Verde")
        azul = item(2, "VESTIDOS CORTOS", color="Azul")
        assert belongs_to_principal(verde, req, type_of)
        assert not belongs_to_principal(azul, req, type_of)

    def test_atributos_vacios_no_cambian_nada(self):
        con = RequestSpec(categories={"CARTERAS"}, attributes={})
        sin = RequestSpec(categories={"CARTERAS"})
        it = item(1, "CARTERAS")
        assert belongs_to_principal(it, con, type_of) == belongs_to_principal(it, sin, type_of)


# ════════════════════════════════════════════════════════════════════
# E2: el orden nunca cruza bloques
# ════════════════════════════════════════════════════════════════════

class TestOrdenEntreBloques:
    """
    Defecto E2, observado el 05/10/2026: un Cinturon en posicion 5 por encima
    de un Clutch en posicion 6, pedidos "bolsos similares". Causa: los
    candidatos visuales arrancaban en score 1.0 y el relleno de catalogo en
    last-0.05, asi que una categoria ajena superaba a la pedida.
    """

    def test_las_alternativas_van_siempre_despues(self):
        items = [item(1, "CINTURONES"), item(2, "CINTURONES"), item(3, "CARTERAS")]
        r = RecommendationSet.build(INTENT_SIMILARITY, items, BAGS, 8, type_of)
        flat = r.to_flat_list()
        assert flat[0]["id"] == "3"                      # la cartera, aunque llego la ultima
        assert [i["id"] for i in flat[1:]] == ["1", "2"]

    def test_el_orden_dentro_de_cada_bloque_se_preserva(self):
        """build() separa, no reordena por parecido."""
        items = [item(i, "CARTERAS") for i in (5, 1, 9)]
        r = RecommendationSet.build(INTENT_SIMILARITY, items, BAGS, 8, type_of)
        assert [i["id"] for i in r.principal.items] == ["5", "1", "9"]

    def test_aplanado_es_concatenacion_exacta(self):
        items = [item(1, "CARTERAS"), item(2, "AROS")]
        r = RecommendationSet.build(INTENT_SIMILARITY, items, BAGS, 8, type_of)
        assert r.to_flat_list() == r.principal.items + r.alternatives.items


# ════════════════════════════════════════════════════════════════════
# Regla de tope
# ════════════════════════════════════════════════════════════════════

class TestTopeDeAlternativas:
    """
    Decision de Yasmani (06/10/2026): min(n - len(principal), tope).

    Estos tests fijan la REGLA, asi que pasan el tope explicito. El valor en
    vigor es configurable y se cubre aparte en TestTopeConfigurable -- de otro
    modo cambiar la variable de entorno romperia tests que no van de eso.
    """

    @pytest.mark.parametrize("n_principal,n_alt_disp,esperado_alt,esperado_total", [
        (6, 6, 2, 8),
        (4, 6, 4, 8),
        (2, 6, 4, 6),   # NO 6: tope duro
        (0, 6, 4, 4),   # NO 8: tope duro
        (8, 6, 0, 8),
        (3, 1, 1, 4),   # menos alternativas disponibles que hueco
    ])
    def test_tabla_de_la_spec_con_tope_4(self, n_principal, n_alt_disp,
                                         esperado_alt, esperado_total):
        items = ([item(f"p{i}", "CARTERAS") for i in range(n_principal)]
                 + [item(f"a{i}", "AROS") for i in range(n_alt_disp)])
        r = RecommendationSet.build(INTENT_SIMILARITY, items, BAGS, 8, type_of,
                                    max_alternatives=4)
        assert len(r.alternatives) == esperado_alt
        assert len(r.to_flat_list()) == esperado_total

    @pytest.mark.parametrize("n_principal,esperado_alt,esperado_total", [
        (6, 2, 8),
        (2, 6, 8),   # con tope 8 el tope no muerde: se completan los 8
        (0, 8, 8),
    ])
    def test_con_tope_8_el_total_no_cambia_respecto_a_hoy(self, n_principal,
                                                          esperado_alt, esperado_total):
        """
        Valor de despliegue actual. Con 8, la fase 1 cambia el ORDEN pero no
        CUANTOS productos se devuelven -- un cambio observable a la vez.
        """
        items = ([item(f"p{i}", "CARTERAS") for i in range(n_principal)]
                 + [item(f"a{i}", "AROS") for i in range(10)])
        r = RecommendationSet.build(INTENT_SIMILARITY, items, BAGS, 8, type_of,
                                    max_alternatives=8)
        assert len(r.alternatives) == esperado_alt
        assert len(r.to_flat_list()) == esperado_total

    def test_devolver_menos_de_n_es_deliberado(self):
        """
        Con el tope OBJETIVO (4). Seis resultados honestos valen mas que ocho
        con seis de relleno. Si este test falla, alguien reintrodujo el
        relleno a toda costa.
        """
        items = [item(1, "CARTERAS")] + [item(f"a{i}", "AROS") for i in range(10)]
        r = RecommendationSet.build(INTENT_SIMILARITY, items, BAGS, 8, type_of,
                                    max_alternatives=4)
        assert len(r.to_flat_list()) == 5      # 1 principal + 4 tope
        assert len(r.to_flat_list()) < 8

    def test_principal_puede_quedarse_vacio(self):
        """Decision de Yasmani: es honesto; el widget decide si dibuja el bloque."""
        items = [item(i, "AROS") for i in range(6)]
        r = RecommendationSet.build(INTENT_SIMILARITY, items, BAGS, 8, type_of,
                                    max_alternatives=4)
        assert len(r.principal) == 0
        assert len(r.alternatives) == 4

    def test_principal_se_recorta_a_lo_pedido(self):
        items = [item(i, "CARTERAS") for i in range(12)]
        r = RecommendationSet.build(INTENT_SIMILARITY, items, BAGS, 8, type_of)
        assert len(r.principal) == 8
        assert len(r.alternatives) == 0

    def test_sin_items_no_falla(self):
        r = RecommendationSet.build(INTENT_SIMILARITY, [], BAGS, 8, type_of)
        assert r.to_flat_list() == []
        assert r.to_prompt_facts()["principal_count"] == 0


# ════════════════════════════════════════════════════════════════════
# Tope configurable (RECS_MAX_ALTERNATIVES)
# ════════════════════════════════════════════════════════════════════

class TestTopeConfigurable:
    """
    Decision de Yasmani (06/10/2026): desplegar la fase 1 con el tope en 8
    para que cambie el ORDEN sin cambiar cuantos productos se devuelven, y
    bajarlo a 4 tras validar -- sin redeploy de imagen.
    """

    def test_valor_de_despliegue_actual_es_8(self):
        assert MAX_ALTERNATIVES == 8

    def test_el_objetivo_sigue_documentado_en_codigo(self):
        """Que el valor en vigor sea 8 no debe borrar la intencion de producto."""
        assert MAX_ALTERNATIVES_TARGET == 6

    def test_variable_de_entorno_manda(self, monkeypatch):
        monkeypatch.setenv("RECS_MAX_ALTERNATIVES", "4")
        assert _read_max_alternatives() == 4

    def test_se_aplica_en_caliente_sin_reimportar(self, monkeypatch):
        """
        build() resuelve el tope en cada llamada, no en el default de la
        firma (que se evalua una sola vez al importar). Asi un cambio de la
        variable en Cloud Run aplica sin redeploy de imagen.
        """
        items = [item(1, "CARTERAS")] + [item(f"a{i}", "AROS") for i in range(10)]
        monkeypatch.setenv("RECS_MAX_ALTERNATIVES", "8")
        assert len(RecommendationSet.build(
            INTENT_SIMILARITY, items, BAGS, 8, type_of).to_flat_list()) == 8
        monkeypatch.setenv("RECS_MAX_ALTERNATIVES", "4")
        assert len(RecommendationSet.build(
            INTENT_SIMILARITY, items, BAGS, 8, type_of).to_flat_list()) == 5

    @pytest.mark.parametrize("valor", ["", "   ", "abc", "4.5", "-1", "None"])
    def test_valor_invalido_degrada_al_de_despliegue(self, monkeypatch, valor):
        """Un tope mal configurado nunca debe tumbar las recomendaciones."""
        monkeypatch.setenv("RECS_MAX_ALTERNATIVES", valor)
        assert _read_max_alternatives() == 8

    def test_cero_desactiva_las_alternativas(self, monkeypatch):
        """0 es valido y significa 'solo lo pedido' -- util como palanca de emergencia."""
        monkeypatch.setenv("RECS_MAX_ALTERNATIVES", "0")
        items = [item(1, "CARTERAS"), item(2, "AROS")]
        r = RecommendationSet.build(INTENT_SIMILARITY, items, BAGS, 8, type_of)
        assert len(r.alternatives) == 0
        assert len(r.to_flat_list()) == 1

    def test_el_parametro_explicito_gana_a_la_variable(self, monkeypatch):
        monkeypatch.setenv("RECS_MAX_ALTERNATIVES", "8")
        items = [item(1, "CARTERAS")] + [item(f"a{i}", "AROS") for i in range(10)]
        r = RecommendationSet.build(INTENT_SIMILARITY, items, BAGS, 8, type_of,
                                    max_alternatives=2)
        assert len(r.alternatives) == 2


# ════════════════════════════════════════════════════════════════════
# exhausted: un campo, un solo significado
# ════════════════════════════════════════════════════════════════════

class TestExhausted:
    """
    El 04/10/2026 una senal con dos significados hizo que el LLM afirmara
    "son las ultimas capas disponibles" y en los dos turnos siguientes
    aparecieran 16 capas mas. Aqui es un booleano, no un campo reinterpretable.
    """

    def test_false_por_defecto(self):
        r = RecommendationSet.build(INTENT_SIMILARITY, [item(1, "CARTERAS")], BAGS, 8, type_of)
        assert r.principal.exhausted is False

    def test_lo_decide_la_ruta(self):
        r = RecommendationSet.build(
            INTENT_SIMILARITY, [item(1, "CARTERAS")], BAGS, 8, type_of, exhausted=True)
        assert r.principal.exhausted is True
        assert r.to_prompt_facts()["catalog_exhausted"] is True

    def test_principal_corto_NO_implica_agotado(self):
        """
        Clave: 2 de 8 porque el pool visual se quedo corto NO significa que
        el catalogo este agotado. Es la distincion que gobierna el boton de
        "ver <categoria> otra vez" en UI.
        """
        items = [item(1, "CARTERAS"), item(2, "CARTERAS")]
        r = RecommendationSet.build(INTENT_SIMILARITY, items, BAGS, 8, type_of)
        assert len(r.principal) < 8
        assert r.principal.exhausted is False

    def test_el_bloque_de_alternativas_nunca_lo_marca(self):
        items = [item(1, "AROS")]
        r = RecommendationSet.build(INTENT_SIMILARITY, items, BAGS, 8, type_of, exhausted=True)
        assert r.alternatives.exhausted is False


# ════════════════════════════════════════════════════════════════════
# Procedencia y parecido real (E3)
# ════════════════════════════════════════════════════════════════════

class TestProcedencia:
    """
    Defecto E3: el "% match" nunca midio nada. Era score_start - rank*step.
    El embedding-service SI calcula la similitud coseno y la descarta con `_`
    (seccion 2.3 de la spec).
    """

    def test_visual_lleva_rank_y_score(self):
        out = tag_origin(item(1, "CARTERAS"), ORIGIN_VISUAL, visual_rank=3, visual_score=0.87)
        assert (out["origin"], out["visual_rank"], out["visual_score"]) == (ORIGIN_VISUAL, 3, 0.87)

    @pytest.mark.parametrize("origin", [ORIGIN_CATALOG, ORIGIN_BEHAVIORAL])
    def test_no_visual_no_tiene_parecido_medido(self, origin):
        """
        None y no 0.0: 0.0 significaria "medido y pesimo". El widget solo
        debe mostrar porcentaje donde visual_score no es None.
        """
        out = tag_origin(item(1, "CARTERAS"), origin)
        assert out["visual_score"] is None
        assert out["visual_rank"] is None

    def test_no_muta_el_item_original(self):
        orig = item(1, "CARTERAS")
        tag_origin(orig, ORIGIN_VISUAL, visual_rank=0)
        assert "origin" not in orig

    def test_origin_invalido_falla_pronto(self):
        with pytest.raises(ValueError):
            tag_origin(item(1, "CARTERAS"), "inventado")

    def test_principal_puede_mezclar_procedencias(self):
        """Bolsos del pool visual + bolsos del catalogo: todos son bolsos."""
        items = [tag_origin(item(1, "CARTERAS"), ORIGIN_VISUAL, visual_rank=0, visual_score=0.9),
                 tag_origin(item(2, "CARTERAS"), ORIGIN_CATALOG)]
        r = RecommendationSet.build(INTENT_SIMILARITY, items, BAGS, 8, type_of)
        assert len(r.principal) == 2
        assert [i["origin"] for i in r.principal.items] == [ORIGIN_VISUAL, ORIGIN_CATALOG]


# ════════════════════════════════════════════════════════════════════
# Bonus de coleccion DENTRO de cada bloque
# ════════════════════════════════════════════════════════════════════

class TestBonusDeColeccion:
    """
    Decision de Yasmani (06/10/2026): incluido en este trabajo.
    El `sorted` global del handler romperia los bloques en cuanto exista el
    contrato.
    """

    def test_sube_dentro_del_bloque(self):
        a = item(1, "CARTERAS", collections=["Fiesta"])
        b = item(2, "CARTERAS", collections=["Playa"])
        out = reorder_by_collection([b, a], {"fiesta"}, collections_of)
        assert [i["id"] for i in out] == ["1", "2"]

    def test_nunca_atraviesa_bloques(self):
        """
        La alternativa comparte coleccion con el ancla y el principal no.
        Aun asi, la alternativa NO puede adelantar. Es el test que protege
        la garantia de to_flat_list().
        """
        principal = item(1, "CARTERAS", collections=["Playa"])
        alt = item(2, "AROS", collections=["Fiesta"])
        r = RecommendationSet.build(INTENT_SIMILARITY, [principal, alt], BAGS, 8, type_of)
        out = reorder_within_blocks(r, {"fiesta"}, collections_of)
        assert [i["id"] for i in out.to_flat_list()] == ["1", "2"]

    def test_preserva_orden_dentro_de_cada_grupo(self):
        items = [item(1, "CARTERAS", collections=["Playa"]),
                 item(2, "CARTERAS", collections=["Fiesta"]),
                 item(3, "CARTERAS", collections=["Playa"]),
                 item(4, "CARTERAS", collections=["Fiesta"])]
        out = reorder_by_collection(items, {"fiesta"}, collections_of)
        assert [i["id"] for i in out] == ["2", "4", "1", "3"]

    def test_sin_colecciones_no_toca_nada(self):
        items = [item(1, "CARTERAS"), item(2, "CARTERAS")]
        assert reorder_by_collection(items, set(), collections_of) == items

    def test_no_altera_ninguna_puntuacion(self):
        """
        El mecanismo anterior sumaba 0.15 a similarity_score. Cuando el score
        sea la similitud coseno real, corromperlo volveria a inventar numeros.
        """
        it = tag_origin(item(1, "CARTERAS", collections=["Fiesta"]),
                        ORIGIN_VISUAL, visual_rank=0, visual_score=0.80)
        out = reorder_by_collection([it], {"fiesta"}, collections_of)
        assert out[0]["visual_score"] == 0.80
        assert out[0]["score"] == 1.0

    def test_colecciones_como_csv(self):
        """El catalogo las entrega como lista o como string CSV."""
        it = item(1, "CARTERAS", collections="Fiesta, Novia")
        assert collections_of(it) == {"fiesta", "novia"}


# ════════════════════════════════════════════════════════════════════
# Hechos para el LLM (E4)
# ════════════════════════════════════════════════════════════════════

class TestPromptFacts:
    """
    E4: el 05/10 el LLM no menciono la mezcla ni cuando el prompt se lo
    pedia. Hechos estructurados en vez de instrucciones.
    """

    def test_cuenta_los_dos_bloques(self):
        items = [item(1, "CARTERAS"), item(2, "CARTERAS"), item(3, "AROS"), item(4, "CINTURONES")]
        f = RecommendationSet.build(INTENT_SIMILARITY, items, BAGS, 8, type_of).to_prompt_facts()
        assert f["principal_count"] == 2
        assert f["alternatives_count"] == 2
        assert f["principal_categories"] == ["CARTERAS"]
        assert f["alternatives_categories"] == ["AROS", "CINTURONES"]

    def test_categorias_en_orden_de_aparicion_sin_duplicados(self):
        items = [item(1, "AROS"), item(2, "CINTURONES"), item(3, "AROS")]
        r = RecommendationSet.build(INTENT_SIMILARITY, items, BAGS, 8, type_of)
        assert r.alternatives.categories == ["AROS", "CINTURONES"]

    def test_incluye_intencion_y_categoria_pedida(self):
        f = RecommendationSet.build(
            INTENT_SIMILARITY, [item(1, "CARTERAS")], BAGS, 8, type_of).to_prompt_facts()
        assert f["intent"] == INTENT_SIMILARITY
        assert f["requested_category"] == "CARTERAS"

    def test_sin_categoria_pedida_es_none(self):
        f = RecommendationSet.build(
            INTENT_GENERIC, [item(1, "AROS")], RequestSpec(), 8, type_of).to_prompt_facts()
        assert f["requested_category"] is None

    def test_caso_real_05102026(self):
        """
        Clutch Antai: 8 productos, solo 2 bolsos. Hoy el LLM no recibia nada
        y hablo de "un look mas completo y elegante". Con esto recibe las
        cuentas, y mencionarlas es lo natural.
        """
        items = [item(1, "CARTERAS"), item(2, "CARTERAS")] + [
            item(i, t) for i, t in enumerate(["AROS", "BRAZALETES", "AROS", "COLLARES"], start=3)]
        f = RecommendationSet.build(INTENT_SIMILARITY, items, BAGS, 8, type_of).to_prompt_facts()
        assert (f["principal_count"], f["alternatives_count"]) == (2, 4)
        assert f["catalog_exhausted"] is False


# ════════════════════════════════════════════════════════════════════
# Compatibilidad y serializacion
# ════════════════════════════════════════════════════════════════════

class TestCompatibilidad:

    def test_el_esquema_por_item_se_preserva(self):
        """Fase 1 no debe romper a ningun consumidor actual."""
        it = item(1, "CARTERAS")
        r = RecommendationSet.build(INTENT_SIMILARITY, [it], BAGS, 8, type_of)
        out = r.to_flat_list()[0]
        for campo in ("id", "title", "score", "product_data"):
            assert campo in out

    def test_api_dict_es_serializable(self):
        import json
        items = [item(1, "CARTERAS"), item(2, "AROS")]
        r = RecommendationSet.build(
            INTENT_SIMILARITY, items, BAGS, 8, type_of,
            anchor_id="999", anchor_type="CARTERAS", route="f08c")
        d = r.to_api_dict()
        json.dumps(d)
        assert d["meta"]["route"] == "f08c"
        assert d["principal"]["exhausted"] is False

    def test_el_set_es_inmutable(self):
        r = RecommendationSet.build(INTENT_SIMILARITY, [item(1, "CARTERAS")], BAGS, 8, type_of)
        with pytest.raises(Exception):
            r.intent = "otro"

    def test_len_del_bloque(self):
        assert len(Block(items=[item(1, "CARTERAS")])) == 1
