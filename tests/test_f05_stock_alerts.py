import pytest

from src.api.integrations.shopify_client import (
    _build_variant_inventory_map,
    _calculate_stock_alert_level,
    _calculate_stock_status,
)


def test_build_variant_inventory_map_keeps_confirmed_zero_stock_variants():
    variants_nodes = [
        {"title": "XS / Negro", "inventoryQuantity": 0, "availableForSale": False},
        {"title": "S / Negro", "inventoryQuantity": 0, "availableForSale": False},
        {"title": "M / Negro", "inventoryQuantity": 0, "availableForSale": False},
        {"title": "L / Negro", "inventoryQuantity": 0, "availableForSale": False},
    ]

    variant_inventory = _build_variant_inventory_map(variants_nodes)

    assert variant_inventory == {"XS": 0, "S": 0, "M": 0, "L": 0}
    assert _calculate_stock_alert_level(variant_inventory) is None
    assert _calculate_stock_status(variant_inventory) == "out_of_stock"


def test_build_variant_inventory_map_skips_variants_without_inventory_signal():
    variants_nodes = [
        {"title": "XS / Negro", "inventoryQuantity": None, "availableForSale": False},
        {"title": "S / Negro", "inventoryQuantity": None, "availableForSale": True},
    ]

    variant_inventory = _build_variant_inventory_map(variants_nodes)

    assert variant_inventory == {"S": 0}
