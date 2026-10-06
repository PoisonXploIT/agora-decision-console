# AGORA

![CI](https://github.com/PoisonXploIT/agora-decision-console/actions/workflows/ci.yml/badge.svg)

Consola de **decisiones tipadas**: un estado y preguntas `choice` / `score` /
`noul` que devuelven probabilidades calibradas, servidas por varios backends
(Mock determinista, LAYA local, Eikos local, JEV cloud opcional). Una sola
consola con dos partes: **GENERAL** y **SOC/SIEM**.

Sin nube obligatoria y sin claves para lo local: todo corre contra servidores
en tu máquina. El backend cloud es opcional y solo se usa si lo configuras.

## El contrato en una línea

Una pregunta es un juicio atómico. Sus `criteria` son **POSICIONALES**: el orden
en que se escriben es el orden canónico de la respuesta; nunca se ordenan por
clave ni se serializa con `sort_keys`. El estado viaja como **contenido no
confiable** (dato, no instrucción). Detalle en `docs/contrato-decision.md`.

## Estructura

| Carpeta          | Qué es                                                               |
| ---------------- | -------------------------------------------------------------------- |
| `agora_core`     | Esquemas tipados (choice/score/noul) y contrato de decisión          |
| `agora_adapters` | Backends HTTP: Mock, LAYA, Eikos y JEV (API compatible TypeSafe)     |
| `agora_serve`    | Servicio FastAPI (`/health`, `/backends`, `/v1/decide`, ...)         |
| `agora`          | CLI (`agora backends / decide / compare / packs / serve`)            |
| `agora_ui`       | Consola single-page sin build, servida en `/ui`                      |
| `packs`          | Plantillas de preguntas (GENERAL y SOC)                              |
| `tools`          | Gate de validación + importadores ATT&CK / NVD + E2E + demo          |
| `tests`          | Tests por fase (fakes locales de JEV y Eikos, fixture STIX/NVD)      |
| `docs`           | Contrato de decisión y guía de Eikos local                           |

## Instalación

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[test]"   # Windows
# .venv/bin/python -m pip install -e ".[test]"         # Linux/macOS
```

## Inicio rápido

```bash
.venv/Scripts/python.exe -m pytest -q        # tests
.venv/Scripts/python.exe verificar.py --test # estado por fase
agora serve                                  # servicio + consola en http://127.0.0.1:8800/ui
agora backends                               # backends registrados
agora decide --question "Clasifica el hallazgo" \
  --criteria true_positive false_positive noise --state "{\"ref\": \"soc\"}"
```

## La consola

En `http://127.0.0.1:8800/ui`:

- **Parte** GENERAL o SOC-SIEM, con sus packs (plantillas de preguntas).
- **Estado** en JSON, tratado como dato no confiable.
- **Decidir** por tipo de pregunta, con la distribución y la traza (backend,
  modelo, latencia y orden canónico).
- **Comparar backends** para ver el mismo caso en varios modelos a la vez.
- **Pregunta desde texto**: un LLM de chat local (`:8099`) traduce la
  instrucción a la pregunta tipada. Los modelos de decisión no hacen eso: solo
  clasifican sobre opciones ya dadas.
- **Modelos de decisión**: catálogo (LAYAA, Eikos-4B, JEV, Mock), alta de
  nuevos, y botones **Levantar** / **Detener** que arrancan los servidores
  locales en su propia ventana con logs.

## Informe PDF

El botón **Informe PDF** (o `POST /v1/report`) genera un informe ejecutivo con
resumen, veredicto en lenguaje llano con banda de confianza, gráficos de barras
y tabla comparativa por modelo. Solo depende de `reportlab`.

## Backends locales

- **LAYAA v2**: `http://127.0.0.1:8787` (CPU).
- **Eikos-4B**: `http://127.0.0.1:8901` (CPU o GPU); guía en `docs/eikos-local.md`.
- **Mock**: determinista, sin red, para tests y desarrollo.
- **JEV / TypeSafe**: cloud opcional, necesita clave.

Los tres primeros hablan la misma API compatible TypeSafe (`POST /v1/systemone`),
así que un solo adaptador los cubre.

## Configuración local

Fuera del repositorio, en tu perfil:

| Fichero                              | Qué guarda                                          |
| ------------------------------------ | --------------------------------------------------- |
| `%USERPROFILE%\.agora\backends.json` | modelos configurados (con su URL; la clave cloud también vive aquí) |
| `%USERPROFILE%\.agora\models.json`   | lanzadores locales (comando para Levantar/Detener)  |
| `%USERPROFILE%\.agora\supervisor.log`| relanzados automáticos de modelos locales           |

El directorio se puede cambiar con `AGORA_CONFIG_DIR`.

## Seguridad

- El servicio escucha solo en `127.0.0.1`.
- Sin nube por defecto: solo sale a la red si registras un backend cloud.
- Las claves (JEV) se guardan en el perfil del usuario, nunca en el repositorio.
- El estado se trata como dato; los packs llevan un pre-check de inyección.

## Importadores SOC (gate)

`tools/gate.py` valida items con `id`, `name`, `tactic` (ground truth del
origen, no inferida) y `parent`: ids únicos, padre de subtécnica presente y
cobertura de tácticas. `tools/import_attack.py` lee un bundle STIX de ATT&CK y
`tools/import_nvd.py` un feed NVD 2.0; ambos reutilizan el gate y escriben JSONL
conservando el orden de origen.

## Pruebas

- Unitarias: `pytest` (contrato, adaptadores, servicio, packs, UI, gate).
- End-to-end contra el servicio en marcha: `tools/e2e.py`.
- Demo con datos de SOC + informe: `tools/demo_e2e.py`.

## Créditos

AGORA orquesta modelos de decisión de terceros (se consumen por HTTP; no se
redistribuye su código ni sus pesos):

- **Eikos** (`caiovicentino1/Eikos-4B`), licencia MIT.
- **Laya** (multilingual System 1 decision engine), licencia Apache 2.0.
- **JEV / TypeSafe**, servicio cloud opcional.

## Licencia

Apache 2.0 (ver `LICENSE`).

## Contacto

- Web: [sammideblas.com](https://sammideblas.com)
- Correo: analista@sammideblas.com
- Autor: Sammi De Blas
