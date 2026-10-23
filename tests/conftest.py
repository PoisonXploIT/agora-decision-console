"""Configuracion comun de tests.

- Desactiva el token de sesion (la bateria no lo necesita) y usa un directorio de
  configuracion temporal para no tocar `~/.agora` del usuario.
- `testserver` es el Host que usa TestClient.
"""
from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="agora-tests-")
os.environ.setdefault("AGORA_CONFIG_DIR", _TMP)
os.environ.setdefault("AGORA_AUTH", "off")
os.environ.setdefault("AGORA_ALLOWED_HOSTS", "testserver,localhost,127.0.0.1,::1")
os.environ.setdefault("AGORA_UI_TOKEN", "token-de-test")
