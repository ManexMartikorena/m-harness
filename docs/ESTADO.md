# Estado del proyecto

Última actualización: 2026-10-20. **Hito 2 (primera conversación) cerrado y
publicado como `v0.2.0`.** Hito 3 (streaming): spec PROPUESTA, PR abierto.

Lo primero al abrir: "Siguiente paso", más abajo.

## Fase actual

**Desarrollo. Hito 2 cerrado (`v0.2.0`). Hito 3 (streaming): spec PROPUESTA
en la rama `docs/spec-hito-3-streaming`, PR abierto.**

- Repositorio: https://github.com/ManexMartikorena/m-harness (público).
- Última versión: **`v0.2.0` — Primera conversación** (2026-10-20):
  https://github.com/ManexMartikorena/m-harness/releases/tag/v0.2.0
- Ramas abiertas: `docs/spec-hito-3-streaming` (spec del hito 3). Las
  integradas se conservan en GitHub.

## Para la release

Aquí va solo lo que el workflow de release no hace solo: una variable nueva o
un paso fuera de lo normal.

- Nada pendiente. `v0.2.0` salió sin pasos fuera de lo normal.

## Hecho

Lo más reciente primero.

- **Spec del hito 3 propuesta, 2026-10-20** (rama
  `docs/spec-hito-3-streaming`, PR abierto):
  - `complete()` sale del puerto: queda `stream()`, y `collect()` (en
    `application`) construye la respuesta entera a partir de los eventos;
  - SSE (*Server-Sent Events*, el formato de streaming de las APIs) a mano,
    sin dependencias nuevas. Las líneas se parten solo en CRLF, LF o CR:
    `aiter_lines()` de httpx 0.28.1 parte también en U+2028 y otros, y
    rompería un JSON válido;
  - corrige DESIGN §5: `MessageEnd` lleva `model`;
  - Ctrl+C a mitad de respuesta corta la respuesta y vuelve al prompt;
  - sonda lanzada en la fase de spec, con permiso del mantenedor (spec
    §1.7): los tokens de salida altos de `glm-5.3-flash` son razonamiento.
    `completion_tokens` incluye `reasoning_tokens`: para "OK", 13 de 16,
    18 de 21 y 43 de 46 (varía mucho). Llega en `delta.reasoning_content`
    con stream y en `message.reasoning` sin él;
  - OpenCode manda `usage` aunque no se pida `stream_options`; ~5 s de
    silencio hasta el primer byte. En OpenCode solo queda POR VERIFICAR el
    formato de un error a mitad de stream.

  Hechos comprobados ese día por el agente en la documentación oficial: el
  endpoint de Go, `https://opencode.ai/inference/go/openai/v1/chat/completions`,
  coincide con el código; la URL que dio Context7 estaba desfasada.
- **Ubuntu de casa preparado, 2026-10-20:**
  - Ubuntu 24.04.5 LTS, no 26.04 como el CI. Funciona: 116 tests, mypy,
    lint-imports y ruff en verde con el python3.14 del sistema (3.14.8), sin
    Python gestionado por uv;
  - uv 0.13.4, con el instalador oficial y `UV_NO_MODIFY_PATH=1`, en
    `~/.local/bin` (ya estaba en el PATH; no se tocó ningún fichero de
    shell). `uv sync` y `pre-commit install` hechos;
  - `.env` con la clave de OpenCode Go y `~/.config/maha/config.toml`.
    Prueba de dos turnos con `glm-5.3-flash` correcta;
  - `gh auth status`: login en github.com como ManexMartikorena, con el scope
    `workflow`;
  - aviso: en ese PC hay otro uv 0.12.17 en `~/.hermes/bin/` (de hermes,
    fuera del PATH) que comparte `~/.cache/uv`. Para quitar uv, no usar
    `uv cache clean` ni `rm -r "$(uv tool dir)"`;
  - dato: "OK" contó `22 in · 67 out` (spec 2 §12.12; se investiga en la
    spec 3, §1.7).
- **PR #12 integrado, 2026-10-20** (merge `80d958d`): cierre de la
  documentación del hito 2.
- **`v0.2.0` publicada, 2026-10-20.** Tag anotado sobre el merge del PR #11
  (`9480b1d`). `release.yml` creó la release en 12 s: título
  "v0.2.0 — Primera conversación", las notas del tag y la lista de PRs #6 a
  #11. `uvx --from git+https://github.com/ManexMartikorena/m-harness@v0.2.0
  maha --version` → `maha 0.2.0`. El CI del merge del #11 pasó entero (ya sin
  cancelaciones en `main`).
- **Hito 2, PR 4 (#11) integrado, 2026-10-20** (merge `9480b1d`; piezas 19
  a 22): versión 0.2.0, nota
  `docs/guia/02-llamada-a-un-llm.md`, spec en IMPLEMENTADA, y README, MAPA y
  ESTADO al día.
  - fuera de plan, a petición del mantenedor: el CI ya no cancela las
    ejecuciones de los pushes a `main`. Al integrar #8, #9 y #10 seguidos,
    las de #8 y #9 salieron canceladas (spec §12.13).
- **Hito 2, PRs 1 a 3 integrados, 2026-10-20** (#8 `ca1aa21`, #9 `dcb7983`,
  #10 `a1964f5`):
  - PR 1, el núcleo: Pydantic 2.14.1, mensajes, petición y respuesta,
    errores del modelo, puerto `ModelClient`, `FakeModelClient` y `Chat`;
  - PR 2, el adaptador: httpx 0.28.1, respx 0.23.1 y `OpenAIChatClient`.
    Un fallo encontrado (la clave cortada por el límite de 300 caracteres),
    convertido en test y arreglado;
  - PR 3, configuración y terminal: `config.py`, la conversación, el
    cableado en `bootstrap`, `.env.example` y `PUESTA_EN_MARCHA` §3.1.
    Corrige la spec §1.11, con el visto bueno del mantenedor: la entrada se
    lee sin hilos, porque con `input()` en un hilo Ctrl+C colgaba `maha`;
  - en verde: 116 tests, con Python 3.14 y 3.15. Lo imprevisto, en la spec
    §12.
- **Verificación a mano del hito 2, 2026-10-20** (spec §7 y §12.10): los
  9 puntos en verde con OpenCode Go y `glm-5.3-flash`. Go acepta
  `Authorization: Bearer`. Clave del mantenedor en el `.env` y
  `~/.config/maha/config.toml` creados en el WSL del PC de Windows.
- **Spec del hito 2 aprobada, 2026-10-20** (PR #7, merge `09ebdb5`), sin
  cambios.
- **Spec del hito 2 propuesta, 2026-10-20** (rama
  `docs/spec-hito-2-primera-conversacion`, PR abierto en GitHub, sin
  integrar). Proveedor elegido por el mantenedor: OpenCode Go.
  - hechos comprobados ese día en la documentación oficial (spec §1.1): URLs
    de chat completions de OpenCode Go y Zen, cabecera
    `x-opencode-session`, modelos sin entrenamiento, formato de OpenAI;
    versiones de pydantic 2.14.1, httpx 0.28.1 y respx 0.23.1, probadas con
    Python 3.14 y 3.15;
  - corrige DESIGN §7: la configuración del proyecto solo elige proveedor y
    modelo (spec §1.10);
  - cuatro PRs de implementación (spec §6).

- **`v0.1.0` publicada, 2026-10-20.** Tag anotado sobre el merge del PR #5
  (`e78f7d9`). `release.yml` creó la release en 12 s: título
  "v0.1.0 — Esqueleto", las notas del tag y la lista de PRs #1 a #5.
  `uv tool install git+https://github.com/ManexMartikorena/m-harness@v0.1.0`
  instala `maha 0.1.0`. Spec §7 completa.
- **Hito 1, PR 2 (#5) integrado, 2026-10-20** (merge `e78f7d9`; piezas 11 a
  15 de la spec §6):
  - workflow de release, versión 0.1.0, nota de la guía
    `docs/guia/01-arquitectura-hexagonal.md`, spec en IMPLEMENTADA, y README,
    MAPA, PUESTA_EN_MARCHA y ESTADO al día;
  - fuera de plan, con el visto bueno del mantenedor: el CI fija gitleaks
    8.30.1, la misma versión que pre-commit (spec §12).
- **GitHub tras el PR 1, 2026-10-20** (humano): el ruleset "main protegida"
  exige `checks (3.14)`, `checks (3.15)` y `secrets`, con "up to date"
  activada (`PUESTA_EN_MARCHA` §5). CI lanzado a mano sobre `main`: gitleaks
  revisó el historial entero (41 commits), sin secretos.
- **Hito 1, PR 1 (#4) integrado, 2026-10-20** (merge `e935068`). Un commit
  por pieza (spec §6, piezas 1 a 10):
  - proyecto uv, ruff, mypy estricto, las cuatro capas con import-linter,
    pytest con el test de arquitectura, el adaptador `cli` con `--version`,
    `bootstrap.py` y el comando `maha`, pre-commit, CI y mapa;
  - en verde: ruff, mypy, import-linter y pytest (8 tests), con Python 3.14
    y también con 3.15;
  - verificación a mano (spec §7): puntos 1 a 8 hechos;
  - lo imprevisto, en la spec §12 "Aprendido al implementar": ruff formatea
    Markdown, mypy e import-linter piden que existan `tests/` y las capas, y
    el hook de gitleaks no mira el primer commit de un repo.

- **Clon en `~/` en el PC de Windows, 2026-10-20:** el agente trabaja desde
  `~/Desarrollo/m-harness`, dentro de WSL. El clon viejo de `/mnt/c/…`, limpio
  y al día, se borró.
- **WSL preparado en el PC de Windows, 2026-10-19:** Ubuntu 26.04.1,
  uv 0.13.1, gh 2.102 con login y el agente dentro de WSL.
- **GitHub revisado, 2026-10-19:** ajustes, rulesets y alertas coinciden con
  `docs/PUESTA_EN_MARCHA.md` §5. Sin issues, tags ni releases.
- **Spec del hito 1 aprobada, 2026-10-19** (PR #2), sin cambios.
  - Plataforma: Linux. En Windows, Ubuntu 26.04 en WSL2, con el agente
    dentro de WSL. CI con `ubuntu-26.04`.
  - Versiones de las herramientas comprobadas ese día (spec §1.1).
- **GitHub configurado, 2026-10-19.**
  - Solo merge commit; las ramas integradas se conservan.
  - `main` y los tags `v*` protegidos con rulesets.
  - Alertas de seguridad activadas.

  Detalle en `docs/PUESTA_EN_MARCHA.md` §5.
- **Repositorio público creado y primer push, 2026-10-19.** Un commit por
  fichero fundacional.
- **Documentos fundacionales, 2026-10-19:**
  - en la raíz: `AGENTS.md`, `CLAUDE.md`, `README.md`, `LICENSE`, `.gitignore`
    y `.gitattributes`;
  - en `docs/`: `ANALISIS.md`, `DESIGN.md`, `ESTADO.md`, `PUESTA_EN_MARCHA.md`,
    `MAPA.md`, `guia/README.md` y `specs/PLANTILLA.md`;
  - en `.github/`: `pull_request_template.md`.
- **Decisiones de diseño del mantenedor, 2026-10-19:**
  - sin frameworks de agentes: a mano lo que es del agente, fontanería
    estándar y la industria documentada al lado;
  - monolito modular con arquitectura hexagonal; asíncrono con `asyncio`;
  - httpx directo; adaptador de OpenAI primero y de Anthropic en el hito 9;
  - trazas propias y OpenTelemetry opcional; Pydantic también en el dominio;
  - comando `maha`, módulo `mharness`, distribución `m-harness`;
  - spec en su propio PR; integración con merge commit; muchos commits
    pequeños;
  - todo lo que hace el agente de código se explica al mantenedor, corto y
    directo.
- **Análisis cerrado, 2026-10-19.**

## Siguiente paso

1. **Humano:** decidir las dudas de la spec §11 e integrar el PR de la spec
   con merge commit (pasa a APROBADA). Las dudas, con su número en §11:
   - 1: `complete()` fuera del puerto;
   - 2: indicador "esperando…" durante el silencio inicial (recomendada la
     opción B);
   - 3: Ctrl+C a mitad de respuesta vuelve al prompt;
   - 5: `Usage` sin `None`.
2. **Agente:** implementar el hito 3 por piezas (spec §6) en
   `feature/hito-3-eventos`, desde la pieza 1: eventos del dominio. La sonda
   ya no es una pieza.

**Sesión abierta el 2026-10-20 en el Ubuntu de casa.** El mantenedor revisó la
spec y pidió push y PR. Se sigue desde el punto 1.

### Al abrir el agente en otro PC (por ejemplo, de vuelta en el WSL del PC de Windows)

Una vez, la primera vez tras este hito:
1. `cd` al clon y `git switch main && git pull`.
2. `uv --version`: tiene que ser 0.13.1 o posterior (si no,
   `uv self update`).
3. `gh auth status`: con login en github.com y el scope `workflow` en
   "Token scopes". Si falta: `gh auth refresh --hostname github.com --scopes
   workflow` (sin él, GitHub rechaza el push de `.github/workflows/`).
4. `uv sync` y `uv run pre-commit install` (`PUESTA_EN_MARCHA` §0). La
   primera ejecución de los hooks descarga Go y compila gitleaks.
5. Comprobar: `uv run pytest`, `uv run mypy` y `uv run lint-imports` en
   verde, y `uv run maha --version` → `maha 0.2.0`.
6. Para conversar: `cp .env.example .env` con la clave de OpenCode Go, y
   `~/.config/maha/config.toml` (`PUESTA_EN_MARCHA` §2 y §3.1). La clave no
   viaja por git: se copia de la consola de opencode.ai (o se crea otra para
   ese PC). Probar con `uv run --env-file .env maha`: dos turnos y `/exit`.

Después, lanzar el agente desde el clon. Él lee `AGENTS.md` y este fichero,
y sigue por el primer punto de "Siguiente paso" que no esté hecho. Para
saber cuál es, el agente lo contrasta con GitHub (`gh pr list`, `gh release
list`). Si hay un PR abierto, se trabaja en su rama:
`git switch <rama> && git pull`.

Regla: no trabajar en los dos PCs a la vez sin push entre medias.

## Pendientes / decisiones abiertas

**Puestos de trabajo:**
- Los dos listos, con clave y configuración: el WSL del PC de Windows
  (Ubuntu 26.04.1) y el Ubuntu de casa (24.04.5, no 26.04; ver "Hecho",
  2026-10-20).

**Externas, con el hito en que bloquean:**
- **Proveedor de modelos: OpenCode Go**, funcionando desde el 2026-10-20
  (verificación a mano del hito 2).

**Se deciden en la spec de su hito:**
- búsqueda en la memoria (hito 13);
- tecnología del sandbox (hito 14);
- cliente MCP a mano o con el SDK oficial (hito 16);
- proveedor de búsqueda web (hito 17);
- tratamiento de PDFs (hito 18).

**Por medir:**
- Línea base de las evals (hito 8).
- Ahorro de tokens de la memoria (hito 13).

## Versiones

Fase de desarrollo (DESIGN §14), un tag por hito:

- [x] 1. Esqueleto. `v0.1.0` (2026-10-20)
- [x] 2. Primera conversación. `v0.2.0` (2026-10-20)
- [ ] 3. Streaming. `v0.3.0`
- [ ] 4. Tool calling y bucle agéntico. `v0.4.0`
- [ ] 5. Permisos y herramientas con efecto. `v0.5.0`
- [ ] 6. Sesiones e historial. `v0.6.0`
- [ ] 7. Trazas y coste. `v0.7.0`
- [ ] 8. Evals y modo no interactivo. `v0.8.0`
- [ ] 9. Adaptador de Anthropic. `v0.9.0`
- [ ] 10. System prompt por capas. `v0.10.0`
- [ ] 11. Gestión del contexto. `v0.11.0`
- [ ] 12. Skills. `v0.12.0`
- [ ] 13. Memoria persistente. `v0.13.0`
- [ ] 14. Sandbox. `v0.14.0`
- [ ] 15. Subagentes. `v0.15.0`
- [ ] 16. MCP. `v0.16.0`
- [ ] 17. Web. `v0.17.0`
- [ ] 18. Multimodal. `v0.18.0`
- [ ] 19. Interfaz completa. `v0.19.0`
- [ ] 20. Exportador OpenTelemetry. `v0.20.0`
- [ ] 21. Versión 1.0. `v0.21.0` y `v1.0.0`

**Mantenimiento.** `v1.N.0` para una mejora y `v1.N.M` para un arreglo.
