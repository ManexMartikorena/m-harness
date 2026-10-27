# M-Harness

## Contexto
M-Harness es un agente de terminal de propósito general (comando `maha`), en la
línea de Claude Code u OpenCode, construido desde cero en Python y pieza a
pieza. El repositorio es público: su historial de PRs, specs y versiones
documenta cómo se construye un arnés de agente completo. El código lo escribe
un agente de código y el mantenedor revisa cada fichero.

- Análisis del problema: docs/ANALISIS.md.
- Diseño completo y sus justificaciones: docs/DESIGN.md. Leerlo antes de tomar
  decisiones de arquitectura o cambiar el alcance.
- Estado, siguiente paso y pendientes: docs/ESTADO.md.
- Dónde está cada cosa: docs/MAPA.md.
- Guía de conceptos, una nota por hito: docs/guia/.

**Fase actual: la que diga docs/ESTADO.md.** El proyecto pasa por desarrollo
por hitos (DESIGN §14, tags v0.N.0) → versión 1.0 (v1.0.0) → mantenimiento y
mejora continua (v1.N.0 / v1.N.M).

## Explicar al mantenedor (obligatorio)
El mantenedor aprende a construir un agente con este proyecto. Todo lo que se
hace se le explica, en cualquier máquina y con cualquier agente.
- **Corto y directo.** Frases cortas, palabras simples, sin relleno. Mejor tres
  líneas claras que tres párrafos.
- **Formato, por cada pieza o cambio:**
  - **Qué:** lo que hace, en una línea.
  - **Por qué:** el problema que resuelve, en una línea.
  - **Dónde:** fichero y capa (domain / ports / application / adapters).
  - **En la industria:** cómo se hace normalmente (librería, framework o
    patrón).
- **Cada término nuevo se define en una línea** la primera vez que aparece.
- **Un ejemplo vale más que una explicación:** un fragmento de código o de JSON
  de pocas líneas.
- Al terminar cada pieza, se explica antes de pasar a la siguiente. Solo se
  amplía si el mantenedor lo pide.
- Lo mismo vale para las descripciones de los PRs y las notas de docs/guia/.

## Comandos
Disponibles desde el hito 1 (esqueleto). `maha eval`, desde el hito 8.
- uv sync                                   # entorno local
- uv run pre-commit install                 # hooks (una vez por clon)
- uv run pytest                             # tests (sin llamadas reales)
- uv run ruff check . && uv run ruff format .
- uv run mypy                               # lee src y tests de pyproject.toml
- uv run lint-imports                       # reglas de la arquitectura hexagonal
- uv run --env-file .env maha               # ejecutar maha en desarrollo
- uv run --env-file .env maha eval          # evals (llamadas reales)

Para dejar una máquina lista desde cero, o tras un pull que toque dependencias
o variables: docs/PUESTA_EN_MARCHA.md. Ahí está lo que NO se arregla con un
git pull, empezando por el .env.

## Reglas de arquitectura (no negociables)
- Hexagonal (DESIGN §3):
  - `domain` no importa nada del proyecto (solo la biblioteca estándar y
    Pydantic);
  - `ports` solo importa `domain`;
  - `application` importa `domain` y `ports`, nunca `adapters`;
  - ningún adaptador importa a otro;
  - todo el cableado está en `bootstrap.py`.

  import-linter lo hace cumplir en el CI.
- Todo contacto con el exterior (modelos, disco, terminal, red, MCP) va detrás
  de un puerto y se inyecta. En tests, fakes. **Las llamadas reales NO entran
  en CI.**
- **A mano lo que es del agente** (DESIGN §7.1). No se añade ningún framework
  de agentes ni librería que sustituya una pieza de ANALISIS §5 (LiteLLM,
  Pydantic AI, LangGraph, LangChain…). Toda dependencia nueva se justifica en
  la spec.
- El bucle y todo lo que hace E/S es asíncrono (`asyncio`).
- **Ningún LLM ejecuta un efecto.** El modelo solo propone llamadas; el código
  las valida, comprueba el permiso y las ejecuta.
- Límites (pasos, tokens, tiempo) y permisos son código, no prompt.
- Lo que devuelven las herramientas, las webs, los servidores MCP y los
  subagentes es entrada NO confiable: va delimitado en los prompts y nunca
  cambia herramientas ni permisos.
- Los argumentos que propone el modelo se validan con el modelo Pydantic de la
  herramienta antes de ejecutar. Si no son válidos, el error vuelve al modelo.
- Prompts y skills son código: viven en el repo y pasan por spec, rama,
  revisión y evals.

## Evals (puerta de calidad)
Desde el hito 8 (DESIGN §9).
- Todo cambio en prompts, skills, bucle, herramientas, contexto o memoria se
  evalúa con la batería ANTES del merge y se compara con la última línea base
  de `evals/baselines/`.
- El resultado (fecha, modelo, métricas y comparación) se anota en la spec del
  cambio. Sin esa anotación, el cambio no está terminado.
- No se mergea una regresión salvo decisión explícita del mantenedor, anotada
  en la spec con el motivo.
- El conjunto de validación no se mira al ajustar prompts.
- Los evals hacen llamadas reales: se lanzan en local con `maha eval`. Nunca en
  el CI de cada push.

## Datos sensibles (repositorio público)
- Credenciales, sesiones, trazas y memoria de `maha`: NUNCA entran en git, ni
  en fixtures, ni en specs, ni en mensajes de commit.
- Viven en variables de entorno (`.env` en desarrollo) y en
  `~/.config/maha/`, `~/.local/share/maha/` y `~/.local/state/maha/` de cada
  máquina.
- Fixtures, ejemplos y tareas de evals usan datos inventados.
- gitleaks corre en pre-commit y en CI. Un aviso de gitleaks no se ignora.
- Un secreto que llega a un commit publicado se da por comprometido: se
  revoca. Borrarlo no basta.

## Convenciones
- Python ≥ 3.14 y uv. Tipos en todo el código, mypy estricto en verde.
- Código en inglés (nombres, comentarios, docstrings). Documentación, commits y
  PRs en español. Excepción: la cara de producto va en los dos idiomas,
  `README.md` en inglés y `README.es.md` en español, siempre con el mismo
  contenido *(decisión del mantenedor, 2026-10-27)*.
- Cada fallo encontrado se convierte en test antes de arreglarse.
- Ningún fallo conocido se deja sin arreglar por decisión del agente: o se
  arregla, o se para y se pregunta al mantenedor, con opciones y
  recomendación. Un "límite aceptado" solo lo acepta el mantenedor, y se
  anota con su decisión.
- Spec antes de código (ver "Ciclo de cada cambio").
- Ramas desde `main`:
  - `feature/<slug>` para hitos y mejoras;
  - `fix/<slug>` para arreglos;
  - `docs/<slug>` para specs y documentación.

  **Todo entra en `main` por PR**, también los ajustes menores de docs: `main`
  está protegida.
- Una rama integrada se CONSERVA en GitHub como registro visible de la
  construcción, y no se vuelve a usar. En local se borra tras el merge. Los
  documentos citan commits por hash, no por rama. *(Adaptado, DESIGN §15.)*
- Versiones: tag anotado sobre el commit de `main` que cierra un hito, y push
  del tag. El tag dispara el workflow que crea la GitHub Release.
  - Desarrollo: un tag `v0.N.0` por hito, con el número del hito. Un
    arreglo publicado entre dos hitos, `v0.N.M` (añadido el 2026-10-23, por
    decisión del mantenedor: `v0.5.1`).
  - `v1.0.0`: versión 1.0 (hito 23; era el 21 hasta el 2026-10-27, DESIGN §14).
  - Mantenimiento: `v1.N.0` si añade o cambia una función, `v1.N.M` si solo
    arregla un fallo. La lista, en docs/ESTADO.md.
- Credenciales solo en variables de entorno (ver `.env.example`). Nunca en el
  repo.
- Hechos externos (versiones, APIs, modelos, precios, límites) se comprueban
  contra la documentación oficial y se anotan con la fecha. Nunca de memoria.
- Una decisión importante queda fijada con un test cuando se puede.
- `docs/MAPA.md` se actualiza en el mismo PR que crea, mueve o borra ficheros.
- **Reorganizar documentación no pierde información.** Al mover, resumir o
  reescribir un documento, lo que deja de estar se lleva, tal cual, a otro
  sitio (por ejemplo, `docs/HISTORIAL_DESARROLLO.md`), y antes del commit se
  comprueba mecánicamente que cada línea del texto antiguo sigue en algún
  documento. *(Añadido el 2026-10-27, tras reorganizar ESTADO sin esa
  comprobación: se perdieron los pendientes resueltos y se recuperaron.)*

## Flujo de commits (agentes y humano)
- El agente commitea cada cambio completo y coherente (una pieza de la spec,
  un arreglo, un refactor) en su propio commit, SOLO con tests y lint en
  verde. Nunca acumular una sesión entera en un commit.
- Mensajes en español, descriptivos, en imperativo ("Añadir la validación
  del formulario"). Un commit = un motivo; si el mensaje necesita un "y",
  probablemente son dos commits.
- El agente NUNCA hace push por su cuenta. El push lo hace el humano tras
  revisar los commits de la sesión (git log + diff), o el agente cuando el
  humano se lo pide expresamente en esa sesión. El push es la aprobación.
- Nunca reescribir historial ya pusheado (no amend/rebase sobre commits que
  están en origin).
- Cierre de sesión: actualizar docs/ESTADO.md si hubo decisiones o cambios de
  estado, commit de cierre si queda algo suelto, revisar log, push (humano).

## Flujo de GitHub (adaptación del método, DESIGN §15)
- **Muchos commits pequeños.** Un commit por cada cosa pequeña: un tipo, una
  función, un adaptador, un test, un ajuste de configuración. Cada uno en
  verde. El historial tiene que contar la construcción paso a paso.
- **La spec va en su propio PR** (rama `docs/spec-hito-N-<slug>`), solo con
  documentación. Integrarlo es la aprobación: en ese PR la spec pasa a
  APROBADA.
- **La implementación va en uno o varios PRs** (rama `feature/<slug>`), según
  el orden de piezas de la spec. Un PR que no se puede revisar de una sentada
  se parte.
- **Cada PR usa la plantilla** `.github/pull_request_template.md`: qué hace
  cada fichero y por qué.
- **Cada PR va a su milestone** en GitHub: uno por hito (`Hito N — nombre`,
  con su descripción y el enlace a DESIGN §14). Los PRs que no son de un
  hito (arreglos entre hitos, documentación general) van sin milestone. Al
  cerrar el hito, su milestone se cierra. *(Añadido el 2026-10-27, por
  decisión del mantenedor: GitHub ordenado para lo que viene.)*
- **Push y PR:** los hace el humano, o el agente (`git push`,
  `gh pr create`) cuando el humano se lo pide en esa sesión.
- **Integración con merge commit**, desde GitHub y solo con el CI en verde.
  Nunca squash ni rebase and merge.
- Tras el merge: `git switch main && git pull` y borrar la rama local. La rama
  de GitHub se conserva.

## Ciclo de cada cambio (hitos y mejoras)
1. **Entender antes de escribir.** Leer el código que se va a tocar y la
   sección de DESIGN que lo explica. Si el cambio choca con una regla no
   negociable, decirlo antes de seguir.
2. **Spec.** Un hito o una mejora llevan spec en
   `docs/specs/hito-N-<slug>.md` o `docs/specs/mejora-AAAA-MM-DD-<slug>.md`,
   con el formato de `docs/specs/PLANTILLA.md`. Primera línea "Estado:
   PROPUESTA". Si cambia el alcance, DESIGN se corrige en el mismo commit que
   la spec, anotado en el sitio con fecha y spec. **No se escribe código hasta
   que el humano la aprueba** (pasa a APROBADA). *(Adaptado, DESIGN §15: la
   spec se propone en su propio PR, y integrarlo es la aprobación.)* Un arreglo
   no necesita spec: test que lo reproduce primero, y después el arreglo.
3. **Rama** `feature/<slug>` o `fix/<slug>`, desde `main`.
4. **Código y tests** en el orden de piezas de la spec, un commit por pieza,
   cada uno en verde. Lo que no viaja por git va a docs/PUESTA_EN_MARCHA.md en
   el mismo commit. Lo que necesita la release (una variable nueva, un paso
   manual) se anota en la spec y en "Para la release" de ESTADO.
5. **Evals**, si el cambio toca el comportamiento del agente (ver "Evals").
   Resultado anotado en la spec.
6. **Verificación a mano** en el puesto, con el entorno de desarrollo. Las
   herramientas con efecto se prueban en un directorio desechable.
7. **Cierre.**
   1. La spec pasa a IMPLEMENTADA, con su sección "Aprendido al implementar".
   2. Se escribe la nota del hito en docs/guia/, y se ponen al día las dos
      caras del proyecto: el `README.md` y el `README.es.md` (el producto:
      qué hace, cómo se instala y se usa) y `docs/PROYECTO.md` (cómo se
      hace y su hoja de ruta). *(Añadido el 2026-10-27, por decisión del mantenedor.)*
   3. Los PRs se integran con merge commit. La rama se borra en local y se
      conserva en GitHub.
   4. Se crea el tag y el humano hace push del tag.

   *(Adaptado, DESIGN §15.)*
8. **Release:** el push del tag dispara el workflow que crea la GitHub Release
   con sus notas.
9. **ESTADO al día**: lo hecho, la última versión y lo pendiente.

## Inicio de sesión (protocolo obligatorio)
Antes de tocar nada, en cada sesión y en cualquier máquina:
1. Leer este fichero completo.
2. Leer docs/ESTADO.md (fase actual, hito o cambio en curso, siguiente paso,
   pendientes).
3. Leer la sección de docs/DESIGN.md, y la spec si la hay, de lo que se vaya a
   tocar.
4. Ejecutar `git log --oneline -15` y `git status --short` para contrastar
   ESTADO.md con la realidad del repo. Si discrepan, avisar al humano antes de
   continuar; ESTADO.md se corrige, nunca se ignora.
5. Responder al humano con tres líneas: hito o cambio en curso (o ninguno, y
   la versión en producción), último cambio commiteado, siguiente paso
   concreto. Esperar confirmación.

Mantenimiento de docs/ESTADO.md:
- Se actualiza en el mismo commit que cierra un paso, o en commit propio al
  cerrar sesión. Nunca queda desactualizado más de una sesión.
- "Siguiente paso" es una acción concreta y ejecutable, con responsable
  (humano o agente), no un hito.
- ESTADO es corto: fase, siguiente paso, pendientes y versiones, y una
  línea por hito en "Hecho". El detalle de lo hecho va a
  docs/HISTORIAL_DESARROLLO.md, lo más reciente primero: al cerrar cada
  hito, su detalle pasa allí. *(Cambiado el 2026-10-27, por decisión del
  mantenedor; antes, el historial salía solo al cerrar la fase de
  desarrollo.)*

## Memoria y contexto (varios PCs, varios agentes)
- El humano trabaja este proyecto desde varios PCs sincronizados por git, y
  puede usar distintos agentes de código.
- TODO el contexto persistente (decisiones, estado del trabajo en curso,
  pendientes, convenciones nuevas, descubrimientos) se guarda en archivos del
  repo: este fichero para reglas y convenciones; docs/ para diseño, specs,
  decisiones y estado.
- Lo que dependa de la máquina y no viaje por git (variables de .env,
  migraciones por aplicar, servicios que levantar, logins) se anota en
  docs/PUESTA_EN_MARCHA.md EN EL MISMO COMMIT que lo introduce. Una variable
  nueva sin su línea ahí deja las otras máquinas rotas.
- Prohibido guardar contexto de proyecto en memoria local de la máquina o del
  agente (por ejemplo, la memoria automática de Claude Code en
  ~/.claude/projects/..., o cualquier otro sistema de memoria o fichero fuera
  del repo). Esa memoria no viaja con el pull a las otras máquinas.
- Al cerrar una sesión con cambios de estado o decisiones, actualizar
  docs/ESTADO.md (o el doc que corresponda) antes de terminar.
