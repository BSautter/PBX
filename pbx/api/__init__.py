"""REST API for PBX management.

Uses Flask with Blueprints for route organization.
"""

__all__ = ["PBXFlaskServer", "create_app"]


def __getattr__(name: str) -> object:
    """Lazy import of API modules to avoid circular imports."""
    if name == "create_app":
        from pbx.api.app import create_app  # noqa: PLC0415

        return create_app
    if name == "PBXFlaskServer":
        from pbx.api.server import PBXFlaskServer  # noqa: PLC0415

        return PBXFlaskServer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
