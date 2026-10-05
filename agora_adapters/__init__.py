"""agora_adapters - backends de decision de AGORA.

- ``base`` : base comun (capabilities, decide, normalizacion por tipo).
- ``mock`` : MockAdapter determinista sin red.
- ``laya`` : LayaAdapter por HTTP a laya-serve (127.0.0.1:8787).
- ``eikos`` : EikosAdapter por HTTP a serve.py de Eikos (127.0.0.1:8901).
"""
from .base import AdapterError, BackendAdapter
from .mock import MockAdapter
from .laya import LayaAdapter
from .eikos import EikosAdapter

__all__ = [
    "AdapterError",
    "BackendAdapter",
    "EikosAdapter",
    "LayaAdapter",
    "MockAdapter",
]
