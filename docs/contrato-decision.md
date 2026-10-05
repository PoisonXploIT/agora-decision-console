# Contrato de decision de AGORA

El contrato es lo que hace intercambiables los backends: cualquier backend que
cumpla estos puntos produce decisiones identicas en forma, aunque difieran en
modelo o en red.

## Tipos de pregunta

Tres tipos, todos atomicos (una pregunta = un juicio):

| Tipo   | `criteria`                              | Salida extra            |
| ------ | ------------------------------------- | ----------------------- |
| choice | las opciones, en orden escrito         | -                       |
| score  | etiquetas de nivel en orden ascendente | `expected` en [1, N]    |
| noul   | acciones candidatas                   | `action` (argmax) + `text` |

`score` necesita al menos dos niveles. Los criterios no se repiten.

## Criterios posicionales (la regla central)

- El orden canonico de los criterios es el orden en que aparecen en la
  pregunta. Nunca se ordenan por clave, nunca se deduplican en silencio:
  un duplicado es error de contrato (`ContractError`).
- La serializacion canonica es `json.dumps(..., ensure_ascii=False)` **sin**
  `sort_keys`. El orden de insercion del dict (que para las probabilidades es
  el orden canonico) se conserva tal cual en ficheros y respuestas HTTP.
- Un test (`tests/test_contract_order.py`) lo prueba: reordenar las claves
  de una decision debe romper la validacion.

## Estado

`DecisionRequest.state` es contenido no confiable: viaja como dato, nunca se
interpreta como instruccion (ni para el backend ni para el LLM que lo lea).

## Normalizacion por tipo

- `probabilities`: dict `{criterio: p}` con las claves **exactamente** en
  orden canonico; cada `p` en [0, 1] y suma 1 (tolerancia 1e-6).
- `score`: ademas `expected` = valor esperado sobre la escala 1..N.
- `noul`: ademas `action` (criterio de maxima probabilidad; empate: el
  primero en orden canonico) y `text` (justificacion breve).

## Trazabilidad

Toda decision lleva un `Trace`:

- `backend`, `model`, `privacy` (`local` | `cloud`), `latency_ms`;
- `criteria_order`: el orden canonico, tal cual;
- `raw`: la salida cruda del backend (truncada a 4000 caracteres).

## Validacion

`validate_decision(decision, question)` (y `validate_question`) lanzan
`ContractError` si: las claves de probabilidades no son los criterios en
orden canonico; alguna probabilidad esta fuera de [0, 1]; la suma no es 1;
el tipo de decision no es el de la pregunta; `score` sin `expected` en
[1, N]; o `noul` con `action` fuera de los criterios.

## Backends

Un backend implementa dos cosas: `capabilities()` (tipos soportados) y
`decide(request) -> Decision`. La salida siempre pasa por la normalizacion y
la validacion anteriores; si el backend devuelve algo que no cumple el
contrato, se lanza `AdapterError`, no una decision a medias.

| Backend | Privacidad | Transporte          |
| ------- | ---------- | ------------------- |
| Mock    | local      | sin red (determinista) |
| LAYA    | local      | HTTP POST /v1/decide a 127.0.0.1:8787 |
| JEV     | cloud      | protocolo OpenAI chat completions, `base_url` configurable; `dry_run` sin red |
| Eikos   | local      | HTTP POST /v1/decide a 127.0.0.1:8901, imagenes base64 opcionales |
