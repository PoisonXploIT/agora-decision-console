# AGORA como servidor MCP

Servidor **MCP** (Model Context Protocol) por stdio para que cualquier agente
(Claude Desktop, Cursor, PydanticAI, LangGraph, n8n AI, etc.) use AGORA como
herramienta de decisión tipada.

```bash
python -m agora_mcp        # o: agora mcp
```

## Herramientas expuestas

| Nombre | Que hace |
|---|---|
| `agora_packs` | lista packs (GENERAL y SOC-SIEM) con descripción y nº de preguntas |
| `agora_decide` | evalúa un pack completo contra un estado y devuelve veredicto + probabilidades por pregunta |
| `agora_compare` | misma pregunta en varios backends, con acuerdo |
| `agora_history` | últimas decisiones guardadas (SQLite) |
| `agora_health` | backends registrados y nº de decisiones |

Todas devuelven texto JSON compacto en `content[0].text`, listo para que el agente
lo parsee.

## Configuración en un cliente MCP

```json
{
  "mcpServers": {
    "agora": {
      "command": "C:/Users/Sammi/AI/agora/.venv/Scripts/python.exe",
      "args": ["-m", "agora_mcp"],
      "env": {
        "AGORA_URL": "http://127.0.0.1:8800",
        "AGORA_API_KEY": "clave-para-agentes"
      }
    }
  }
}
```

- `AGORA_API_KEY` es una clave de servicio (`AGORA_API_KEYS` en el servicio). Solo
  permite decidir, comparar, packs y leer historial; nunca administrar.
- Si el agente corre en el mismo equipo y no hay clave, el servidor usa el token de
  `~/.agora/ui_token` (cabecera `X-AGORA-Token`).
- El servicio debe estar levantado (`agora serve`).

## Probar a mano

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python -m agora_mcp
```

Respuesta esperada: `protocolVersion` y `serverInfo.name = "agora"`.

## Seguridad

- Transporte stdio: no abre puertos.
- Todo el tráfico va a `127.0.0.1:8800`; el servicio rechaza `Host` no loopback.
- Los argumentos de las herramientas solo llevan pack/estado/pregunta: no hay URLs,
  asi que no se puede convertir en un proxy SSRF.
- Sin `AGORA_API_KEY` no funciona fuera del equipo donde vive el token de sesión.
