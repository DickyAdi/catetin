"""ASGI entrypoint. Run with: uvicorn catetin.main:app

Composition-only: this module builds the app via `composition.build_app()`
and nothing else. No adapters are constructed here.
"""

from .composition import build_app

app = build_app()
