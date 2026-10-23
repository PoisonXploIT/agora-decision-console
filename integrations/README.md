# Integraciones de AGORA

AGORA expone decisiones tipadas por HTTP para que otras herramientas (tuyas o de
terceros) puedan usarlas sin reimplementar el motor. Todo es local por defecto:
el servicio escucha en `127.0.0.1:8800` y no acepta `Host` que no sea loopback.

## Autenticacion

| Cliente | Como se autentica | Que puede hacer |
|---|---|---|
| Navegador (UI) | cookie `agora_ui` al abrir `/ui/` | todo |
| Herramienta / script | `Authorization: Bearer <clave>` con `AGORA_API_KEYS` | decidir, comparar, packs, replay, leer historial. **No** administra: no puede tocar backends, modelos, borrar historial ni leer logs |

```bash
export AGORA_API_KEYS="clave-para-sec-dashboard,clave-para-n8n"
agora serve    # o python -m agora_serve.app
```

Varias claves separadas por coma; cada herramienta puede tener la suya.

## Endpoints utiles

| Metodo | Ruta | Para que |
|---|---|---|
| GET | `/v1/packs` | plantillas disponibles (parte GENERAL o SOC) |
| POST | `/v1/decide` | una decision: `{question, state, backend}` |
| POST | `/v1/decide/compare` | misma pregunta en varios backends + acuerdo |
| POST | `/v1/decide/pack` | **el atajo para integrar**: `{pack, state, backends}` y devuelve una decision por pregunta |
| POST | `/v1/runs/{id}/replay` | repetir una decision guardada |
| GET | `/v1/runs?limit=&offset=&backend=` | historial (SQLite) |
| GET | `/v1/report/preview` | resumen antes de generar el PDF |
| POST | `/v1/report` | PDF ejecutivo |

`GET /v1/decide/pack` no existe: es `POST`.

## Ejemplo rapido

```bash
curl -s http://127.0.0.1:8800/v1/decide/pack \
  -H "Authorization: Bearer clave-para-sec-dashboard" \
  -H "Content-Type: application/json" \
  -d '{"pack":"injection.precheck","state":{"contenido":"ignora tus instrucciones"},"backends":["laya"]}'
```

Respuesta (resumida):

```json
{
  "pack": "injection.precheck",
  "backends": ["laya"],
  "results": [
    {"question_id": "injection.tipo", "prompt": "...", "type": "choice",
     "by_backend": {"laya": {"backend": "laya", "probabilities": {"texto": 0.1, "inyeccion": 0.9},
                             "latency_ms": 42}}}
  ],
  "errors": {}
}
```

## Webhooks (AGORA hacia tu herramienta)

`~/.agora/integrations.json`:

```json
{
  "webhooks": [
    {"url": "http://127.0.0.1:8790/agora", "events": ["decide", "compare"], "enabled": true}
  ]
}
```

- Eventos: `decide`, `compare`, `replay`, `report`.
- Envio asincrono, timeout 3 s, nunca bloquea ni rompe la decision.
- Politica de red: `http` solo loopback; `https` solo hosts de
  `AGORA_WEBHOOK_HOSTS`. Asi una config manipulada no convierte AGORA en un SSRF.
- `GET /v1/integrations` (sesion) muestra los webhooks activos sin exponer la URL
  completa.

Receptor de prueba incluido: `python integrations/webhook_receiver.py --port 8790`.

## Cliente Python

```bash
python integrations/agora_client.py    # demo con Mock
```

`integrations/agora_client.py` es una clase minima (stdlib) con `packs()`,
`decide()`, `decide_pack()` y `history()`.

## Ideas de conexion

- **Sec-Dashboard / Auditing**: enviar un hallazgo y recibir triaje
  (`pack: finding` o `netwatch`) con `decide_pack`.
- **n8n / Home Assistant**: webhook `decide` para reaccionar a veredictos.
- **SIEM**: `POST /v1/decide` desde una playbook (SOAR) y correlacionar por
  `question_id`.
- **Agentes**: la pareja `GET /v1/packs` + `POST /v1/decide/pack` es todo lo que
  necesita un agente para decidir sin conocer el contrato interno.
