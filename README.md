# maha

[![CI](https://github.com/ManexMartikorena/m-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/ManexMartikorena/m-harness/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/ManexMartikorena/m-harness)](https://github.com/ManexMartikorena/m-harness/releases)
[![Licencia: MIT](https://img.shields.io/badge/licencia-MIT-blue)](LICENSE)

**Un agente de IA para la terminal.** Le pides algo en lenguaje natural y
`maha` lee tu código, busca, escribe, edita y ejecuta comandos para
hacerlo, **preguntándote antes de cada cambio**. Funciona con el proveedor y
el modelo que elijas, y te dice en cada turno lo que ha costado.

> 🚧 **En desarrollo: `v0.7.0`.** Ya es usable para trabajar en un
> proyecto: conversar, leer y cambiar ficheros, ejecutar comandos, guardar y
> retomar sesiones, y ver el coste. Lo que viene, en la [hoja de
> ruta](#hoja-de-ruta).

```
$ maha
maha 0.7.0 · opencode-go · glm-5.3-flash · /help for commands
> Lee notas.txt con read_file y dime qué pone, en una frase.
  → read_file(path="notas.txt")
  ✓ 1 line
En notas.txt pone: "comprar pan".
  [tokens: 2542 in · 26 out · 1 call · $0.0004 · session $0.0004]
> Cambia la segunda línea de notas.txt por 'tres' con edit_file.
  → edit_file(new_string="tres", old_string="dos", path="notas.txt")
  ┌ edit notas.txt
  │ @@ -1,2 +1,2 @@
  │  uno
  │ -dos
  │ +tres
  └ Allow? [y] yes · [a] always this session · [n] no: y
  ✓ 1 replacement
```

## Qué hace

- **Trabaja en tu proyecto.** Lee, lista y busca ficheros (`read_file`,
  `list_dir`, `glob`, `grep`, respetando `.gitignore`), los escribe y edita
  (`write_file`, `edit_file`, con el diff a la vista) y ejecuta comandos
  (`run_command`).
- **Nada cambia sin tu permiso.** Cada escritura y cada comando te preguntan
  antes: una vez, siempre en esta sesión, o no. Leer fuera del directorio o
  un fichero secreto (`.env`, claves, `.ssh`…) también pregunta. Los
  comandos no reciben tu clave del proveedor.
- **El modelo y el proveedor que quieras.** Formato de OpenAI de serie, con
  OpenCode Go y Zen ya configurados, y cualquier servidor compatible que
  declares. Cambias de modelo con `/model` o en la configuración.
- **Sesiones que no se pierden.** Cada conversación se guarda sola, turno a
  turno, y se retoma desde cualquier directorio.
- **Sabes lo que gastas.** Cada turno dice sus tokens y su coste, y la
  sesión lo que lleva. Con OpenCode Go, lo que cuenta contra tu límite
  mensual.
- **Todo queda registrado, sin tus secretos.** Cada sesión deja una traza
  de lo que hizo el agente; `/trace` la resume.

## Instalación

Necesitas [uv](https://docs.astral.sh/uv/) (instala también Python 3.14 si
falta).

```
uv tool install git+https://github.com/ManexMartikorena/m-harness@v0.7.0
```

Después, elige proveedor y modelo:

```toml
# ~/.config/maha/config.toml
provider = "opencode-go"   # o "opencode-zen"
model = "glm-5.3-flash"
```

y deja la clave en una variable de entorno:

```
export OPENCODE_API_KEY=...
maha
```

`maha` trabaja sobre el directorio donde lo abres.

### Otro proveedor

Cualquier servidor con el formato de OpenAI, declarado en tu configuración:

```toml
# ~/.config/maha/config.toml
provider = "local"
model = "el-id-de-tu-modelo"

[providers.local]
base_url = "http://localhost:11434/v1"
# api_key_env = "MI_CLAVE"   # sin ella, no se envía clave
```

Un proyecto puede elegir su proveedor y modelo en `.maha/config.toml`, pero
nunca declarar proveedores: así un repositorio ajeno no puede llevarse tu
clave a otro servidor.

## Uso

| Comando | Qué hace |
|---|---|
| `/help` | Lista los comandos |
| `/model [ID]` | Enseña el modelo, o lo cambia |
| `/sessions` | Las sesiones recientes, de todos los directorios |
| `/resume [ID]` | Retoma una sesión; sin ID, la última de este directorio |
| `/delete ID` | Borra una sesión y su traza |
| `/trace [ID]` | Lo que hizo y costó una sesión, turno a turno |
| `/exit` | Sale (también Ctrl+D) |

- **Ctrl+C** a mitad de una respuesta la corta y vuelve al prompt; el
  modelo sabe que la cortaste. En el prompt, sale.
- **Sin terminal** (`maha < instrucciones.txt`), todo lo que tiene efecto
  se deniega.

### Dónde guarda cada cosa

| Qué | Dónde |
|---|---|
| Configuración | `~/.config/maha/config.toml` |
| Precios propios (opcional) | `~/.config/maha/models.toml` |
| Sesiones | `~/.local/share/maha/sessions/` |
| Trazas | `~/.local/share/maha/traces/` |
| Registro de diagnóstico | `~/.local/state/maha/maha.log` |

Todo es local. Las sesiones, las trazas y el registro solo los puede leer
tu usuario. Respeta las variables `XDG_*`.

## Hoja de ruta

`maha` crece hito a hito hasta la versión 1.0. Lo siguiente:

- **Modo no interactivo y evals:** `maha -p "…"` para scripts, retomar al
  arrancar, salida JSON, topes de coste, `maha stats`.
- **Más proveedores:** formato de Anthropic, esfuerzo de razonamiento.
- **Instrucciones del proyecto** (`AGENTS.md`, `/init`), compactación del
  contexto y **deshacer** cambios.
- **Skills y comandos propios, memoria entre sesiones, sandbox, modos de
  permiso, subagentes, MCP y hooks.**
- **Web e imágenes.**
- **Una interfaz a pantalla completa**, con menú de comandos y navegación
  sencilla.
- **La 1.0**, instalable para cualquier usuario y con su documentación.

El plan completo, hito a hito: [el proyecto](docs/PROYECTO.md#hoja-de-ruta).

## El proyecto

`maha` se construye desde cero y a la vista: sin frameworks de agentes, cada
pieza en su propio PR, con su spec, sus tests y una nota que explica el
concepto. Si quieres saber cómo funciona un agente por dentro, o construir
el tuyo, empieza por **[cómo se ha hecho](docs/PROYECTO.md)**.

## Licencia

[MIT](LICENSE)
