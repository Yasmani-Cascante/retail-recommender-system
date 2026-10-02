"""
Tests para f08b_target_categories.resolve_f08b_target_categories
======================================================================

Cubre el comportamiento de F-08B principal: auto-referencia, especificidad,
el sistema de conflictos de slot (incluyendo "conjunto", integrado
27/09/2026), la excepcion accessory/bag (multi-tipo, no se auto-excluyen
por completo), y las sugerencias genericas via product_taxonomy.py.

Ejecutar:
    pytest tests/unit/test_f08b_target_categories.py -v
"""
import pytest

from src.recommenders.f08b_target_categories import resolve_f08b_target_categories


# ════════════════════════════════════════════════════════════════════
# STUBS -- misma taxonomia de prueba que test_f08b2_category_resolution.py,
# ampliada con "conjunto" (ahora en sugerencias genericas, 27/09/2026) e
# "intimates" (sigue excluido).
# ════════════════════════════════════════════════════════════════════

_AVAILABLE_CATEGORIES = {
    "ZAPATOS", "VESTIDOS LARGOS", "VESTIDOS CORTOS",
    "AROS", "COLLARES", "BRAZALETES", "CLUTCH", "CARTERAS",
    "TOPS", "PANTALONES", "CONJUNTOS FALDAS", "LENCERIA",
}

_SLOT_TYPES = {
    "accessory": ["AROS", "COLLARES", "BRAZALETES"],
    "bag": ["CARTERAS", "CLUTCH"],
    "dress": ["VESTIDOS LARGOS", "VESTIDOS CORTOS"],
    "shoes": ["ZAPATOS"],
    "top": ["TOPS"],
    "bottom": ["PANTALONES"],
    "conjunto": ["CONJUNTOS FALDAS"],
    "intimates": ["LENCERIA"],
}

_TYPE_TO_SLOT = {t: slot for slot, types in _SLOT_TYPES.items() for t in types}

# Candidatos genericos = todos los buckets menos "intimates" (mismo criterio
# que product_taxonomy.generic_suggestion_candidate_slots() desde 27/09/2026
# -- "conjunto" ya NO esta excluido).
_GENERIC_CANDIDATES = sorted(set(_SLOT_TYPES.keys()) - {"intimates"})


def stub_extract_categories(query: str, available):
    q = query.lower()
    detected = []
    if "accesorio" in q:
        detected += ["AROS", "COLLARES", "BRAZALETES", "CLUTCH", "CARTERAS"]
    if "zapato" in q:
        detected.append("ZAPATOS")
    if "vestidos" in q:
        detected += ["VESTIDOS LARGOS", "VESTIDOS CORTOS"]
    if "aros" in q:
        detected.append("AROS")
    if "arete" in q:
        detected.append("AROS")
    if "collar" in q and "este collar" not in q:
        detected.append("COLLARES")
    if "conjunto" in q:
        detected.append("CONJUNTOS FALDAS")
    seen, out = set(), []
    for c in detected:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return [c for c in out if c in available]


def stub_get_concrete_categories():
    return set(_AVAILABLE_CATEGORIES)


def stub_get_outfit_slot(t: str):
    return _TYPE_TO_SLOT.get(t.upper())


def stub_generic_suggestion_candidate_slots():
    return list(_GENERIC_CANDIDATES)


def resolve(query: str, anchor_type: str):
    return resolve_f08b_target_categories(
        conversation_query=query,
        anchor_product_type=anchor_type,
        extract_categories_fn=stub_extract_categories,
        get_concrete_categories_fn=stub_get_concrete_categories,
        get_outfit_slot_fn=stub_get_outfit_slot,
        generic_suggestion_candidate_slots_fn=stub_generic_suggestion_candidate_slots,
    )


# ════════════════════════════════════════════════════════════════════
# Auto-referencia y especificidad -- mismo comportamiento que F-08B.2
# ════════════════════════════════════════════════════════════════════

class TestAutoReferenciaYEspecificidad:

    def test_auto_referencia_se_filtra(self):
        """"esto aros" sobre ancla AROS no debe colarse como pedido nuevo."""
        target_cats, single_type, _ = resolve("Con que vestidos combina esto aros?", "AROS")
        assert set(target_cats) == {"dress"}
        assert single_type is None

    def test_pedido_especifico_unico_no_expande_por_bucket(self):
        """"aretes" sobre ancla BRAZALETES -> single_specific_type=AROS, sin expandir."""
        target_cats, single_type, was_explicit = resolve("Con que aretes puedo combinar esto?", "BRAZALETES")
        assert single_type == "AROS"
        assert target_cats == ["accessory"]  # el bucket SI se pasa a la busqueda (Fase 1b lo filtra despues)

    def test_pedido_amplio_no_fija_single_specific_type(self):
        target_cats, single_type, was_explicit = resolve("Que accesorios combinan con esto?", "VESTIDOS LARGOS")
        assert single_type is None
        assert set(target_cats) == {"accessory", "bag"}

    def test_was_explicit_request_true_para_pedido_amplio_explicito(self):
        """
        Caso que motivo agregar este tercer valor de retorno: un pedido
        amplio pero EXPLICITO ("accesorios") debe distinguirse de una
        consulta generica -- el llamador replica el log original
        "F-08B query category detected" solo en este caso.
        """
        _, _, was_explicit = resolve("Que accesorios combinan con esto?", "VESTIDOS LARGOS")
        assert was_explicit is True

    def test_was_explicit_request_false_para_consulta_generica(self):
        _, _, was_explicit = resolve("que combina con esto?", "VESTIDOS LARGOS")
        assert was_explicit is False


# ════════════════════════════════════════════════════════════════════
# Sistema de conflictos de slot -- incluye "conjunto" (27/09/2026)
# ════════════════════════════════════════════════════════════════════

class TestConflictosDeSlot:

    def test_ancla_vestido_excluye_top_bottom_enterito_y_conjunto(self):
        """Pedido generico sobre un vestido no debe incluir top/bottom/conjunto."""
        target_cats, _, was_explicit = resolve("que combina con esto?", "VESTIDOS LARGOS")
        assert "top" not in target_cats
        assert "bottom" not in target_cats
        assert "conjunto" not in target_cats
        assert "dress" not in target_cats  # propio bucket, tambien excluido

    def test_ancla_conjunto_excluye_dress_top_bottom(self):
        """
        Caso real que motivo el fix (27/09/2026): antes, un ancla "conjunto"
        no excluia dress/top/bottom -- podia sugerir una prenda suelta junto
        a un conjunto ya completo.
        """
        target_cats, _, _ = resolve("que combina con esto?", "CONJUNTOS FALDAS")
        assert "dress" not in target_cats
        assert "top" not in target_cats
        assert "bottom" not in target_cats
        assert "conjunto" not in target_cats  # propio bucket

    def test_conjunto_aparece_para_ancla_sin_conflicto(self):
        """
        Caso real (27/09/2026): "conjunto" salio de GENERIC_SUGGESTION_
        EXCLUDED_SLOTS -- para un ancla que no conflictua con el (zapatos),
        ahora debe aparecer como candidato.
        """
        target_cats, _, _ = resolve("que combina con esto?", "ZAPATOS")
        assert "conjunto" in target_cats


# ════════════════════════════════════════════════════════════════════
# Excepcion accessory/bag -- multi-tipo, no se auto-excluyen por completo
# ════════════════════════════════════════════════════════════════════

class TestExcepcionAccessoryBag:

    def test_ancla_aros_permite_sugerir_el_bucket_accessory_completo(self):
        """
        FIX historico (14/07/2026): auto-excluir el bucket ENTERO cuando el
        ancla es de ese bucket bloqueaba sugerir un COLLAR sobre un ancla
        AROS (ambos "accessory"). accessory/bag son la excepcion.
        """
        target_cats, _, _ = resolve("que combina con esto?", "AROS")
        assert "accessory" in target_cats  # NO se auto-excluye

    def test_ancla_cartera_permite_sugerir_el_bucket_bag_completo(self):
        target_cats, _, _ = resolve("que combina con esto?", "CARTERAS")
        assert "bag" in target_cats


# ════════════════════════════════════════════════════════════════════
# Casos limite
# ════════════════════════════════════════════════════════════════════

class TestCasosLimite:

    def test_deteccion_que_falla_cae_al_comportamiento_amplio(self):
        """Si extract_categories_fn lanza excepcion, cae al fallback amplio, sin propagar."""
        def failing_extract(query, available):
            raise RuntimeError("fallo simulado")
        target_cats, single_type, was_explicit = resolve_f08b_target_categories(
            "que combina con esto?", "VESTIDOS LARGOS",
            failing_extract, stub_get_concrete_categories,
            stub_get_outfit_slot, stub_generic_suggestion_candidate_slots,
        )
        assert single_type is None
        assert "dress" not in target_cats  # propio bucket sigue excluido (calculado antes del try)
        assert "top" not in target_cats    # conflicto sigue aplicando

    def test_ancla_tipo_desconocido_no_rompe(self):
        """Un tipo de ancla sin outfit_slot conocido no debe romper -- own_cat queda ''."""
        target_cats, single_type, _ = resolve("que combina con esto?", "TURBANTES")
        assert isinstance(target_cats, list)
        assert len(target_cats) > 0

    def test_anchor_type_en_minuscula_se_normaliza(self):
        r_lower = resolve("Con que aretes puedo combinar esto?", "brazaletes")
        r_upper = resolve("Con que aretes puedo combinar esto?", "BRAZALETES")
        assert r_lower == r_upper
