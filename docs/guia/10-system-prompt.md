# 10. El system prompt: lo que el modelo sabe antes de leerte

Hito 10 (`v0.10.0`). Spec: `docs/specs/hito-10-system-prompt.md`.
Diseño: `docs/DESIGN.md` §4, §5, §8 y §14.

## El problema

Hasta el hito 9, el modelo recibía la conversación y la lista de
herramientas, y nada más. No sabía:

- **quién es** ni cómo se trabaja bien con código (leer antes de cambiar,
  no adivinar rutas, parar al terminar);
- **dónde trabaja:** qué directorio, si es un repo git, qué día es;
- **las reglas del proyecto:** con qué se lanzan los tests, qué no tocar.

Eso va en el system prompt. Y como un agente reenvía todo en cada paso,
tiene que ser estable, para que el proveedor lo sirva desde la caché.

## Cómo lo resuelve M-Harness

### 1. Qué es el system prompt

- *System prompt:* el texto que el modelo lee antes de la conversación. No
  es un mensaje más: cada API lo pone en su sitio (OpenAI, un mensaje
  `system`; Anthropic, el campo `system`; guía 09).

```json
{"model": "glm-5.3-flash",
 "messages": [{"role": "system", "content": "You are maha, a coding agent…"},
              {"role": "user", "content": "Arregla el IVA reducido"}]}
```

### 2. Las capas, de la más fija a la más variable

| # | Capa | De dónde sale |
|---|---|---|
| 1 | Base | `src/mharness/prompts/base.md` (o el fichero de la persona) |
| 1b | Familia | `prompts/families/<familia>.md`, si existe |
| 2 | Usuario | `~/.config/maha/AGENTS.md` |
| 3 | Proyecto | los `AGENTS.md` de la raíz git al directorio actual |
| 4 | Extra | `instructions` de `config.toml` |
| 5 | Entorno | directorio, raíz git, plataforma, shell y fecha |

- **Por qué en ese orden:** la caché compara el principio exacto de la
  petición. Lo que menos cambia va primero, y así todas las sesiones
  comparten la base en la caché.
- **Se construye una vez por sesión** (al arrancar, con `/new` y con
  `/resume`). Un `AGENTS.md` editado a mitad de sesión cuenta desde
  `/new`, y `maha` lo dice.
- **Capas de familia:** el mecanismo está, pero sin ficheros. Una capa solo
  entra si las evals muestran un fallo propio de esa familia, y no lo
  hubo: el único patrón era de la base, y se arregló en la base.

`maha prompt` enseña el prompt de una sesión en ese directorio, sin llamar
al modelo:

```
$ maha prompt
  [instructions: AGENTS.md]
You are maha, a coding agent that works in the user's terminal. …
<instructions source="AGENTS.md">
Los tests se lanzan con `uv run pytest`.
</instructions>
<environment>
Working directory: /home/ana/tienda
Git repository: yes, root /home/ana/tienda
…
```

### 3. `AGENTS.md`: instrucciones del proyecto, nunca permisos

- *`AGENTS.md`:* un fichero de texto en el repo con lo que un agente
  necesita saber: comandos, convenciones, trampas. Es un estándar abierto
  que leen Codex, OpenCode y otros. `maha` lee también `CLAUDE.md` donde
  no hay `AGENTS.md`.
- **Van delimitadas, con su origen**, y al arrancar se dice cuáles se han
  cargado: nada entra en el prompt sin verse.
- **No tocan permisos ni herramientas.** Un `AGENTS.md` de un repositorio
  ajeno puede pedir cualquier cosa; los permisos son código (guía 05).

`/init` escribe o mejora el `AGENTS.md` del proyecto: el agente mira el
repo con sus herramientas, pide permiso y escribe. En una subcarpeta,
escribe el `AGENTS.md` de esa carpeta, que se carga junto al de la raíz
(desde la `v0.10.1`).

```
> /init los tests se lanzan con unittest, nunca con pytest
  ┌ create AGENTS.md (49 lines)
  └ Allow? [y] yes · [a] always this session · [n] no: y
  [AGENTS.md takes effect in the next session: /new]
```

### 4. Dos herramientas para trabajar con la persona

- **`todo_write`:** el modelo lleva una lista de tareas en el trabajo de
  varios cambios, y la terminal la pinta:

  ```
    ☑ Renombrar precio_final
    ▸ Añadir el test del envío gratis
    ☐ Actualizar el README
  ```

  La primera guía hizo que Kimi abriera listas para cambios de una línea
  (+12 % de pasos). Se reescribió mirando solo las tareas de train, y
  ahora la lista aparece en el trabajo largo y se cierra al terminar.
- **`ask_user`:** el modelo pregunta con opciones, y siempre hay "Other"
  para escribir otra cosa. Solo existe si hay alguien que responda: en
  `-p` y en las evals no se registra, y el modelo no pierde un paso
  preguntando a nadie. Mientras la persona lee, el reloj del turno se para.

### 5. Títulos de sesión

Tras el primer turno, un modelo barato (`small_model`) titula la sesión en
segundo plano, sin hacer esperar a nadie:

```
20261110-145743-483d  2026-11-10 15:57  2 messages  ~/demo  Multiplicación de 17 por 23
```

Su coste cuenta en la sesión, en `/trace` y en `maha stats`. `/rename`
pone uno a mano, que el automático nunca pisa.

### 6. Los prompts son código

- Viven en el repo (`src/mharness/prompts/`), con huecos `{{nombre}}` que
  se rellenan de forma estricta: un hueco sin valor es un error, no un
  prompt roto.
- Se revisan en un PR y **se miden con evals**. La traza y la línea base
  guardan la huella del prompt, y el informe avisa si cambió.
- Medido en este hito: el prompt subió el coste por ejecución (GLM +78 %,
  Haiku +48 %), la mayor parte desde la caché, sin bajar el éxito. La
  tarea 24 mide `/init` tal como lo teclea la persona: 15/15.

## En la industria

- **Claude Code:** un system prompt fijo y `CLAUDE.md` como mensaje del
  usuario; `--system-prompt` y `--append-system-prompt`; `TodoWrite` y
  `AskUserQuestion`; `/init`.
- **OpenCode:** base + entorno + `AGENTS.md`, con un prompt por familia de
  modelo; `todowrite`; títulos con `small_model`.
- **Codex:** junta los `AGENTS.md` de la raíz git al directorio actual,
  con un tope de bytes.
- **Frameworks:** plantillas Jinja2 y prompts versionados en Langfuse o
  LangSmith. Aquí, plantillas propias de pocas líneas (DESIGN §7.1).
