"""agora_adapters - backends de decision de AGORA.

- ``base`` : base comun (capabilities, decide, normalizacion por tipo).
- ``mock`` : MockAdapter determinista sin red.
- ``laya`` : LayaAdapter por HTTP a laya-serve (127.0.0.1:8787).
- ``eikos`` : EikosAdapter por HTTP a serve.py de Eikos (127.0.0.1:8901).
"""
from .base import AdapterError, BackendAdapter
from .eikos import EikosAdapter
from .laya import LayaAdapter
from .mock import MockAdapter

__all__ = [
    "AdapterError",
    "BackendAdapter",
    "EikosAdapter",
    "LayaAdapter",
    "MockAdapter",
]
