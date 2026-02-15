"""Shipment route tests."""

from fastapi_sendparcel.routes.shipments import router


def test_shipments_health_route_exists() -> None:
    paths = {route.path for route in router.routes}

    assert "/shipments/health" in paths
