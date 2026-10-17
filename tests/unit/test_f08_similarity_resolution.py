"""
Tests de caracterizacion para f08_similarity_resolution
=========================================================

PASO 1 (02/10/2026): estos tests fijan el comportamiento ACTUAL de F-08
Fase A y F-08C -- incluidas sus divergencias y el bug conocido de la
etiqueta de agotamiento -- no el comportamiento deseado. Cuando el paso 2
corrija una divergencia, el test correspondiente DEBE fallar y
actualizarse en el mismo commit: asi el cambio queda como decision
visible, no como efecto colateral. Los tests marcados "PASO 2" en su
docstring son exactamente esos.

Contexto completo: DCT_Cierre_Sesion_01102026.md, Addendum A.
Equivalencia con el codigo inline original: verificada aparte con un arnes
de caracterizacion (40.000 casos aleatorios, 0 divergencias, 6/6 mutantes
detectados) -- ver Addendum A, seccion A.6.

Ejecutar:
    pytest tests/unit/test_f08_similarity_resolution.py -v
"""
import pytest

from src.recommenders.f08_similarity_resolution import (
    F08A_ROUTE,
    F08C_ROUTE,
    POOL_EMPTY,
    POOL_HAPPY,
    POOL_PARTIAL,
    SIGNAL_CATALOG_EXHAUSTED,
    _read_visual_pool_cap,
    build_fill_exclusion,
    build_partial_exhaustion_info,
    build_partial_fill_events,
    candidate_breakdown,
    classify_pool,
    fill_score_start,
    filter_visual_candidates,
    filter_fill_to_request,
    interleave_by_subtype,
    order_candidates,
    principal_first_enabled,
    resolve_similarity_categories,
    split_candidates_by_request,
    visual_pool_size,
)


# ════════════════════════════════════════════════════════════════════
# STUBS
# ════════════════════════════════════════════════════════════════════
#
# _PARENT_MAP replica los grupos padre REALES de CATEGORY_KEYWORDS
# (improved_fallback_exclude_seen.py) relevantes para estos tests, EN EL
# MISMO ORDEN que el archivo real -- el orden importa (ACCESSORIES antes que
# JOYAS decide el grupo de AROS/COLLARES/BRAZALETES, ver hallazgo A.3.b).

_PARENT_MAP = {
    "VESTIDOS": ["VESTIDOS LARGOS", "VESTIDOS CORTOS", "VESTIDOS MIDIS"],
    "CAPAS": ["CAPAS BORDADAS", "CAPAS GASA"],
    "ACCESSORIES": ["AROS", "COLLARES", "BRAZALETES", "BRAZALETE", "CLUTCH",
                    "CINTURONES", "CARTERAS", "TOCADOS", "ALAS DE NOVIA"],
    "JOYAS": ["AROS", "COLLARES", "BRAZALETES", "BRAZALETE"],
}
_ACCESSORIES = _PARENT_MAP["ACCESSORIES"]


def parent_map_fn():
    # Copia defensiva: igual que el real, cada llamada devuelve listas nuevas.
    return {k: list(v) for k, v in _PARENT_MAP.items()}


def failing_parent_map_fn():
    raise RuntimeError("CATEGORY_KEYWORDS no disponible")


def make_type_of(index):
    """type_of() sobre un dict pid -> product_type; "" si el pid no existe."""
    return lambda pid: index.get(str(pid), "")


# ════════════════════════════════════════════════════════════════════
# Etapa 1 -- resolucion de categorias, F-08 Fase A (solo el ancla decide)
# ════════════════════════════════════════════════════════════════════

class TestResolucionF08A:

    def test_ancla_con_grupo_padre_expande_a_hermanas_en_mayusculas(self):
        res = resolve_similarity_categories(F08A_ROUTE, "Capas Gasa", None, parent_map_fn)
        assert res.categories == ["CAPAS BORDADAS", "CAPAS GASA"]
        assert res.anchor_type_for_ranking == "CAPAS GASA"
        assert res.source == "parent_group"
        assert res.expansion_error is None

    def test_ancla_sin_grupo_padre_usa_tipo_exacto(self):
        """KIMONOS no tiene grupo padre en CATEGORY_KEYWORDS (A.3.c)."""
        res = resolve_similarity_categories(F08A_ROUTE, "KIMONOS", None, parent_map_fn)
        assert res.categories == ["KIMONOS"]
        assert res.source == "exact_type"

    def test_divergencia_a_ignora_categorias_del_texto(self):
        """
        PASO 2 (decision de producto): A nunca consulta el texto de la query.
        "collares parecidos a este" viendo unos AROS en Turn 1 -> se ignora
        "collares", se resuelve por el ancla.
        """
        res = resolve_similarity_categories(F08A_ROUTE, "AROS", ["COLLARES"], parent_map_fn)
        assert res.categories == _ACCESSORIES
        assert res.source == "parent_group"

    def test_fallo_de_expansion_degrada_al_tipo_exacto(self):
        res = resolve_similarity_categories(F08A_ROUTE, "aros", None, failing_parent_map_fn)
        assert res.categories == ["AROS"]
        assert res.anchor_type_for_ranking == "AROS"
        assert "CATEGORY_KEYWORDS no disponible" in res.expansion_error

    def test_sin_tipo_de_ancla_no_hay_filtro_ni_ranking(self):
        res = resolve_similarity_categories(F08A_ROUTE, "", None, parent_map_fn)
        assert res.categories == []
        assert res.anchor_type_for_ranking is None
        assert res.source == "none"

    def test_ancla_none_lanza_igual_que_el_original(self):
        """
        Fidelidad: el original hace _f08_ptype.upper() sin proteger None;
        la excepcion la captura el try externo del handler (fallback TF-IDF).
        """
        with pytest.raises(AttributeError):
            resolve_similarity_categories(F08A_ROUTE, None, None, parent_map_fn)


# ════════════════════════════════════════════════════════════════════
# Etapa 1 -- resolucion de categorias, F-08C (el texto manda)
# ════════════════════════════════════════════════════════════════════

class TestResolucionF08C:

    def test_sin_texto_expande_por_contexto_y_protege_ancla(self):
        """'similar a este' sobre un Collar -> familia completa, Collar priorizado."""
        res = resolve_similarity_categories(F08C_ROUTE, "COLLARES", [], parent_map_fn)
        assert res.categories == _ACCESSORIES
        assert res.anchor_type_for_ranking == "COLLARES"
        assert res.source == "parent_group"

    def test_texto_que_incluye_al_ancla_protege_ancla(self):
        """
        FIX 18/07/2026, caso real: "Muestrame accesorios similares" sobre un
        Collar -- el texto detecta la familia, que incluye COLLARES.
        """
        res = resolve_similarity_categories(F08C_ROUTE, "COLLARES", _ACCESSORIES, parent_map_fn)
        assert res.categories == _ACCESSORIES
        assert res.anchor_type_for_ranking == "COLLARES"
        assert res.source == "query_text"

    def test_texto_que_excluye_al_ancla_respeta_pedido_explicito(self):
        """'muestrame bolsos' viendo un Collar: no se prioriza COLLARES."""
        res = resolve_similarity_categories(
            F08C_ROUTE, "COLLARES", ["CARTERAS", "CLUTCH"], parent_map_fn)
        assert res.categories == ["CARTERAS", "CLUTCH"]
        assert res.anchor_type_for_ranking is None

    def test_sin_grupo_padre_conserva_mayusculas_originales(self):
        """
        Fidelidad: en C el tipo exacto se usa TAL CUAL (sin .upper()), a
        diferencia de A. Solo afecta a la etiqueta de agotamiento.
        """
        res = resolve_similarity_categories(F08C_ROUTE, "Kimonos", [], parent_map_fn)
        assert res.categories == ["Kimonos"]
        assert res.anchor_type_for_ranking == "KIMONOS"

    def test_fallo_de_expansion_mantiene_ranking_fijado_antes(self):
        res = resolve_similarity_categories(F08C_ROUTE, "AROS", [], failing_parent_map_fn)
        assert res.categories == ["AROS"]
        assert res.anchor_type_for_ranking == "AROS"
        assert res.expansion_error is not None

    def test_query_categories_none_equivale_a_vacio(self):
        a = resolve_similarity_categories(F08C_ROUTE, "AROS", None, parent_map_fn)
        b = resolve_similarity_categories(F08C_ROUTE, "AROS", [], parent_map_fn)
        assert a == b


# ════════════════════════════════════════════════════════════════════
# Contrato implicito: doble grupo padre (hallazgo A.3.b)
# ════════════════════════════════════════════════════════════════════

class TestDobleGrupoPadre:

    @pytest.mark.parametrize("route", [F08A_ROUTE, F08C_ROUTE])
    @pytest.mark.parametrize("anchor", ["AROS", "COLLARES", "BRAZALETES", "BRAZALETE"])
    def test_tipos_de_joyeria_resuelven_a_accessories_no_a_joyas(self, route, anchor):
        """
        PASO 2: hoy gana ACCESSORIES (9 tipos) solo por orden de insercion.
        Si se decide hacerlo explicito (o cambiar a JOYAS), este test cambia.
        """
        res = resolve_similarity_categories(route, anchor, [], parent_map_fn)
        assert [c.upper() for c in res.categories] == _ACCESSORIES

    def test_el_orden_del_mapa_decide_el_grupo(self):
        """Documenta POR QUE el contrato es fragil: invertir el orden cambia el resultado."""
        reordered = {"JOYAS": _PARENT_MAP["JOYAS"], "ACCESSORIES": _ACCESSORIES}
        res = resolve_similarity_categories(F08A_ROUTE, "AROS", None, lambda: reordered)
        assert res.categories == ["AROS", "COLLARES", "BRAZALETES", "BRAZALETE"]


# ════════════════════════════════════════════════════════════════════
# Etapa 2 -- filtrado del pool
# ════════════════════════════════════════════════════════════════════

class TestFiltrado:

    INDEX = {"1": "AROS", "2": "VESTIDOS CORTOS", "3": "COLLARES", "9": "AROS"}

    def test_excluye_ancla_vistos_y_otras_categorias_preservando_orden(self):
        out = filter_visual_candidates(
            ["9", "2", "3", "1", "x"], anchor_pid="9",
            categories=["AROS", "COLLARES"], type_of=make_type_of(self.INDEX),
            exclude_ids={"1"},
        )
        assert out == ["3"]

    def test_sin_categorias_no_filtra_por_tipo(self):
        out = filter_visual_candidates(
            ["1", "2", "x"], "9", [], make_type_of(self.INDEX), set())
        assert out == ["1", "2", "x"]

    def test_comparacion_de_categoria_insensible_a_mayusculas(self):
        out = filter_visual_candidates(
            ["1", "3"], "9", ["aros"], make_type_of(self.INDEX), set())
        assert out == ["1"]

    def test_producto_fuera_del_indice_nunca_pasa_con_categorias(self):
        """Precondicion de interleave_by_subtype: ningun candidato sin tipo llega a ella."""
        out = filter_visual_candidates(["x"], "9", ["AROS"], make_type_of(self.INDEX), set())
        assert out == []

    def test_breakdown_mismo_formato_que_los_logs(self):
        out = candidate_breakdown(["1", "3", "9"], make_type_of(self.INDEX))
        assert out == {"AROS": 2, "COLLARES": 1}


# ════════════════════════════════════════════════════════════════════
# Etapa 3 -- orden: particion T8 + intercalado NIVEL 1
# ════════════════════════════════════════════════════════════════════

class TestOrden:

    # Caso real T8 (05/07 y 18/07/2026): "similar a" un Collar devolvia
    # 5 Aros + 2 Chocker + 1 Collar, ordenado solo por similitud visual.
    INDEX = {
        "a1": "AROS", "a2": "AROS", "a3": "AROS", "a4": "AROS", "a5": "AROS",
        "b1": "BRAZALETES", "c1": "COLLARES", "c2": "COLLARES",
    }
    POOL = ["a1", "a2", "b1", "a3", "c1", "a4", "a5", "c2"]

    def test_interleave_round_robin_por_subtipo(self):
        t = make_type_of(self.INDEX)
        assert interleave_by_subtype(["a1", "a2", "a3", "c1", "b1"], t) == [
            "a1", "c1", "b1", "a2", "a3"]

    def test_f08a_particion_t8_mas_intercalado(self):
        out = order_candidates(F08A_ROUTE, self.POOL, "COLLARES", make_type_of(self.INDEX))
        # Collares primero; luego hermanas intercaladas (AROS, BRAZALETES, AROS...)
        assert out == ["c1", "c2", "a1", "b1", "a2", "a3", "a4", "a5"]

    def test_f08c_particion_t8_sin_intercalado(self):
        """
        PASO 2 (brecha inversa A->C): C no intercala -- las hermanas quedan
        en orden de similitud puro, AROS puede monopolizar el relleno.
        """
        out = order_candidates(F08C_ROUTE, self.POOL, "COLLARES", make_type_of(self.INDEX))
        assert out == ["c1", "c2", "a1", "a2", "b1", "a3", "a4", "a5"]

    @pytest.mark.parametrize("route", [F08A_ROUTE, F08C_ROUTE])
    def test_sin_ancla_de_ranking_no_reordena(self, route):
        out = order_candidates(route, self.POOL, None, make_type_of(self.INDEX))
        assert out == self.POOL


# ════════════════════════════════════════════════════════════════════
# Etapa 4 -- caminos y senales de agotamiento
# ════════════════════════════════════════════════════════════════════

class TestCaminos:

    @pytest.mark.parametrize("n_cand,n,expected", [
        (8, 8, POOL_HAPPY), (12, 8, POOL_HAPPY),
        (7, 8, POOL_PARTIAL), (1, 8, POOL_PARTIAL),
        (0, 8, POOL_EMPTY),
    ])
    def test_umbrales(self, n_cand, n, expected):
        assert classify_pool(n_cand, n) == expected


class TestRellenoParcial:

    def test_eventos_con_peso_extra_al_ancla(self):
        ev = build_partial_fill_events(F08C_ROUTE, ["CAPAS BORDADAS", "CAPAS GASA"], "CAPAS GASA")
        types = [e["product_info"]["product_type"] for e in ev]
        assert types == ["CAPAS BORDADAS", "CAPAS GASA", "CAPAS GASA"]
        assert ev[2]["product_info"]["source"] == "f08c_partial_fill_anchor_boost"
        assert all(e["source"] == "f08c_partial_fill" for e in ev)

    def test_tags_por_ruta(self):
        ev = build_partial_fill_events(F08A_ROUTE, ["AROS"], "AROS")
        assert ev[0]["source"] == "f08a_partial_fill"
        assert ev[1]["product_info"]["source"] == "f08a_partial_fill_anchor_boost"

    def test_exclusion_vistos_mas_candidatos_mas_ancla(self):
        assert build_fill_exclusion({"s1"}, ["v1", "v2"], "anc") == {"s1", "v1", "v2", "anc"}

    def test_relleno_suficiente_no_agota(self):
        assert build_partial_exhaustion_info(["AROS"], 3, 5, 5) is None

    def test_bug_conocido_etiqueta_es_primer_hermano(self):
        """
        PASO 2 -- BUG CONOCIDO (hallazgo A.3.a), conservado a proposito:
        ancla CAPAS GASA, relleno insuficiente -> se reporta CAPAS BORDADAS.
        Cuando se corrija, este test debe cambiar a "CAPAS GASA".
        """
        info = build_partial_exhaustion_info(["CAPAS BORDADAS", "CAPAS GASA"], 2, 1, 6)
        assert info == {"category": "CAPAS BORDADAS", "shown_count": 3, "total_count": 3,
                        "kind": SIGNAL_CATALOG_EXHAUSTED}

    def test_kind_es_catalog_exhausted(self):
        """
        PASO 2 (04/10/2026): aqui el agotamiento SI esta respaldado -- se
        pidieron n_needed con strict_category=True y no habia tantos. Es la
        unica de las dos senales que autoriza al LLM a decir "ya te los
        mostre todos".
        """
        info = build_partial_exhaustion_info(["PANTALONES"], 4, 1, 4)
        assert info["kind"] == SIGNAL_CATALOG_EXHAUSTED

    def test_sin_categorias_etiqueta_generica(self):
        info = build_partial_exhaustion_info([], 1, 0, 3)
        assert info["category"] == "esta categoria"

    @pytest.mark.parametrize("last,expected", [(None, 0.90), (1.0, 0.95), (0.7666, 0.7166)])
    def test_score_inicial_del_relleno(self, last, expected):
        assert fill_score_start(last) == expected


# ════════════════════════════════════════════════════════════════════
# Configuracion de rutas: inventario explicito de divergencias
# ════════════════════════════════════════════════════════════════════

class TestInventarioDeDivergencias:
    """
    Fija la tabla A.2 del Addendum. Si un campo cambia, debe ser una
    decision consciente del paso 2 (y este test se actualiza con ella).
    """

    def test_f08a(self):
        r = F08A_ROUTE
        assert (r.use_query_categories, r.uppercase_sibling_categories,
                r.interleave_siblings,
                r.faiss_top_k, r.visual_score_step) == (False, True, True, 30, 0.03)
        assert (r.visual_source, r.fill_source) == ("visual_search_f08", "categorized_fill_f08a")

    def test_f08c(self):
        r = F08C_ROUTE
        assert (r.use_query_categories, r.uppercase_sibling_categories,
                r.interleave_siblings,
                r.faiss_top_k, r.visual_score_step) == (True, False, False, 50, 0.02)
        assert (r.visual_source, r.fill_source) == (
            "visual_diversification_f08c", "categorized_fill_f08c")

    def test_configs_inmutables(self):
        with pytest.raises(Exception):
            F08A_ROUTE.interleave_siblings = False  # frozen dataclass


# ═════════════════════════════════════════════════════════════════════
# NIVEL 1 del plan E5: el pool crece con lo ya mostrado
# ═════════════════════════════════════════════════════════════════════

class TestTamanoDelPoolVisual:
    """
    Gap E5 (06/10/2026). El filtro de categoria y la exclusion de vistos se
    aplican DESPUES del recorte top_k, asi que un pool fijo se consume en
    productos ya descartados. Evidencia: 05/10/2026, con 80 vistos solo 3 de
    50 vecinos sobrevivieron y ninguno era de la categoria pedida, teniendo el
    catalogo material sin mostrar.
    """

    def test_sin_nada_mostrado_es_el_base(self):
        assert visual_pool_size(F08C_ROUTE, 0, cap=200) == 50
        assert visual_pool_size(F08A_ROUTE, 0, cap=200) == 30

    def test_crece_con_lo_mostrado(self):
        assert visual_pool_size(F08C_ROUTE, 80, cap=200) == 130

    def test_el_caso_real_del_05102026(self):
        """Con 80 vistos el pool pasa de 50 a 130: 80 huecos mas para sobrevivir."""
        antes, ahora = F08C_ROUTE.faiss_top_k, visual_pool_size(F08C_ROUTE, 80, cap=200)
        assert ahora - antes == 80

    def test_el_tope_corta(self):
        assert visual_pool_size(F08C_ROUTE, 10_000, cap=200) == 200

    def test_un_tope_absurdo_degrada_al_base_no_por_debajo(self):
        """Un cap mal configurado no debe empeorar lo que ya funcionaba."""
        assert visual_pool_size(F08C_ROUTE, 80, cap=10) == 50

    def test_n_shown_negativo_no_encoge_el_pool(self):
        assert visual_pool_size(F08C_ROUTE, -5, cap=200) == 50

    def test_fase_a_en_turn_1_no_cambia(self):
        """
        En Turn 1 shown_products esta siempre vacio: el nivel 1 es un no-op
        para Fase A. Se cablea por simetria, no porque haga falta hoy.
        """
        assert visual_pool_size(F08A_ROUTE, 0, cap=200) == F08A_ROUTE.faiss_top_k

    def test_tope_configurable(self, monkeypatch):
        monkeypatch.setenv("RECS_VISUAL_POOL_CAP", "120")
        assert _read_visual_pool_cap() == 120
        assert visual_pool_size(F08C_ROUTE, 500) == 120

    @pytest.mark.parametrize("valor", ["", "  ", "abc", "0", "-3", "1.5"])
    def test_tope_invalido_degrada_al_default(self, monkeypatch, valor):
        monkeypatch.setenv("RECS_VISUAL_POOL_CAP", valor)
        assert _read_visual_pool_cap() == 200

    def test_base_configurable_iguala_las_dos_rutas(self, monkeypatch):
        """
        La base 30 de Fase A penalizaba al TURNO 1, que es donde n_shown es 0
        y el nivel 1 no puede compensar nada (07/10/2026, T1: 3 carteras de 30
        vecinos). Una sola variable iguala ambas rutas.
        """
        monkeypatch.setenv("RECS_VISUAL_POOL_BASE", "100")
        assert visual_pool_size(F08A_ROUTE, 0) == 100
        assert visual_pool_size(F08C_ROUTE, 0) == 100
        assert visual_pool_size(F08A_ROUTE, 20) == 120

    @pytest.mark.parametrize("valor", ["", "  ", "abc", "0", "-5"])
    def test_base_invalida_degrada_al_faiss_top_k_de_la_ruta(self, monkeypatch, valor):
        monkeypatch.setenv("RECS_VISUAL_POOL_BASE", valor)
        assert visual_pool_size(F08A_ROUTE, 0) == F08A_ROUTE.faiss_top_k
        assert visual_pool_size(F08C_ROUTE, 0) == F08C_ROUTE.faiss_top_k


# ════════════════════════════════════════════════════════════════════
# G1 -- la decision se toma sobre LO PEDIDO, no sobre el total
# ════════════════════════════════════════════════════════════════════

class TestSeparacionPorLoPedido:
    """
    Gap G1 (07/10/2026). Clasificar el pool por el TOTAL hacia que el sistema
    creyera tener "de sobra" cuando de lo pedido solo tenia uno.
    """

    INDEX = {"c1": "CARTERAS", "c2": "CARTERAS", "a1": "AROS",
             "a2": "AROS", "b1": "BRAZALETES", "k1": "CLUTCH"}

    # Pool REAL del turno T9 del 07/10/2026, tal como lo registro el log:
    # {'AROS': 4, 'CLUTCH': 1, 'CARTERAS': 1, 'BRAZALETES': 4, 'TOCADOS': 1}
    T9_INDEX = ({f"a{i}": "AROS" for i in range(4)}
                | {f"b{i}": "BRAZALETES" for i in range(4)}
                | {"k1": "CLUTCH", "c1": "CARTERAS", "t1": "TOCADOS"})

    def test_separa_preservando_el_orden(self):
        own, other = split_candidates_by_request(
            ["a1", "c1", "b1", "c2"], {"CARTERAS"}, make_type_of(self.INDEX))
        assert own == ["c1", "c2"]
        assert other == ["a1", "b1"]

    def test_caso_real_T9_del_07102026(self):
        """
        11 candidatos en el pool, de los cuales 1 solo es CARTERAS.

        ANTES: 11 >= 8 -> camino feliz. El sistema creia tener "de sobra",
        nunca pregunto al catalogo, devolvio 1 bolso y 7 joyas, y dejo
        exhausted=False aunque no supiera nada del stock.
        AHORA: own=1 < 8 -> camino parcial. Pregunta al catalogo.
        """
        pool = list(self.T9_INDEX)
        assert len(pool) == 11
        own, other = split_candidates_by_request(
            pool, {"CARTERAS"}, make_type_of(self.T9_INDEX))
        assert len(own) == 1 and len(other) == 10
        assert classify_pool(len(pool), 8) == POOL_HAPPY        # decision ANTERIOR
        assert classify_pool(len(own), 8) == POOL_PARTIAL       # decision NUEVA

    def test_con_G2_el_clutch_contaria_como_bolso(self):
        """
        Mismo pool de T9. Si CLUTCH contara como lo pedido (gap G2), serian 2
        en vez de 1 -- y el CLUTCH LEONOR no habria aparecido en 4a posicion
        por debajo de dos pares de aros (screenshot del 07/10/2026).
        Sigue siendo < 8, asi que el camino parcial no cambia.
        """
        own, _ = split_candidates_by_request(
            list(self.T9_INDEX), {"CARTERAS", "CLUTCH"}, make_type_of(self.T9_INDEX))
        assert len(own) == 2

    def test_insensible_a_mayusculas(self):
        own, _ = split_candidates_by_request(
            ["c1"], {"carteras"}, make_type_of(self.INDEX))
        assert own == ["c1"]

    def test_sin_categorias_todo_es_pedido(self):
        """Un ancla sin tipo no debe dejar el principal vacio por accidente."""
        own, other = split_candidates_by_request(
            ["a1", "c1"], set(), make_type_of(self.INDEX))
        assert own == ["a1", "c1"] and other == []

    def test_varias_categorias_pedidas(self):
        """Preparado para G2: CARTERAS y CLUTCH son el mismo bolso para quien compra."""
        own, other = split_candidates_by_request(
            ["c1", "k1", "a1"], {"CARTERAS", "CLUTCH"}, make_type_of(self.INDEX))
        assert own == ["c1", "k1"] and other == ["a1"]


class TestInterruptorPrincipalFirst:

    def test_activado_por_defecto(self, monkeypatch):
        monkeypatch.delenv("RECS_PRINCIPAL_FIRST", raising=False)
        assert principal_first_enabled() is True

    @pytest.mark.parametrize("valor", ["0", "false", "FALSE", "no", "off", " Off "])
    def test_se_puede_apagar_sin_redesplegar(self, monkeypatch, valor):
        monkeypatch.setenv("RECS_PRINCIPAL_FIRST", valor)
        assert principal_first_enabled() is False

    @pytest.mark.parametrize("valor", ["1", "true", "YES", "on"])
    def test_valores_afirmativos(self, monkeypatch, valor):
        monkeypatch.setenv("RECS_PRINCIPAL_FIRST", valor)
        assert principal_first_enabled() is True

    @pytest.mark.parametrize("valor", ["quiza", "2", ""])
    def test_valor_no_reconocido_degrada_al_default(self, monkeypatch, valor):
        monkeypatch.setenv("RECS_PRINCIPAL_FIRST", valor)
        assert principal_first_enabled() is True


# ════════════════════════════════════════════════════════════════════
# Defensa contra B2: el catalogo puede devolver cualquier cosa
# ════════════════════════════════════════════════════════════════════

class TestFiltroDelRelleno:
    """
    Gap B2 (vivo). `get_personalized_fallback` se salta strict_category
    cuando la categoria preferida queda en cero y cae a PRIORIDAD 3
    ("diverse"), que ignora las categorias.

    Evidencia de produccion (10/10/2026, T10):
        Preferred categories: ['CARTERAS', 'CLUTCH']
        Generated 8 diverse recommendations      <- ni un bolso
    """

    # Los 8 productos que devolvio el catalogo en T10, por tipo.
    T10_DIVERSE = [
        {"id": str(i), "product_type": t} for i, t in enumerate(
            ["LENCERIA", "AROS", "VESTIDOS CORTOS", "CALZONES",
             "TOPS", "AROS", "FALDAS", "PIJAMAS"])
    ]
    BOLSOS = {"CARTERAS", "CLUTCH"}

    def test_caso_real_T10_descarta_todo(self):
        assert filter_fill_to_request(self.T10_DIVERSE, self.BOLSOS) == []

    def test_la_lenceria_no_llega_al_usuario(self):
        """Lenceria entre las alternativas de un bolso -- reportado el 10/10."""
        out = filter_fill_to_request(self.T10_DIVERSE, self.BOLSOS)
        assert not any(p["product_type"] == "LENCERIA" for p in out)

    def test_asi_el_agotamiento_se_mide_bien(self):
        """
        Antes: 8 productos devueltos -> 8 >= 8 -> exhausted=False, aunque
        ninguno fuera un bolso. Eso bloqueaba el aviso y el boton de reinicio.
        """
        n = 8
        assert len(self.T10_DIVERSE) >= n          # la medida ANTERIOR
        assert len(filter_fill_to_request(self.T10_DIVERSE, self.BOLSOS)) < n  # la NUEVA

    def test_el_caso_sano_pasa_intacto(self):
        sano = [{"id": "a", "product_type": "CARTERAS"},
                {"id": "b", "product_type": "CLUTCH"},
                {"id": "c", "product_type": "AROS"}]
        assert [p["id"] for p in filter_fill_to_request(sano, self.BOLSOS)] == ["a", "b"]

    def test_preserva_el_orden(self):
        sano = [{"id": str(i), "product_type": "CARTERAS"} for i in (3, 1, 2)]
        assert [p["id"] for p in filter_fill_to_request(sano, self.BOLSOS)] == ["3", "1", "2"]

    def test_sin_categorias_pedidas_no_filtra(self):
        assert len(filter_fill_to_request(self.T10_DIVERSE, set())) == 8

    def test_insensible_a_mayusculas(self):
        out = filter_fill_to_request([{"id": "a", "product_type": "carteras"}], self.BOLSOS)
        assert len(out) == 1

    @pytest.mark.parametrize("raro", [{}, {"id": "x"}, {"id": "y", "product_type": None}])
    def test_productos_sin_tipo_se_descartan(self, raro):
        """Sin tipo legible no se puede afirmar que sea lo pedido."""
        assert filter_fill_to_request([raro], self.BOLSOS) == []

    def test_lista_vacia(self):
        assert filter_fill_to_request([], self.BOLSOS) == []


# ═════════════════════════════════════════════════════════════════════
# Senal de category_exhausted_info: las dos variantes nunca se confunden
# ═════════════════════════════════════════════════════════════════════

class TestTipoDeSenal:
    """
    PASO 2 (04/10/2026) -- FIX de senal sobrecargada.

    Antes, las dos funciones devolvian dicts indistinguibles y el motor de
    personalizacion trataba a las dos como agotamiento de catalogo, haciendo
    que el LLM afirmara en falso "ya te mostre todos los articulos".
    """

    INDEX = {"g1": "CAPAS GASA", "g2": "CAPAS GASA", "b1": "CAPAS BORDADAS"}

    def test_la_senal_de_agotamiento_viene_etiquetada(self):
        """
        Historia (10/10/2026): aqui habia un test que comparaba DOS senales,
        "catalog_exhausted" y "result_mixed". La segunda se elimino al quedar
        sin emisor: su informacion -- la composicion del resultado -- ya no
        viaja por esta senal sino por la ESTRUCTURA del contrato
        (principal / alternatives). Ver el comentario de SIGNAL_CATALOG_EXHAUSTED.
        """
        exhausted = build_partial_exhaustion_info(["CAPAS GASA"], 2, 0, 3)
        assert exhausted["kind"] == SIGNAL_CATALOG_EXHAUSTED

    def test_valores_estables(self):
        """Contrato con mcp_personalization_engine.py: no renombrar a la ligera."""
        assert SIGNAL_CATALOG_EXHAUSTED == "catalog_exhausted"

    def test_default_del_consumidor_preserva_los_call_sites_manuales(self):
        """
        El handler construye el dict a mano en dos sitios (smart_fallback
        "Caso B" y el Caso A de queries de categoria directa), sin la clave
        'kind'. El motor lee con .get("kind", SIGNAL_CATALOG_EXHAUSTED), que
        es justamente la semantica de esos dos sitios -- por eso no hubo que
        tocarlos. Este test fija ese contrato.
        """
        dict_sin_kind = {"category": "CLUTCH", "shown_count": 0, "total_count": 8}
        assert dict_sin_kind.get("kind", SIGNAL_CATALOG_EXHAUSTED) == SIGNAL_CATALOG_EXHAUSTED
