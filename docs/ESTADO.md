# Estado del proyecto

Última actualización: 2026-10-20. **Hito 1 (esqueleto) cerrado y publicado
como `v0.1.0`.** Hito 2: PRs #8, #9 y #10 abiertos; verificación a mano hecha.

Lo primero al abrir: "Siguiente paso", más abajo.

## Fase actual

**Desarrollo. Hito 1 cerrado (`v0.1.0`). Hito 2 (primera conversación): spec
APROBADA (PR #7); PRs 1 a 3 (#8, #9 y #10) abiertos, por integrar;
verificación a mano hecha. Falta el PR 4 (cierre).**

- Repositorio: https://github.com/ManexMartikorena/m-harness (público).
- Última versión: **`v0.1.0` — Esqueleto** (2026-10-20):
  https://github.com/ManexMartikorena/m-harness/releases/tag/v0.1.0
- Ramas abiertas, apiladas: `feature/hito-2-nucleo` (PR 1, #8) ←
  `feature/hito-2-openai` (PR 2, #9) ← `feature/hito-2-terminal` (PR 3, #10).
  Las integradas se conservan en GitHub.

## Para la release

Aquí va solo lo que el workflow de release no hace solo: una variable nueva o
un paso fuera de lo normal.

- Nada pendiente. `v0.1.0` salió sin pasos fuera de lo normal.

## Hecho

Lo más reciente primero.

- **Verificación a mano del hito 2, 2026-10-20** (spec §7 y §12.10): los
  9 puntos en verde con OpenCode Go y `glm-5.3-flash`. Go acepta
  `Authorization: Bearer`. Clave del mantenedor en el `.env` y
  `~/.config/maha/config.toml` creados en el WSL del PC de Windows.
- **Hito 2, PR 3 abierto, 2026-10-20** (PR #10) (rama `feature/hito-2-terminal`;
  piezas 14 a 18): `config.py`, conversación en la terminal, cableado en
  `bootstrap`, `.env.example` y `PUESTA_EN_MARCHA` §3.1, y mapa. En verde:
  116 tests. Probado con un pty: Ctrl+D y `/exit` salen con 0, Ctrl+C con
  130, y un error de red no corta la conversación.
  - corrige la spec §1.11, con el visto bueno del mantenedor: la entrada se
    lee sin hilos, porque con `input()` en un hilo Ctrl+C colgaba `maha`
    (spec §12.6).
- **Hito 2, PR 2 abierto, 2026-10-20** (PR #9) (rama `feature/hito-2-openai`,
  apilada sobre la del PR 1; piezas 9 a 13): httpx 0.28.1 y respx 0.23.1,
  `OpenAIChatClient` con petición, cabeceras, respuesta y errores, y mapa.
  En verde: 81 tests. Un fallo encontrado (clave cortada por el límite de
  300 caracteres), convertido en test y arreglado. Lo imprevisto, en la
  spec §12.
- **Hito 2, PR 1 abierto, 2026-10-20** (PR #8) (rama `feature/hito-2-nucleo`;
  piezas 1 a 8 de la spec §6): Pydantic 2.14.1, mensajes, petición y
  respuesta, errores del modelo, puerto `ModelClient`, `FakeModelClient`,
  `Chat` y mapa. En verde: ruff, mypy, import-linter y pytest (32 tests).
  Lo imprevisto, en la spec §12.
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

1. **Humano:** revisar e integrar, en este orden y con merge commit, los
   PRs #8, #9 y #10. Cada uno muestra también los commits de los anteriores
   hasta que se integran.
2. **Agente:** PR 4 del hito 2 (`feature/hito-2-cierre`), piezas 19 a 22:
   versión 0.2.0, nota 02 de la guía, spec IMPLEMENTADA y docs.

**Sesión del 2026-10-20 en el WSL del PC de Windows:** PRs 1 a 3 del hito 2
abiertos en GitHub y verificación a mano hecha. Se sigue desde el punto 1.

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
   verde, y `uv run maha --version` → `maha 0.1.0`.

Para revisar la spec en el PC (opcional, también se puede en GitHub):
`git fetch && git switch docs/spec-hito-2-primera-conversacion`.

Después, lanzar el agente desde el clon. Él lee `AGENTS.md` y este fichero,
y sigue por el primer punto de "Siguiente paso" que no esté hecho. Para
saber cuál es, el agente lo contrasta con GitHub (`gh pr list`, `gh release
list`). Si hay un PR abierto, se trabaja en su rama:
`git switch <rama> && git pull`.

Regla: no trabajar en los dos PCs a la vez sin push entre medias.

## Pendientes / decisiones abiertas

**Puestos de trabajo:**
- Ubuntu de casa: uv ≥ 0.13.1, `gh` con el scope `workflow`, `uv sync` y
  `pre-commit install` (ver "Al abrir el agente en otro PC"). Para conversar
  con `maha`, además: el `.env` con `OPENCODE_API_KEY` y
  `~/.config/maha/config.toml` (`PUESTA_EN_MARCHA` §2 y §3.1). El WSL del PC
  de Windows ya está listo, con clave y configuración.

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
