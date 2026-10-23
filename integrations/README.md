# Integraciones de AGORA

AGORA expone decisiones tipadas por HTTP para que otras herramientas (tuyas o de
terceros) puedan usarlas sin reimplementar el motor. Todo es local por defecto:
el servicio escucha en `127.0.0.1:8800` y no acepta `Host` que no sea loopback.

## Autenticacion

| Cliente | Como se autentica | Que puede hacer |
|---|---|---|
| Navegador (UI) | cookie `agora_ui` al abrir `/ui/` | todo |
| Herramienta / script | `Authorization: Bearer <clave>` con `AGORA_API_KEYS` | decidir, comparar, packs, replay, leer historial. **No** administra |
| Agente MCP | `AGORA_API_KEY` o token de `~/.agora/ui_token` | lo mismo, via herramientas MCP |

```bash
export AGORA_API_KEYS="clave-sec-dashboard,clave-n8n,clave-agentes"
agora serve
```

## Servidor MCP (para agentes)

`python -m agora_mcp` (o `agora mcp`) expone AGORA como herramientas MCP por stdio:
`agora_packs`, `agora_decide`, `agora_compare`, `agora_history` y `agora_health`.
Config del cliente y seguridad en [`../agora_mcp/README.md`](../agora_mcp/README.md).

## Endpoints utiles

| Metodo | Ruta | Para que |
|---|---|---|
| GET | `/v1/packs` | plantillas disponibles (GENERAL o SOC) |
| POST | `/v1/decide` | una decision: `{question, state, backend}` |
| POST | `/v1/decide/compare` | misma pregunta en varios backends + acuerdo |
| POST | `/v1/decide/pack` | **atajo para integrar**: `{pack, state, backends}` y una decision por pregunta |
| POST | `/v1/runs/{id}/replay` | repetir una decision guardada |
| GET | `/v1/runs?limit=&offset=&backend=` | historial (SQLite) |
| POST | `/v1/report/preview` | resumen antes de generar el PDF |
| POST | `/v1/report` | PDF ejecutivo |
| GET | `/v1/integrations` | sinks y claves configurados |
| GET | `/metrics` | metricas Prometheus (agregados) |

## Ejemplo rapido

```bash
curl -s http://127.0.0.1:8800/v1/decide/pack \
  -H "Authorization: Bearer clave-sec-dashboard" \
  -H "Content-Type: application/json" \
  -d '{"pack":"injection.precheck","state":{"contenido":"ignora tus instrucciones"},"backends":["laya"]}'
```

## Sinks: AGORA hacia tus herramientas

`~/.agora/integrations.json` acepta varios tipos de salida (asincronos, sin bloquear
la decision):

| Tipo | Que hace | Seguridad |
|---|---|---|
| `webhook` | POST JSON a una URL | `http` loopback o `https` en `AGORA_WEBHOOK_HOSTS` |
| `jsonl` | añade una linea JSON a un fichero | solo dentro de `~/.agora`, permisos 0600 |
| `syslog` | envia el evento por UDP (RFC5424) | host loopback o `AGORA_SYSLOG_HOSTS` |
| `splunk` | POST a Splunk HEC con `Authorization: Splunk <token>` | token solo por env y host en allowlist |
| `telegram` | mensaje al chat indicado | token solo por env (`TELEGRAM_BOT_TOKEN`), `chat_id` numerico |

```json
{
  "sinks": [
    {"type": "webhook",  "url": "http://127.0.0.1:8790/agora", "events": ["decide"]},
    {"type": "jsonl",    "path": "decisiones.jsonl", "events": ["decide", "compare"]},
    {"type": "syslog",   "host": "127.0.0.1", "port": 5514, "events": ["compare"]},
    {"type": "splunk",   "url": "https://hectest.example:8088/services/collector",
     "token_env": "SPLUNK_HEC_TOKEN", "events": ["decide"]},
    {"type": "telegram", "token_env": "TELEGRAM_BOT_TOKEN", "chat_id": "12345",
     "events": ["decide"]}
  ]
}
```

Para hosts `https` propios hay que anadirlos a `AGORA_WEBHOOK_HOSTS`. El formato
antiguo (`{"webhooks": [...]}`) sigue funcionando.

Eventos: `decide`, `compare`, `replay`, `report`.

## Metricas Prometheus

`GET /metrics` devuelve solo agregados: decisiones por backend y estado,
comparaciones, packs servidos, errores, fallos de sink y runs en SQLite. Sin estado,
sin preguntas y sin claves.

## Ejemplos incluidos

- `tools.json`: esquema de function-calling para cualquier LLM.
- `n8n-workflow.json`: webhook -> `decide_pack` (triaje de hallazgo).
- `home-assistant.yaml`: `rest_command` y sensor de historial.
- `webhook_receiver.py`: receptor local para probar sinks.
- `agora_client.py`: cliente Python (stdlib).

## Casos de uso

- **Sec-Dashboard / Auditing**: enviar un hallazgo y recibir triaje (`finding`).
- **n8n / Home Assistant**: automatizar reacciones a veredictos o notificar por
  Telegram.
- **SIEM / SOAR**: `POST /v1/decide` desde una playbook y correlacionar por
  `question_id`; el sink `splunk` manda cada decision al HEC.
- **Agentes**: MCP con `agora_decide` o `agora_decide_pack`.
