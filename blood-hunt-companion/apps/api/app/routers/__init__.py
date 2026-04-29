"""FastAPI route modules. Each module owns a `router` that `main.py` includes."""

from . import gear, simulation

__all__ = ["gear", "simulation"]
