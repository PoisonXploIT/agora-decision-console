# AGORA - hoja de ruta

Venv: `.venv` (pydantic, fastapi, uvicorn, reportlab, pytest, httpx).

Comprobador: `.venv\Scripts\python.exe verificar.py` (con `--test` ejecuta los tests; con `--all`
falla si queda alguna fase). La marca de fin de cada fase es que `verificar.py` la dé en PASS.

AGORA es una consola de decisiones tipadas: un estado y preguntas `choice` / `score` / `noul`
que devuelven probabilidades calibradas, servidas por varios backends (Mock, LAYA local, JEV cloud
opcional, Eikos local). Una sola UI con dos partes: GENERAL y SOC/SIEM.

Libertad de implementación: la estructura interna, los nombres de funciones y el orden fino son
libres, siempre que `verificar.py` y los tests pasen. Si una fase crece, partirla y anotarlo.

## Reglas

- Sin nube y sin claves: los tests van contra servidores falsos locales; LAYA en `127.0.0.1:8787`.
- Los `criteria` son posicionales: nunca ordenar claves, nunca `sort_keys=True`. Un test lo prueba.
- Una pregunta es un juicio atómico; el estado es contenido no confiable.
- Verificar contra disco (tests y `verificar.py`), no dar nada por hecho.

## Fases

- **F0 Fundación.** `agora_core` con los esquemas tipados (choice, score, noul) y el contrato de
  decisión: orden canónico de criterios, serialización que no ordena, validación y `Trace`.
  Tests: esquemas y contrato de orden.
- **F1 Adaptadores.** Base común (`capabilities` y `decide`), `MockAdapter` determinista y
  `LayaAdapter` por HTTP a `laya-serve`. Salida normalizada por tipo y `Trace` con `criteria_order`.
  Test con Mock.
- **F2 JEV.** `JevAdapter` con `base_url` configurable, `privacy=cloud`, `dry_run` sin red. Test con
  un servidor falso local.
- **F3 Servicio.** `agora_serve` (FastAPI): `/health`, `/backends`, `/v1/decide`,
  `/v1/decide/compare`, `/v1/packs`, `/v1/runs`. Test con `TestClient` y Mock.
- **F4 CLI.** `agora/cli.py` con `backends`, `decide`, `compare`, `packs list`, `packs validate`,
  `serve`. Test invocando `main()`.
- **F5 Pack GENERAL.** Tres plantillas (routing, risk gate, pre-check de inyección) y validador de
  packs que conserva el orden. Test.
- **F6 Pack SOC.** Netwatch (choice `expected_ai_use, background_exfil_suspect, telemetry_noise,
  unrelated`; score de 4 niveles; acción inmediata) y finding (choice `true_positive,
  false_positive, noise`; score de 4 niveles; acción). Test de referencia congelado.
- **F7 UI.** Single-page sin build: selector de parte GENERAL/SOC-SIEM, estado, preguntas, backends,
  botón Decidir, tarjetas de distribución y panel de traza. Test de carga.
- **F8 ATT&CK.** `tools/gate.py` e `tools/import_attack.py`: leer el bundle STIX, construir items con
  la táctica como ground truth y validar (id único, padre de subtécnica, cobertura). Test con fixture.
- **F9 NVD.** Reutilizar el gate para CVE (NVD es dominio público). Salida `data/soc/nvd_items.jsonl`.
- **F10 Eikos.** `EikosAdapter` por HTTP a `serve.py` (con imágenes opcionales) y guía de arranque de
  Eikos-4B (cabe en 16 GB; Eikos-27B INT4 son 19,4 GB y no caben). Test con servidor falso.
- **F11 Empaquetado.** README, LICENSE Apache 2.0, `docs/contrato-decision.md`, `.gitignore`.

Cuando las 12 pasen: escribe la marca de fin.
