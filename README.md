# AGORA

Consola de decisiones tipadas: un estado mas preguntas `choice` / `score` /
`noul` que devuelven probabilidades calibradas, servidas por varios backends
(Mock determinista, LAYA local, JEV cloud opcional, Eikos local). Una sola
UI con dos partes: GENERAL y SOC/SIEM.

Sin nube obligatoria, sin claves: todo corre contra servidores locales; el
backend cloud (JEV) es optativo y solo se usa contra un servidor que tu
elijas.

## Contrato en una linea

Una pregunta es un juicio atomico. Sus `criteria` son POSICIONALES: el orden
en que se escriben es el orden canonico de la respuesta; nunca se ordenan por
clave ni se serializa con `sort_keys`. El estado viaja como contenido no
confiable (dato, no instruccion). Detalle en `docs/contrato-decision.md`.

## Estructura

| Carpeta            | Que es                                                        |
| ------------------ | ------------------------------------------------------------- |
| `agora_core`       | Esquemas tipados (choice/score/noul) y contrato de decision   |
| `agora_adapters`   | Backends: Mock, LAYA (HTTP), JEV (OpenAI-compatible), Eikos  |
| `agora_serve`      | Servicio FastAPI (`/health`, `/backends`, `/v1/decide`, ...) |
| `agora`            | CLI (`agora backends / decide / compare / packs / serve`)     |
| `agora_ui`         | UI single-page sin build, montada en `/ui`                    |
| `packs`            | Plantillas de preguntas (GENERAL y SOC)                       |
| `tools`            | Gate de validacion + importadores ATT&CK y NVD                |
| `data/soc`         | Items importados (ATT&CK, NVD), JSONL en orden de origen      |
| `tests`            | Tests por fase (fixture STIX/NVD, servidores falsos locales)  |

## Comienzo rapido

```bat
.venv\Scripts\python.exe -m pytest -q          ; tests de todas las fases
.venv\Scripts\python.exe verificar.py --test   ; estado por fase
agora serve                                    ; servicio + UI en http://127.0.0.1:8800/ui
agora backends                               ; backends registrados
agora decide --question "Clasifica el hallazgo" --criteria true_positive false_positive noise --state "{\"ref\": \"soc\"}"
```

## Importadores SOC (gate)

`tools/gate.py` valida items con `id`, `name`, `tactic` (ground truth del
origen, no inferida) y `parent`: ids unicos, padre de subtecnica presente y
cobertura de tacticas. `tools/import_attack.py` lee un bundle STIX de
ATT&CK y `tools/import_nvd.py` un feed NVD 2.0; ambos reutilizan el gate y
escriben JSONL conservando el orden de origen.

## Backends locales

- LAYA: `http://127.0.0.1:8787` (laya-serve).
- Eikos: `http://127.0.0.1:8901` (serve.py; guia en `docs/eikos-local.md`).
- Mock: determinista, sin red, para tests y desarrollo.

## Progreso

La hoja de ruta por fases esta en `FASES.md`; el comprobador es
`verificar.py` (`--test` ejecuta los tests de cada fase completa).

## Licencia

Apache 2.0 (ver `LICENSE`).
