"""Import-level contract tests for Web Push routes."""

from fastapi import status


def test_push_subscribe_routes_are_bodyless_204_responses():
    """FastAPI must allow the app to register both no-content endpoints."""

    from backend.main import app

    routes = {
        (route.path, method): route
        for route in app.routes
        for method in getattr(route, "methods", ())
    }
    for method in ("POST", "DELETE"):
        route = routes[("/api/v1/push/subscribe", method)]
        assert route.status_code == status.HTTP_204_NO_CONTENT
        assert route.response_model is None
