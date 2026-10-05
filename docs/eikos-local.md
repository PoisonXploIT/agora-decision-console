# Eikos local (guia de arranque)

AGORA consume Eikos a traves de `EikosAdapter` (`agora_adapters/eikos.py`),
que habla HTTP con un servidor local `serve.py` en `http://127.0.0.1:8901`.
Sin nube, sin claves: todo queda en la maquina.

## Que cabe en 16 GB

- **Eikos-4B**: cabe con holgura en 16 GB de VRAM (cuantizado INT4/INT8)
  y es el modelo recomendado para esta consola.
- **Eikos-27B INT4**: son 19,4 GB y **no caben** en 16 GB. No intentarlo:
  ni cuantizacion extra ni offload a CPU compensan la latencia para una
  consola de decisiones.

## Arranque

1. Poner el modelo descargado en `C:\Users\Sammi\AI\eikos\models\eikos-4b`.
2. Servirlo con el servidor local (el mismo que usa LAYA, apuntando al
   directorio del modelo):

   ```bat
   C:\Users\Sammi\AI\eikos\.venv\Scripts\python.exe serve.py ^
     --model C:\Users\Sammi\AI\eikos\models\eikos-4b ^
     --host 127.0.0.1 --port 8901
   ```

3. Comprobar salud: `GET http://127.0.0.1:8901/health` debe devolver
   `{"ok": true, ...}`.

## Protocolo (POST /v1/decide)

Petición:

```json
{
  "question": {"id": "...", "type": "choice", "prompt": "...", "criteria": ["a", "b"]},
  "state": { },
  "images": ["<base64>", "<base64>"]
}
```

- `images` es **opcional**: base64 de imagenes que el modelo puede ver
  (por ejemplo, capturas del SIEM en la parte SOC). Sin imagenes, el campo
  no se envia.

Respuesta:

```json
{
  "probabilities": [0.7, 0.3],
  "expected": null,
  "action": null,
  "text": null,
  "model": "eikos-4b"
}
```

- `probabilities` puede ser lista alineada por posicion con `criteria` o
  dict `{criterio: p}`; el adaptador normaliza al orden canonico y valida
  contra el contrato de decision.
- Para preguntas `score`, el servidor puede enviar `expected` (valor
  esperado 1..N); para `noul`, `action` y `text`. Si no los envia, el
  adaptador los calcula (argmax y texto local).

## Uso desde AGORA

```python
from agora_adapters import EikosAdapter
ad = EikosAdapter(base_url="http://127.0.0.1:8901")
decision = ad.decide(request, images=[b64])   # images opcional
```

O por CLI/servicio una vez registrado el backend en el registry de
`agora_serve`. El `Trace` de la decision lleva `backend="eikos"`,
`privacy="local"` y el modelo reportado por el servidor.

## Verificacion sin Eikos real

Los tests usan un servidor falso con el mismo protocolo
(`tests/fakes/fake_eikos_server.py`), por lo que `pytest
tests/test_adapters_eikos.py` pasa sin modelo ni GPU.
