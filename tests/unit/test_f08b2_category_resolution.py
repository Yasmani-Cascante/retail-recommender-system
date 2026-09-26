"""
Tests para f08b2_category_resolution.resolve_f08b2_complement_types
======================================================================

Cubre, con los casos REALES reproducidos en produccion (20-21/09/2026), los
dos bugs corregidos esta semana y confirma que el comportamiento original
(mapa _OUTFIT_COMPLEMENT_MAP, casos amplios como "accesorios"/"vestidos")
sigue exactamente igual, sin regresiones.

Sirve como red de seguridad antes de la refactorizacion de unificacion de
taxonomia (Fase 2, roadmap) -- ver docstring de
src/recommenders/f08b2_category_resolution.py para el contexto completo.

Ejecutar:
    pytest tests/unit/test_f08b2_category_resolution.py -v
"""
import pytest

from src.recommenders.f08b2_category_resolution import (
    resolve_f08b2_complement_types,
    _OUTFIT_COMPLEMENT_MAP,
)


# ════════════════════════════════════════════════════════════════════
# STUBS de las dependencias inyectadas
# ════════════════════════════════════════════════════════════════════
#
# Replican, para las frases exactas usadas en estos tests, el comportamiento
# real de extract_categories_from_query() / get_concrete_categories() /
# types_in_outfit_slot() -- confirmado contra los logs de produccion del
# 20-24/09/2026, no inventado. No son un reemplazo de esas funciones reales;
# si su comportamiento cambia de forma incompatible, estos stubs deben
# actualizarse para seguir reflejando la realidad.

_AVAILABLE_CATEGORIES = {
    "ZAPATOS", "VESTIDOS LARGOS", "VESTIDOS CORTOS", "VESTIDOS MIDIS",
    "NOVIAS LARGOS", "NOVIAS CORTOS", "NOVIAS MIDIS",
    "AROS", "COLLARES", "BRAZALETES", "CLUTCH", "CINTURONES",
    "CARTERAS", "TOCADOS",
}

_SLOT_TYPES = {
    "accessory": ["AROS", "COLLARES", "BRAZALETES", "BRAZALETE",
                  "CINTURONES", "TOCADOS", "ALAS DE NOVIA"],
    "bag": ["CARTERAS", "CLUTCH"],
    "dress": ["VESTIDOS CORTOS", "VESTIDOS LARGOS", "VESTIDOS MIDIS",
              "NOVIAS LARGOS", "NOVIAS CORTOS", "NOVIAS MIDIS"],
    "shoes": ["ZAPATOS"],
}


def stub_extract_categories(query: str, available):
    """
    Replica el comportamiento real observado en logs para las frases
    exactas usadas en estos tests -- incluyendo la deteccion de auto-
    referencia via substring (asi es como extract_categories_from_query
    detecto 'AROS' en "esto aros" y 'COLLARES' NO en "este collar", per
    logs reales del 20-21/09/2026).
    """
    q = query.lower()
    detected = []
    if "accesorio" in q:
        detected += ["AROS", "COLLARES", "BRAZALETES", "CLUTCH",
                     "CINTURONES", "CARTERAS", "TOCADOS"]
    if "zapato" in q:
        detected.append("ZAPATOS")
    if "vestidos" in q:  # plural -- "vestido" singular (referencia al ancla) no dispara
        detected += ["VESTIDOS LARGOS", "VESTIDOS CORTOS", "VESTIDOS MIDIS"]
    if "aros" in q:
        detected.append("AROS")
    if "arete" in q:
        detected.append("AROS")
    seen, out = set(), []
    for c in detected:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return [c for c in out if c in available]


def stub_get_concrete_categories():
    return set(_AVAILABLE_CATEGORIES)


def stub_types_in_outfit_slot(slot: str):
    return list(_SLOT_TYPES.get(slot, []))


def resolve(query: str, anchor_type: str):
    """Helper para no repetir las 3 dependencias inyectadas en cada test."""
    return resolve_f08b2_complement_types(
        conversation_query=query,
        outfit_product_type=anchor_type,
        extract_categories_fn=stub_extract_categories,
        get_concrete_categories_fn=stub_get_concrete_categories,
        types_in_outfit_slot_fn=stub_types_in_outfit_slot,
    )


# ════════════════════════════════════════════════════════════════════
# Bug 1 (20/09/2026): auto-referencia al propio tipo del ancla
# ════════════════════════════════════════════════════════════════════

class TestAutoReferencia:
    """
    Antes del fix: mencionar el propio tipo del ancla en la consulta se
    trataba como un pedido nuevo, mezclando accesorios no pedidos.
    """

    def test_vestidos_mas_auto_referencia_a_aros_da_solo_vestidos(self):
        """
        Caso real (20/09/2026): "Con que vestidos combina mejor esto aros?",
        ancla AROS. Antes: mezclaba COLLARES/BRAZALETES. Ahora: solo vestidos.
        """
        result = resolve("Con que vestidos combina mejor esto aros?", "AROS")
        assert set(result) == {
            "VESTIDOS CORTOS", "VESTIDOS LARGOS", "VESTIDOS MIDIS",
            "NOVIAS LARGOS", "NOVIAS CORTOS", "NOVIAS MIDIS",
        }
        assert "COLLARES" not in result
        assert "BRAZALETES" not in result
        assert "AROS" not in result

    def test_aretes_mas_auto_referencia_a_collar_da_solo_aros(self):
        """
        Caso real (20/09/2026): "Que aretes puedo combinar este collar?",
        ancla COLLARES. Antes: mezclaba BRAZALETES/CINTURONES/etc. Ahora:
        solo AROS (la especificidad del pedido, ver Bug 2 mas abajo).
        """
        result = resolve("Que aretes puedo combinar este collar?", "COLLARES")
        assert result == ["AROS"]


# ════════════════════════════════════════════════════════════════════
# Bug 2 (20/09/2026): sobre-expansion de categoria especifica y unica
# ════════════════════════════════════════════════════════════════════

class TestEspecificidadNoSeExpande:
    """
    Antes del fix: un pedido especifico y unico (ej. "aretes") se mapeaba
    a su bucket completo (accessory), devolviendo collares/brazaletes/etc.
    ademas de aros.
    """

    def test_aretes_especifico_da_solo_aros_no_todo_el_bucket(self):
        """Caso real (20/09/2026): "Con que aretes puedo combinar esto?", ancla BRAZALETES."""
        result = resolve("Con que aretes puedo combinar esto?", "BRAZALETES")
        assert result == ["AROS"]

    def test_zapatos_especifico_da_solo_zapatos(self):
        """Caso real (20/09/2026): "Que zapatos combinan con este vestido?", ancla NOVIAS LARGOS."""
        result = resolve("Que zapatos combinan con este vestido?", "NOVIAS LARGOS")
        assert result == ["ZAPATOS"]


# ════════════════════════════════════════════════════════════════════
# Comportamiento original preservado: pedidos amplios SI expanden
# ════════════════════════════════════════════════════════════════════

class TestPedidoAmplioSiExpande:
    """
    Un pedido amplio (la deteccion YA devuelve multiples tipos, senal de
    que el usuario no fue especifico) debe seguir expandiendo por bucket,
    exactamente como antes de los fixes de esta semana -- sin regresion.
    """

    def test_accesorios_amplio_expande_a_todo_el_bucket_accessory_y_bag(self):
        """Caso real (20/09/2026): "Que accesorios combinan con este vestido?", ancla NOVIAS LARGOS."""
        result = resolve("Que accesorios combinan con este vestido?", "NOVIAS LARGOS")
        assert set(result) == {
            "AROS", "COLLARES", "BRAZALETES", "BRAZALETE",
            "CINTURONES", "TOCADOS", "ALAS DE NOVIA", "CARTERAS", "CLUTCH",
        }

    def test_vestidos_amplio_expande_a_todo_el_bucket_dress(self):
        """Caso real (20/09/2026): "Con que vestidos combina mejor?", ancla AROS."""
        result = resolve("Con que vestidos combina mejor?", "AROS")
        assert set(result) == {
            "VESTIDOS CORTOS", "VESTIDOS LARGOS", "VESTIDOS MIDIS",
            "NOVIAS LARGOS", "NOVIAS CORTOS", "NOVIAS MIDIS",
        }


# ════════════════════════════════════════════════════════════════════
# Caso historico: el bug original que motivo Fix 2 (Fase 1b, 28/07/2026)
# ════════════════════════════════════════════════════════════════════

class TestCasoHistoricoT8:
    """
    El caso que origino el "Fix 2" documentado en
    DCT_Fase1b_Composite_Embedding_F08B_Cierre_24072026.md, seccion 12.4:
    ancla AROS (accesorio) pidiendo una prenda (direccion nunca contemplada
    por _OUTFIT_COMPLEMENT_MAP, que solo tiene entradas para prendas).
    """

    def test_t8_ancla_aros_pidiendo_vestidos_ya_no_cae_al_mapa_de_accesorios(self):
        result = resolve("con que vestidos combina mejor?", "AROS")
        # Antes del Fix 2 original: ['COLLARES', 'CLUTCH', 'CINTURONES']
        assert "COLLARES" not in result or "VESTIDOS LARGOS" in result
        assert any("VESTIDOS" in t or "NOVIAS" in t for t in result)


# ════════════════════════════════════════════════════════════════════
# Sin categoria explicita: comportamiento original del mapa, sin cambios
# ════════════════════════════════════════════════════════════════════

class TestMapaOriginalSinCategoriaExplicita:
    """
    Cuando la consulta no tiene ninguna categoria explicita detectable,
    el comportamiento debe ser IDENTICO al de antes de los fixes de esta
    semana -- el mapa _OUTFIT_COMPLEMENT_MAP, sin tocar.
    """

    def test_consulta_generica_usa_el_mapa_para_tipo_de_prenda_conocido(self):
        result = resolve("que combina con esto?", "VESTIDOS LARGOS")
        assert result == _OUTFIT_COMPLEMENT_MAP["VESTIDOS LARGOS"]

    def test_ancla_tipo_accesorio_sin_entrada_cae_al_fallback_generico(self):
        """
        Caso real documentado (16-17/07/2026): ancla AROS DANAE (accesorio,
        sin entrada en el mapa) + consulta generica -> cae al fallback
        generico ["AROS", "COLLARES", "CLUTCH", "CINTURONES"], filtrando el
        propio tipo del ancla si coincide.
        """
        result = resolve("que combina con esto?", "AROS")
        assert result == ["COLLARES", "CLUTCH", "CINTURONES"]  # AROS excluido (es el ancla)

    def test_ancla_sin_entrada_ni_coincidencia_con_fallback_devuelve_los_4(self):
        result = resolve("que combina con esto?", "CARTERAS")
        assert result == ["AROS", "COLLARES", "CLUTCH", "CINTURONES"]


# ════════════════════════════════════════════════════════════════════
# Casos limite / adversariales
# ════════════════════════════════════════════════════════════════════

class TestCasosLimite:

    def test_deteccion_vacia_no_rompe_cae_al_mapa(self):
        """Si extract_categories_fn no encuentra nada, cae al mapa original."""
        def empty_extract(query, available):
            return []
        result = resolve_f08b2_complement_types(
            "asdkjhaskjdh", "VESTIDOS LARGOS",
            empty_extract, stub_get_concrete_categories, stub_types_in_outfit_slot,
        )
        assert result == _OUTFIT_COMPLEMENT_MAP["VESTIDOS LARGOS"]

    def test_deteccion_solo_auto_referencia_queda_vacia_cae_al_mapa(self):
        """
        Si lo unico detectado es el propio tipo del ancla (auto-referencia
        pura, sin ningun pedido real), debe caer al mapa -- no a una lista
        vacia silenciosa.
        """
        def only_self_extract(query, available):
            return ["AROS"]
        result = resolve_f08b2_complement_types(
            "esto aros", "AROS",
            only_self_extract, stub_get_concrete_categories, stub_types_in_outfit_slot,
        )
        assert result == ["COLLARES", "CLUTCH", "CINTURONES"]

    def test_anchor_type_en_minuscula_se_normaliza(self):
        """El tipo del ancla puede llegar en minuscula -- debe normalizarse."""
        result_lower = resolve("Con que aretes puedo combinar esto?", "brazaletes")
        result_upper = resolve("Con que aretes puedo combinar esto?", "BRAZALETES")
        assert result_lower == result_upper == ["AROS"]

    def test_nunca_incluye_el_propio_tipo_del_ancla(self):
        """Invariante general: el resultado nunca debe incluir el tipo del ancla."""
        casos = [
            ("Que accesorios combinan con esto?", "AROS"),
            ("Con que vestidos combina mejor?", "VESTIDOS LARGOS"),
            ("que combina con esto?", "CARTERAS"),
        ]
        for query, anchor in casos:
            result = resolve(query, anchor)
            assert anchor.upper() not in result
