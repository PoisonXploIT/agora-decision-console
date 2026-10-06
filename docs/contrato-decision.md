# Contrato de decisión de AGORA

El contrato es lo que hace intercambiables los backends: cualquier backend que
cumpla estos puntos produce decisiones idénticas en forma, aunque difieran en
modelo o en red.

## Tipos de pregunta

Tres tipos, todos atómicos (una pregunta = un juicio):

| Tipo   | `criteria`                              | Salida extra               |
| ------ | --------------------------------------- | -------------------------- |
| choice | las opciones, en orden escrito          | -                          |
| score  | etiquetas de nivel en orden ascendente  | `expected` en [1, N]       |
| noul   | acciones candidatas                     | `action` (argmax) + `text` |

`score` necesita al menos dos niveles. Los criterios no se repiten.

## Criterios posicionales (la regla central)

- El orden canónico de los criterios es el orden en que aparecen en la
  pregunta. Nunca se ordenan por clave, nunca se deduplican en silencio:
  un duplicado es error de contrato (`ContractError`).
- La serialización canónica es `json.dumps(..., ensure_ascii=False)` **sin**
  `sort_keys`. El orden de inserción del dict (que para las probabilidades es
  el orden canónico) se conserva tal cual en ficheros y respuestas HTTP.
- Un test (`tests/test_contract_order.py`) lo prueba: reordenar las claves
  de una decisión debe romper la validación.

## Estado

`DecisionRequest.state` es contenido no confiable: viaja como dato, nunca se
interpreta como instrucción (ni para el backend ni para el LLM que lo lea).

## Normalización por tipo

- `probabilities`: dict `{criterio: p}` con las claves **exactamente** en
  orden canónico; cada `p` en [0, 1] y suma 1 (tolerancia 1e-6).
- `score`: además `expected` = valor esperado sobre la escala 1..N.
- `noul`: además `action` (criterio de máxima probabilidad; empate: el
  primero en orden canónico) y `text` (justificación breve).

## Trazabilidad

Toda decisión lleva un `Trace`:

- `backend`, `model`, `privacy` (`local` | `cloud`), `latency_ms`;
- `criteria_order`: el orden canónico, tal cual;
- `raw`: la salida cruda del backend (truncada a 4000 caracteres).

## Validación

`validate_decision(decision, question)` (y `validate_question`) lanzan
`ContractError` si: las claves de probabilidades no son los criterios en
orden canónico; alguna probabilidad está fuera de [0, 1]; la suma no es 1;
el tipo de decisión no es el de la pregunta; `score` sin `expected` en
[1, N]; o `noul` con `action` fuera de los criterios.

## Backends

Un backend implementa dos cosas: `capabilities()` (tipos soportados) y
`decide(request) -> Decision`. La salida siempre pasa por la normalización y
la validación anteriores; si el backend devuelve algo que no cumple el
contrato, se lanza `AdapterError`, no una decisión a medias.

| Backend | Privacidad | Transporte                                                        |
| ------- | ---------- | ----------------------------------------------------------------- |
| Mock    | local      | sin red (determinista)                                            |
| LAYA    | local      | HTTP POST `/v1/systemone` a `127.0.0.1:8787`                      |
| Eikos   | local      | HTTP POST `/v1/systemone` a `127.0.0.1:8901`; imágenes base64 opcionales |
| JEV     | cloud      | API compatible TypeSafe (`POST /v1/systemone`) con clave; `base_url` y `model` configurables |

Los tres backends HTTP hablan el mismo protocolo, así que comparten un único
adaptador (`agora_adapters/laya.py`); `EikosAdapter` es una variante con el
puerto por defecto de Eikos y el `kind` correspondiente. El repo incluye además
`JevAdapter`, una variante para servidores **OpenAI chat completions** con
`dry_run` (sin red), útil para probar sin nube.
