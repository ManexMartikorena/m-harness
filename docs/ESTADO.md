# Estado del proyecto

Última actualización: 2026-10-19. **Diseño cerrado**: análisis
(`docs/ANALISIS.md`) y diseño (`docs/DESIGN.md`) aprobados. Empieza la fase de
código con el hito 1.

Lo primero al abrir: "Siguiente paso", más abajo.

## Fase actual

**Desarrollo, hito 1 (esqueleto): spec propuesta, pendiente de aprobación.**

- Repositorio: https://github.com/ManexMartikorena/m-harness (público).
- Última versión: ninguna.
- Ramas abiertas: `docs/spec-hito-1-esqueleto` (spec del hito 1).

## Para la release

Nada todavía. Aquí va solo lo que el workflow de release no hace solo: una
variable nueva o un paso fuera de lo normal.

## Hecho

Lo más reciente primero.

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

1. **Humano:** revisar el PR de la spec del hito 1
   (`docs/specs/hito-1-esqueleto.md`), contestar la decisión abierta 13
   (Windows nativo o WSL2, y job de Windows en el CI) e integrarlo, que es
   aprobarla.
2. **Agente:** implementar el PR 1 del hito 1 (`feature/hito-1-esqueleto`),
   en el orden de piezas de la spec (§6).

## Pendientes / decisiones abiertas

**Para el hito 1:**
- Tras integrar su PR 1, añadir al ruleset "main protegida" los checks
  obligatorios del CI (spec del hito 1, §6).
- Actualizar uv a 0.13.1 o posterior en cada PC: el hito 1 lo exige
  (spec §1.1). En este PC hay 0.12.17.
- Decisión abierta 13 de la spec: Windows nativo o WSL2 en este PC.

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
