"""EikosAdapter: backend local Eikos por HTTP (serve.py).

El ``serve.py`` de Eikos habla la **API compatible TypeSafe** (``POST
/v1/systemone``), la misma que LAYA y JEV, asi que este adaptador es el
adaptador HTTP comun con el nombre, el puerto por defecto y el ``kind`` de
Eikos. Ademas acepta ``images`` (base64 o data URI) que Eikos puede leer con
su torre de vision; los demas backends ignoran ese campo.

Guia de arranque del Eikos local en ``docs/eikos-local.md`` (Eikos-4B cabe en
16 GB; Eikos-27B INT4 son 19,4 GB y no caben).
"""
from __future__ import annotations

from .laya import LayaAdapter


class EikosAdapter(LayaAdapter):
    """Adaptador HTTP a ``serve.py`` de Eikos (local, API compatible TypeSafe)."""

    kind = "eikos"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8901",
        timeout: float = 120.0,
        api_key: str | None = None,
        model: str | None = None,
    ):
        super().__init__(base_url=base_url, timeout=timeout, api_key=api_key, model=model)
        self.name = "eikos"


__all__ = ["EikosAdapter"]
