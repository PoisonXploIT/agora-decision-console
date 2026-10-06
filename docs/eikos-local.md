# Eikos local (guia de arranque)

Eikos es un modelo de **decision tipada** (choice / score / noul) que responde
en una sola pasada, con una probabilidad por opcion. Su `serve.py` habla la
**API compatible TypeSafe** (`POST /v1/systemone`), la misma que LAYA y JEV, asi
que AGORA lo usa con el mismo adaptador HTTP (`agora_adapters/laya.py`).

Sin nube y sin claves: el servidor escucha en `127.0.0.1`.

## Que cabe en 16 GB

- **Eikos-4B** (~9 GB en bf16): cabe en 16 GB de VRAM. Es el recomendado.
- **Eikos-27B INT4**: 19,4 GB; **no cabe** en 16 GB. Hace falta una GPU mayor,
  vLLM con offload parcial (lento) o paciencia.

## Descarga de los pesos

Los pesos estan en Hugging Face (`caiovicentino1/Eikos-4B`). Con el cliente de
HF:

```bash
python -m pip install huggingface_hub
huggingface-cli download caiovicentino1/Eikos-4B --local-dir <carpeta>/Eikos-4B
```

Incluye `serve.py`, `decision_core.py`, `letter_adapter.py` y `calib.json`
junto a los `safetensors`: no hay que clonar nada mas.

## Arranque

```bash
cd <carpeta>/Eikos-4B
python serve.py --model <carpeta>/Eikos-4B --device cpu  --port 8901
python serve.py --model <carpeta>/Eikos-4B --device cuda --port 8901
```

- `--device cpu`: sin GPU, apto para convivir con otro modelo en la tarjeta.
- `--device cuda`: mucho mas rapido, pero ocupa la GPU.
- Para produccion existe `serve_vllm.sh` (exige vLLM >= 0.30) y `serve.py
  --vllm-url`.

Salud: `GET http://127.0.0.1:8901/health`.

## API (POST /v1/systemone)

Peticion:

```json
{
  "state": { },
  "questions": {
    "q1": {
      "type": "choice",
      "instructions": "clasifica el evento",
      "criteria": { "a": "opcion a", "b": "opcion b" }
    }
  }
}
```

- `criteria` de `choice` es un mapa `opcion -> descripcion` (se conserva el orden).
- `score` usa una lista de niveles en orden; `noul` (si/no) usa las claves
  `true` / `false`.

Respuesta:

```json
{
  "model": "...Eikos-4B",
  "answers": {
    "q1": {
      "type": "choice",
      "choice": "a",
      "probabilities": { "a": 0.75, "b": 0.25 },
      "confidence": 0.75
    }
  },
  "usage": { "input_tokens": 128, "output_tokens": 0 },
  "latency_s": 1.36
}
```

- `score` devuelve ademas `score` y `legend` (claves `"0".."N-1"`).
- `noul` devuelve `noul` (probabilidad de `true`).
- El adaptador normaliza todo al **orden canonico** de los criterios y valida
  contra el contrato de decision.

## Uso desde AGORA

Registrar el backend (una vez; queda persistido en `%USERPROFILE%\.agora\backends.json`):

```bash
curl -X POST http://127.0.0.1:8800/backends -H "Content-Type: application/json" \
  -d '{"name":"eikos-4b","kind":"http","base_url":"http://127.0.0.1:8901"}'
```

O desde la UI, panel "Modelos de decision": preset **Eikos-4B**, boton
**Levantar** (abre su consola con los logs) y **Guardar modelo**.

## Verificacion sin Eikos real

Los tests usan un servidor falso con el mismo protocolo
(`tests/fakes/fake_eikos_server.py`), asi que `pytest
tests/test_adapters_eikos.py` pasa sin modelo ni GPU.
