# Estado del proyecto

Última actualización: 2026-10-20. **Diseño cerrado**: análisis
(`docs/ANALISIS.md`) y diseño (`docs/DESIGN.md`) aprobados. Empieza la fase de
código con el hito 1.

Lo primero al abrir: "Siguiente paso", más abajo.

## Fase actual

**Desarrollo, hito 1 (esqueleto): PR 1 terminado en local (10 piezas de 15);
falta subirlo, revisarlo e integrarlo. Después, el PR 2.**

- Repositorio: https://github.com/ManexMartikorena/m-harness (público).
- Última versión: ninguna.
- Ramas abiertas: `feature/hito-1-esqueleto` (PR 1 del hito 1), con las
  piezas 1 a 10 commiteadas, de `9de9fa6` a `db7ea5d`.

## Para la release

Nada todavía. Aquí va solo lo que el workflow de release no hace solo: una
variable nueva o un paso fuera de lo normal.

## Hecho

Lo más reciente primero.

- **Hito 1, PR 1 terminado en local, 2026-10-20** (WSL del PC de Windows).
  Rama `feature/hito-1-esqueleto`, un commit por pieza (spec §6, piezas
  1 a 10):
  - proyecto uv, ruff, mypy estricto, las cuatro capas con import-linter,
    pytest con el test de arquitectura, el adaptador `cli` con `--version`,
    `bootstrap.py` y el comando `maha`, pre-commit, CI y mapa;
  - en verde: ruff, mypy, import-linter y pytest (8 tests), con Python 3.14
    y también con 3.15;
  - verificación a mano (spec §7): puntos 1 a 7 hechos; el 8 es el CI en
    GitHub, al abrir el PR;
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

1. **Humano** (o el agente, si se lo pide): push de
   `feature/hito-1-esqueleto` y abrir el PR 1 con la plantilla. **Sin este
   push, el otro PC no ve nada de lo hecho.**
2. **Humano:** revisar el PR 1 (commit a commit) y comprobar en GitHub que
   pasan `checks (3.14)`, `checks (3.15)` y `secrets`. Si `secrets` falla
   por permisos, ver spec §10. Integrar con merge commit.
3. **Humano**, justo después: en el ruleset "main protegida", exigir esos
   tres checks (`docs/PUESTA_EN_MARCHA.md` §5).
   Y lanzar el CI a mano una vez sobre `main` (*Actions → CI → Run
   workflow*, o `gh workflow run ci.yml --ref main`): así gitleaks revisa el
   historial entero, también los commits de antes del CI (spec §12).
4. **Agente:** PR 2 (`feature/hito-1-release`), piezas 11 a 15 de la spec
   §6: release, versión 0.1.0, nota de la guía, cierre de la spec y docs.

### Al abrir el agente en otro PC (por ejemplo, el Ubuntu de casa)

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
   verde, y `uv run maha --version`.

Después, lanzar el agente desde el clon. Él lee `AGENTS.md` y este fichero,
y sigue por el primer punto de "Siguiente paso" que no esté hecho. Si el
PR 1 sigue sin integrar, se trabaja en su rama:
`git switch feature/hito-1-esqueleto && git pull`.

Regla: no trabajar en los dos PCs a la vez sin push entre medias.

## Pendientes / decisiones abiertas

**Para el hito 1:**
- Tras integrar su PR 1, añadir al ruleset "main protegida" los checks
  obligatorios del CI (Siguiente paso 3).
- Ubuntu de casa: uv ≥ 0.13.1, `uv sync` y `pre-commit install` (ver "Al
  abrir el agente en otro PC"). El WSL del PC de Windows ya está listo.

**Externas, con el hito en que bloquean:**
- **Proveedor de modelos** (hito 2): suscripción propia a OpenCode Go (un solo
  miembro por espacio de trabajo) u OpenCode Zen con pago por uso. Mientras
  tanto, `FakeModelClient`.

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

- [ ] 1. Esqueleto. `v0.1.0`
- [ ] 2. Primera conversación. `v0.2.0`
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
