Estado: PROPUESTA (2026-10-19) → APROBADA (2026-10-19, por el humano, sin cambios) → IMPLEMENTADA (2026-10-20)

# Spec — Hito 1: Esqueleto

Referencias: `docs/DESIGN.md` §3 (arquitectura), §7 (stack), §12 (tests y
CI), §13 (distribución), §14 (hito 1) y §15 (flujo de GitHub); `AGENTS.md`
(reglas no negociables).

## 0. Alcance

**El problema.** Todavía no hay código. Sin una base (paquete, capas, calidad
automática y CI), cada hito tendría que inventarla, y una regla de
arquitectura rota entraría en `main` sin que nadie lo viera.

**Lo que hace este cambio.** Deja un paquete Python instalable con el comando
`maha`, que de momento solo responde a `maha --version`. Crea las cuatro
capas vacías, con sus reglas de dependencia comprobadas por máquina. Y pone
en marcha la calidad automática: lint, tipos, tests, escaneo de secretos, CI
en cada PR y una release por cada tag.

Dentro de alcance:
- `pyproject.toml` con uv, `uv.lock` y `.python-version`.
- Paquete `mharness`: las capas `domain`, `ports`, `application` y
  `adapters` vacías, `bootstrap.py` y el adaptador `cli`.
- `maha --version`, `maha` sin argumentos (muestra la ayuda) y
  `python -m mharness`.
- ruff, mypy estricto, pytest + pytest-asyncio e import-linter.
- Un test de arquitectura: el núcleo solo usa la biblioteca estándar y
  Pydantic.
- pre-commit con ruff y gitleaks.
- CI en GitHub Actions con Python 3.14 y 3.15, más gitleaks.
- Workflow de release al hacer push de un tag `v*`.
- Nota 01 de la guía. `MAPA`, `PUESTA_EN_MARCHA`, `ESTADO` y `README` al
  día.

**Fuera de alcance** (y por qué):
- Tipos del dominio, puertos, configuración y `.env.example`: hito 2, cuando
  hay algo que tipar y configurar.
- Dependencias de ejecución (Pydantic, httpx, Rich…): cada una llega con la
  pieza que la usa, desde el hito 2.
- respx y `tests/fakes/`: hito 2, con el primer adaptador HTTP.
- Windows nativo y macOS: la plataforma es Linux, y en Windows se trabaja
  con WSL2 (ANALISIS §7). Ver §1.14.
- Ficheros adjuntos a la release (wheel) y PyPI: fuera de v1 (DESIGN §13).
- Actualización automática de versiones (Dependabot version updates,
  Renovate): se valora cuando haya dependencias de ejecución.

## 1. Decisiones de fondo

### 1.1 Versiones comprobadas hoy

Comprobadas el 2026-10-19 en PyPI, python.org y las releases de GitHub de
cada proyecto.

| Herramienta | Versión | Publicada |
|---|---|---|
| uv y `uv_build` | 0.13.1 | 2026-10-14 |
| Python | 3.14.8 · 3.15.0 | 2026-09-30 · 2026-10-09 |
| ruff | 0.17.1 | 2026-10-15 |
| mypy | 2.4.0 | 2026-10-01 |
| pytest | 9.1.1 | 2026-06-19 |
| pytest-asyncio | 1.4.0 | 2026-05-26 |
| import-linter | 2.15 | 2026-09-04 |
| pre-commit | 4.7.0 | 2026-10-12 |
| pre-commit-hooks | 6.0.0 | 2025-08-09 |
| gitleaks | 8.30.1 | 2026-03-21 |
| actions/checkout | 7.0.1 | 2026-07-20 |
| astral-sh/setup-uv | 10.3.0 | 2026-10-09 |
| gitleaks/gitleaks-action | 3.0.0 | 2026-05-30 |

- **Política:** en `pyproject.toml`, cota inferior (`>=` la versión
  comprobada); la versión exacta la fija `uv.lock`. Subir versiones es un
  cambio aparte (`uv lock --upgrade`), con su propio commit.
- **Hace falta uv 0.13.** Es la primera versión que trae Python 3.15.0, y
  pasa a usar 3.15 por defecto. En este PC había uv 0.12.17 (el mantenedor
  lo actualizó a 0.13.1 el 2026-10-19). Con
  `[tool.uv] required-version = ">=0.13.1"`, un uv viejo falla con un mensaje
  claro en lugar de comportarse distinto.

### 1.2 Python de desarrollo: 3.14

`.python-version` con `3.14` y `requires-python = ">=3.14"`.

- **Por qué:** DESIGN §7 desarrolla en 3.14, y uv 0.13 usaría 3.15 si no se
  fija. El CI prueba las dos.

### 1.3 Backend de construcción: `uv_build`

`uv_build>=0.13.1,<0.14`, con `module-name = "mharness"`. Sin esa línea, uv
buscaría el módulo `m_harness`, que deduce del nombre de la distribución.

- **Por qué:** es el backend de uv, sin configuración extra, y sirve para
  Python puro, que es nuestro caso.
- **Descartados:** hatchling (más flexible, no hace falta) y setuptools (más
  antiguo y con más configuración).

*Backend de construcción:* el programa que convierte el código en un paquete
instalable (wheel).

### 1.4 La versión vive en un solo sitio: `pyproject.toml`

- Nace en `0.0.0`. El último commit de implementación de cada hito la sube
  con `uv version --bump minor` (hito 1 → `0.1.0`).
- `maha --version` la lee de los metadatos del paquete instalado
  (`importlib.metadata`).
- Un test comprueba que coincide con `pyproject.toml`. El workflow de release
  comprueba que coincide con el tag.
- **Descartado:** sacar la versión de los tags de git (setuptools-scm,
  hatch-vcs). Es habitual, pero exige otro backend, y la versión deja de
  verse en el diff que se revisa.

### 1.5 El comando entra por la raíz de composición

`maha` → `mharness.bootstrap:main` → adaptador `cli`. `python -m mharness`
hace lo mismo.

```python
# bootstrap.py (hito 1: todavía no hay nada que cablear)
def main(argv: Sequence[str] | None = None) -> int:
    return cli.run(argv)
```

- **Por qué:** `bootstrap.py` es el único módulo que conoce todas las piezas
  (DESIGN §3). Si el comando entrara directamente por `cli`, el cableado
  acabaría dentro de un adaptador.

*Raíz de composición (composition root, Mark Seemann):* el punto, junto a la
entrada del programa, donde se crean las piezas y se conectan entre sí.

### 1.6 Textos de la interfaz en inglés

Propuesta del agente.

- **Por qué:** el código está en inglés, y los mensajes propios de argparse
  ("usage:", "error:") también. Mezclar idiomas en la terminal queda raro.
- Traducir la interfaz queda fuera de v1. La documentación sigue en español.

### 1.7 Reglas de capas con import-linter

```toml
[[tool.importlinter.contracts]]
name = "Hexagonal layers"
type = "layers"
containers = ["mharness"]
layers = ["__main__", "bootstrap", "adapters", "application", "ports", "domain"]
exhaustive = true

[[tool.importlinter.contracts]]
name = "Adapters are independent"
type = "independence"
modules = ["mharness.adapters.*"]
```

- **`layers`:** una capa solo importa las que tiene debajo. Cubre las reglas
  de `domain`, `ports`, `application` y `bootstrap` (AGENTS.md).
- **`exhaustive`:** todo módulo nuevo directamente bajo `mharness` tiene que
  estar en la lista. Así, `config.py` (hito 2) obliga a decidir su capa.
- **`independence` con comodín:** cada adaptador nuevo (`adapters/models`,
  `adapters/tools`…) queda cubierto sin tocar la configuración.
- **Probado** el 2026-10-19 en un directorio desechable con import-linter
  2.15. Detecta `domain → adapters`, un módulo sin capa y un adaptador que
  importa a otro.

*Contrato:* una regla de import-linter sobre quién puede importar a quién.
Se comprueba con `uv run lint-imports`.

### 1.8 Test de arquitectura: el núcleo no usa librerías externas

import-linter mira los imports entre módulos del proyecto. Para librerías
externas solo admite listas negras, y la regla de AGENTS es una lista blanca:
`domain` usa solo la biblioteca estándar y Pydantic.

- **Qué:** `tests/architecture/test_core_imports.py` lee con `ast` los
  imports de `domain`, `ports` y `application`. Falla si alguno no está en
  `sys.stdlib_module_names`, ni es `pydantic`, ni es `mharness`.
- **Por qué también `ports` y `application`:** todo contacto con el exterior
  va detrás de un puerto. Si `application` importa httpx, se ha saltado un
  puerto. Ampliar la lista exige cambiar el test, y eso se ve en la revisión.
- **Ejemplo de fallo:** `import httpx` en `domain/messages.py` →
  `mharness.domain.messages imports httpx`.

### 1.9 Calidad: ruff, mypy y pytest

- **ruff:**
  - reglas `E`, `W`, `F` (pycodestyle y pyflakes), `I` (orden de imports),
    `B` (bugbear), `UP` (sintaxis moderna), `SIM` (simplificaciones),
    `ASYNC` (errores típicos de asyncio), `PT` (estilo de pytest) y `RUF`
    (propias de ruff);
  - `target-version = "py314"` y longitud de línea 88, la de por defecto.
- **mypy:** `strict = true` sobre `src` y `tests`.
  - Por qué los tests: en el hito 2 los fakes (`FakeModelClient`) tienen que
    cumplir los mismos `Protocol` que los adaptadores reales, y mypy solo lo
    comprueba si mira los tests.
  - El comando pasa a ser `uv run mypy`, que lee los directorios de la
    configuración. Se corrige en `AGENTS.md` y en `PUESTA_EN_MARCHA.md`.
- **pytest**, en `[tool.pytest]` (formato TOML nativo desde pytest 9):
  - `asyncio_mode = "auto"`: todo test `async def` corre con asyncio sin
    marcarlo. Solo se usa asyncio, así que el modo estricto no aporta nada;
  - `--strict-markers` y `--strict-config`: un marcador o una opción mal
    escritos son un error;
  - `filterwarnings = ["error"]`: un aviso (por ejemplo, de una función
    obsoleta) rompe los tests. Así nos enteramos al subir versiones o con
    Python 3.15;
  - las carpetas de tests son paquetes (`__init__.py`): permite
    `from tests.fakes import …` en el hito 2 y nombres de fichero repetidos.
  - Probado el 2026-10-19 con pytest 9.1.1 y pytest-asyncio 1.4.0.

### 1.10 pre-commit

*pre-commit:* programa que ejecuta comprobaciones (hooks) antes de cada
`git commit` y lo para si alguna falla.

- **ruff** (`check --fix` y `format`), como hooks locales que llaman a
  `uv run`. Así hay una sola versión de ruff, la del lockfile.
  - Descartado: el repo `ruff-pre-commit`, que obliga a mantener la versión
    en dos sitios.
- **gitleaks**, con el hook oficial (`id: gitleaks`, v8.30.1). Es un programa
  en Go, y pre-commit (desde la 3.0) descarga Go y lo compila la primera vez.
  No hay que instalar nada a mano.
- **`check-yaml`, `check-toml` y `check-added-large-files`**
  (pre-commit-hooks v6.0.0): un workflow o un `pyproject.toml` rotos no llegan
  al commit.
- **mypy, import-linter y pytest no van en pre-commit:** tardan más y los
  pasa el CI. El agente los ejecuta antes de cada commit (AGENTS.md).

### 1.11 CI

`.github/workflows/ci.yml`:

- **Cuándo:** en cada PR (también en cada push a una rama con PR abierto),
  en cada push a `main` y a mano (`workflow_dispatch`).
  - DESIGN §12 decía "en cada push y PR"; se corrige en el mismo commit que
    esta spec. Todo entra por PR, así que no se pierde nada y no se
    duplican ejecuciones.
- **Job `checks`:** Ubuntu 26.04 (`runs-on: ubuntu-26.04`), con Python 3.14
  y 3.15 en matriz. Pasos: `uv sync --locked` → `ruff check` →
  `ruff format --check` → `mypy` → `lint-imports` → `pytest`.
  - `--locked` falla si `uv.lock` no está al día con `pyproject.toml`.
  - Por qué no `ubuntu-latest`: hoy apunta a 24.04 y cambia sin avisar. Con
    la versión explícita, el CI usa la misma Ubuntu que el puesto de
    desarrollo (§1.14), y cambiarla es un commit visible.
- **Job `secrets`:** gitleaks-action sobre todo el historial
  (`fetch-depth: 0`). Es gratis en cuentas personales; en una organización
  pediría licencia.
- **Permisos mínimos** (`contents: read`) y cancelación de ejecuciones viejas
  de la misma rama.
- **Acciones fijadas por hash de commit**, con la versión en un comentario:

  ```yaml
  - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
  ```

  - Por qué: un tag de una acción se puede mover y un hash no. Es lo que
    recomienda GitHub para repositorios públicos. En marzo de 2025 se
    comprometió la acción `tj-actions/changed-files` moviendo sus tags.

### 1.12 Release

`.github/workflows/release.yml`, al hacer push de un tag `v*`:

1. Comprueba que el tag coincide con la versión: `v$(uv version --short)`
   tiene que ser igual al tag.
2. Crea la release con `gh release create`. `gh` ya viene en los runners de
   GitHub, así que no hace falta otra acción de terceros.
   - Título: la primera línea del mensaje del tag anotado.
   - Notas: el resto del mensaje del tag y, debajo, la lista de PRs que
     genera GitHub (`--generate-notes`).
   - `--notes-from-tag` y `--generate-notes` no se pueden combinar en gh
     2.101 (comprobado en su código). Por eso el mensaje del tag se lee con
     git y se pasa con `--notes`.
3. Permiso `contents: write`, solo en este workflow.

```
git tag -a v0.1.0 -m "v0.1.0 — Esqueleto" -m "Paquete, capas, calidad automática, CI y release."
```

### 1.13 Dos PRs de implementación

- **PR 1:** el proyecto, las capas, `maha --version`, la calidad y el CI.
- **PR 2:** la release y el cierre del hito.
- **Por qué:** cada uno se revisa de una sentada, y el PR 1 ya pasa por su
  propio CI.

### 1.14 Plataforma: Linux, también en este PC

Hoy este PC trabaja en Windows nativo, y `PUESTA_EN_MARCHA` §1 pide WSL2. El
mantenedor delegó la decisión en el agente (2026-10-19). La decisión es
aplicar lo que ya fija ANALISIS §7: **Linux, y en Windows, WSL2.**

- **Puesto de desarrollo:** Ubuntu 26.04 LTS, la misma versión que el CI. En
  Windows, dentro de WSL2 (`wsl --install -d Ubuntu-26.04`), con el repo
  clonado en `~/` y el agente de código ejecutándose también dentro de WSL.
  Así, los comandos que lanza el agente son los de Linux.
- **CI:** solo Linux (§1.11). Sin job de Windows.
- **Windows nativo no es una plataforma soportada en v1.** Soportarlo sería
  un cambio de alcance (ANALISIS y DESIGN), y choca con dos hitos:
  - la terminal del agente (hito 5) ejecuta comandos de shell, distintos en
    PowerShell;
  - el sandbox (hito 14) se apoya en el aislamiento del sistema operativo, y
    las opciones de DESIGN §7.1 (bubblewrap, Landlock, contenedores) son de
    Linux.
- **Descartado:** añadir un job de Windows al CI. Probaría una plataforma que
  no se soporta, y cada fallo propio de Windows costaría tiempo sin acercar
  la v1.
- **En este PC** solo hay la distribución `docker-desktop` en WSL2
  (comprobado el 2026-10-19). Falta instalar Ubuntu 26.04. Ver §8.

## 2. En la industria

| Pieza | M-Harness | Alternativas | Cuándo se elegirían |
|---|---|---|---|
| Entorno y dependencias | uv | Poetry, PDM, Hatch; pip + venv | Poetry o PDM: proyectos que ya los usan. Hatch: matrices de entornos. pip: sin herramientas extra |
| Backend de construcción | `uv_build` | hatchling, setuptools, flit-core | setuptools: extensiones en C. hatchling: plugins |
| Lint y formato | ruff | black + flake8 + isort | Proyectos antiguos ya configurados |
| Tipos | mypy | pyright y basedpyright, ty (Astral), pyrefly (Meta) | pyright: integración con VS Code. ty y pyrefly: mucho más rápidos; ty sigue en 0.0.x |
| Reglas de arquitectura | import-linter | tach, pytestarch | tach: módulos con interfaz pública declarada. pytestarch: reglas escritas como tests |
| Hooks de git | pre-commit | lefthook, husky (JavaScript) | lefthook: repos con varios lenguajes y más velocidad |
| Secretos | gitleaks | trufflehog, detect-secrets, secret scanning de GitHub | trufflehog: comprueba si la clave sigue viva. detect-secrets: línea base de falsos positivos |
| Versión | estática en `pyproject.toml` | setuptools-scm, hatch-vcs | Cuando se publica a menudo y no se quiere tocar el fichero |
| CI | GitHub Actions | GitLab CI, CircleCI | Según dónde esté el repositorio |
| Releases | `gh` + notas generadas | release-please, semantic-release, softprops/action-gh-release | release-please: versión y changelog automáticos a partir de commits con formato Conventional Commits |

*Nombres comprobados en PyPI y GitHub el 2026-10-19.*

## 3. Diseño de detalle

### 3.1 Ficheros

```
m-harness/
├── pyproject.toml            # metadatos, dependencias de desarrollo y configuración de las herramientas
├── uv.lock                   # versiones exactas (lo genera uv)
├── .python-version           # 3.14
├── .pre-commit-config.yaml
├── .github/workflows/
│   ├── ci.yml
│   └── release.yml
├── src/mharness/
│   ├── __init__.py           # docstring: qué es el paquete
│   ├── __main__.py           # python -m mharness
│   ├── bootstrap.py          # raíz de composición: main() del comando maha
│   ├── domain/__init__.py    # capas vacías: un docstring con la regla de la capa
│   ├── ports/__init__.py
│   ├── application/__init__.py
│   └── adapters/
│       ├── __init__.py
│       └── cli/
│           ├── __init__.py
│           └── app.py        # argparse: --version y ayuda
└── tests/
    ├── __init__.py
    ├── test_entry_point.py
    ├── adapters/             # __init__.py, test_cli.py
    └── architecture/         # __init__.py, test_core_imports.py
```

`tests/unit/` y `tests/fakes/` nacen en el hito 2.

### 3.2 `pyproject.toml`, lo esencial

```toml
[project]
name = "m-harness"
version = "0.0.0"
description = "Agente de terminal de propósito general, construido desde cero."
readme = "README.md"
license = "MIT"
license-files = ["LICENSE"]
authors = [{ name = "Manex Martikorena" }]
requires-python = ">=3.14"
dependencies = []

[project.scripts]
maha = "mharness.bootstrap:main"

[dependency-groups]
dev = [
    "import-linter>=2.15",
    "mypy>=2.4.0",
    "pre-commit>=4.7.0",
    "pytest>=9.1.1",
    "pytest-asyncio>=1.4.0",
    "ruff>=0.17.1",
]

[build-system]
requires = ["uv_build>=0.13.1,<0.14"]
build-backend = "uv_build"

[tool.uv]
required-version = ">=0.13.1"

[tool.uv.build-backend]
module-name = "mharness"
```

Más `[tool.ruff]`, `[tool.mypy]`, `[tool.pytest]` y `[tool.importlinter]`,
según §1.7 y §1.9.

*Grupo de dependencias (`dependency-groups`, PEP 735):* dependencias que solo
hacen falta para desarrollar. `uv sync` instala el grupo `dev` por defecto, y
no viajan con el paquete instalado.

### 3.3 Comportamiento de `maha`

| Orden | Salida | Código de salida |
|---|---|---|
| `maha --version` | `maha 0.1.0` | 0 |
| `maha` | la ayuda (uso y opciones) | 0 |
| `maha --nope` | uso y error en stderr | 2 (convención de argparse) |
| `python -m mharness --version` | igual que `maha --version` | 0 |

### 3.4 Configuración nueva

Ninguna: ni variables de entorno ni fichero de configuración.

## 4. Plan de tests

Sin llamadas reales ni red.

1. `tests/adapters/test_cli.py`:
   1. `--version` imprime `maha <versión>` y sale con 0.
   2. Esa versión es la de `pyproject.toml`, leída con `tomllib`. Fija la
      decisión 1.4.
   3. Sin argumentos, imprime la ayuda y devuelve 0.
   4. Una opción desconocida sale con 2 y escribe el error en stderr.
2. `tests/test_entry_point.py`:
   1. El script `maha` de los metadatos apunta a `mharness.bootstrap:main`.
      Fija la decisión 1.5.
   2. `python -m mharness --version`, en un subproceso, imprime la versión.
      Comprueba el paquete instalado de verdad.
3. `tests/architecture/test_core_imports.py`:
   1. `domain`, `ports` y `application` solo importan la biblioteca estándar,
      `pydantic` y `mharness`. Fija la decisión 1.8.
   2. La función que extrae los imports detecta uno prohibido en un trozo de
      código de ejemplo, sin tocar `src`. Así se sabe que el test 3.1 no pasa
      por no mirar nada.
4. import-linter (no es pytest; corre en el CI): los contratos de §1.7.

## 5. Evals

No aplica: este hito no tiene comportamiento del agente. Las evals nacen en el
hito 8.

## 6. Orden de piezas para el implementador

Cada punto es un commit, con lo que exista hasta ese momento (tests, lint,
tipos, contratos) en verde.

**PR 1** (`feature/hito-1-esqueleto`)
1. **Proyecto uv.** `pyproject.toml` (metadatos, `uv_build`,
   `required-version`, versión 0.0.0), `.python-version`, `uv.lock` y
   `src/mharness/__init__.py`. En `PUESTA_EN_MARCHA`: uv ≥ 0.13.1.
   *Commit:* "Crear el proyecto Python con uv"
2. **ruff.** Grupo `dev` con ruff y su configuración.
   *Commit:* "Añadir ruff para lint y formato"
3. **mypy.** Modo estricto sobre `src` y `tests`; el comando `uv run mypy`,
   en `AGENTS` y `PUESTA_EN_MARCHA`.
   *Commit:* "Añadir mypy en modo estricto"
4. **Capas.** `domain`, `ports`, `application` y `adapters`, cada una con su
   docstring; import-linter y sus dos contratos.
   *Commit:* "Crear las capas hexagonales con sus reglas de dependencia"
5. **pytest y test de arquitectura.** pytest y pytest-asyncio con su
   configuración, y `tests/architecture/test_core_imports.py`. Van juntos
   porque pytest sin tests termina con error.
   *Commit:* "Comprobar que el núcleo solo usa la biblioteca estándar y Pydantic"
6. **Adaptador `cli`.** `adapters/cli/app.py` con `--version` y la ayuda;
   tests 1.1 a 1.4.
   *Commit:* "Añadir la opción --version al adaptador de terminal"
7. **Punto de entrada.** `bootstrap.py`, `__main__.py` y `[project.scripts]`;
   tests 2.1 y 2.2.
   *Commit:* "Conectar el comando maha a la raíz de composición"
8. **pre-commit.** `.pre-commit-config.yaml` y pre-commit en `dev`. En
   `PUESTA_EN_MARCHA`: `pre-commit install` y la primera descarga de Go.
   *Commit:* "Añadir los hooks de pre-commit con ruff y gitleaks"
9. **CI.** `.github/workflows/ci.yml`.
   *Commit:* "Añadir el CI de GitHub Actions"
10. **Mapa.** `docs/MAPA.md` con los ficheros del PR.
    *Commit:* "Actualizar el mapa con el esqueleto"

**Tras integrar el PR 1** (humano): añadir al ruleset "main protegida" los
checks obligatorios `checks (3.14)`, `checks (3.15)` y `secrets`. Así el
PR 2 ya pasa por ellos. *(Antes se preveía al cerrar el hito.)*

**PR 2** (`feature/hito-1-release`)

11. **Release.** `.github/workflows/release.yml`.
    *Commit:* "Añadir el workflow de release"
12. **Versión.** `uv version --bump minor` → `0.1.0`.
    *Commit:* "Subir la versión a 0.1.0"
13. **Guía.** `docs/guia/01-arquitectura-hexagonal.md` y su fila en el
    índice.
    *Commit:* "Añadir la nota de la guía sobre la arquitectura hexagonal"
14. **Cierre de la spec.** Estado IMPLEMENTADA y "Aprendido al implementar".
    *Commit:* "Cerrar la spec del hito 1"
15. **Documentación al día.** README (hito 1 hecho e insignia del CI), MAPA y
    ESTADO.
    *Commit:* "Actualizar la documentación al cerrar el hito 1"

**Tras integrar el PR 2:** el agente crea el tag anotado `v0.1.0` sobre el
merge commit de `main`; el humano hace push del tag, que dispara la release.

## 7. Verificación a mano

1. Clon limpio en un directorio desechable: `uv sync` instala Python 3.14 si
   falta y crea `.venv`.
2. `uv run maha --version` → `maha 0.0.0` en el PR 1 y `maha 0.1.0` en el
   PR 2. `uv run maha` → la ayuda. `uv run maha --nope` → código 2.
3. `uv run python -m mharness --version` → lo mismo que el punto 2.
4. Los cuatro comandos de `PUESTA_EN_MARCHA` §4, en verde.
5. Romper una regla a propósito, sin commitear: añadir
   `from mharness.adapters import cli` en `domain/__init__.py`, ver fallar
   `uv run lint-imports` y deshacerlo.
6. gitleaks, en un repo git desechable con la misma configuración de
   pre-commit: un fichero con un token inventado con formato de token de
   GitHub (`ghp_` + 36 caracteres) → el commit se bloquea.
7. Instalación como herramienta: `uv tool install .` → `maha --version` desde
   otro directorio → `uv tool uninstall m-harness`. Tras el tag:
   `uv tool install git+https://github.com/ManexMartikorena/m-harness@v0.1.0`.
8. En GitHub: el PR 1 muestra `checks (3.14)`, `checks (3.15)` y `secrets` en
   verde. Tras el push del tag, la release aparece con su título y sus notas.

## 8. Lo que no viaja por git y lo que necesita la release

- **Este PC, antes del PR 1** (humano): instalar Ubuntu 26.04 en WSL2,
  clonar el repo en `~/` e instalar ahí git, gh (con su login), uv y el
  agente de código (§1.14). La implementación se hace desde ese clon. El
  clon de Windows deja de usarse. Va a `PUESTA_EN_MARCHA` §1 y §6 en el
  mismo commit que esta decisión.
- **uv ≥ 0.13.1 en cada máquina:** `uv self update`, o el método con que se
  instaló uv. Va a `PUESTA_EN_MARCHA` §1 y §0, en la pieza 1.
- **`uv run pre-commit install`**, una vez por clon. La primera ejecución de
  gitleaks descarga Go y compila: necesita red y tarda unos minutos, solo esa
  vez (queda en la caché de pre-commit). Va a `PUESTA_EN_MARCHA` en la
  pieza 8.
- **GitHub:** los checks obligatorios del ruleset (§6, tras el PR 1). Se
  anota en `PUESTA_EN_MARCHA` §5.
- **Release:** nada fuera de lo normal. Es la primera (`v0.1.0`).
- **`docs/MAPA.md`:** todos los ficheros de §3.1.

## 9. Guía

`docs/guia/01-arquitectura-hexagonal.md`, "La arquitectura hexagonal de un
agente":

1. Por qué un agente encaja en puertos y adaptadores: un núcleo y muchos
   exteriores (modelo, disco, terminal, MCP).
2. Las cuatro capas y la regla de dependencia, con el contrato de
   import-linter como ejemplo.
3. La raíz de composición: `bootstrap.py`, y por qué `maha` entra por ahí.
4. La base que lo vigila todo: lockfile, lint, tipos, tests, secretos, CI y
   release.

"En la industria": la tabla de §2.

## 10. Riesgos

- **Python 3.15 es nuevo** (2026-10-09). Alguna herramienta puede fallar con
  él. Si pasa, se anota aquí y decide el mantenedor: esperar, fijar una
  versión o quitar 3.15 de los checks obligatorios. El job no se marca como
  opcional sin esa decisión.
- **Clonar en `/mnt/c/…` en lugar de `~/`** dentro de WSL: es mucho más
  lento y mezcla permisos y finales de línea. `PUESTA_EN_MARCHA` §1 lo avisa.
- **`filterwarnings = ["error"]`** puede romper los tests por un aviso de una
  librería de terceros. Si pasa, se ignora solo ese aviso, con un comentario
  y la referencia; nunca todos.
- **gitleaks-action es gratis solo en cuentas personales.** Si el repositorio
  pasa a una organización, hace falta su licencia (gratuita) o ejecutar
  gitleaks directamente.
- **Permisos de gitleaks-action:** con `contents: read` puede no tener acceso
  a los commits del PR. Se comprueba en el propio PR 1. Si falla, se añade
  solo `pull-requests: read` y se anota en "Aprendido al implementar".

## 11. Decisiones

Del humano (2026-10-19):
- Delega en el agente la decisión de plataforma (antes, la decisión abierta
  13): "lo que sea más serio y bueno para el proyecto".
- Aprueba la spec sin cambios, en el PR #2.

Propuestas del agente, aprobadas por el humano (2026-10-19):
1. Versiones de §1.1: cota inferior en `pyproject.toml` y versión exacta en
   el lockfile.
2. Python 3.14 en `.python-version` y uv ≥ 0.13.1 obligatorio (§1.1 y §1.2).
3. `uv_build` como backend (§1.3).
4. Versión estática en `pyproject.toml`, subida al cerrar cada hito (§1.4).
5. `maha` entra por `bootstrap.main` (§1.5).
6. Interfaz en inglés (§1.6).
7. Contratos de import-linter (§1.7) y test de imports del núcleo (§1.8).
8. Reglas de ruff, mypy también sobre los tests y configuración de pytest
   (§1.9).
9. pre-commit con ruff local y el hook oficial de gitleaks (§1.10).
10. CI: disparadores, matriz y acciones fijadas por hash (§1.11). Corrige
    DESIGN §12.
11. Release con `gh` y el mensaje del tag (§1.12).
12. Dos PRs de implementación y checks obligatorios desde el PR 1 (§1.13 y
    §6).
13. Plataforma Linux también en este PC: Ubuntu 26.04 en WSL2, CI solo en
    Linux con `ubuntu-26.04` y sin soporte de Windows nativo en v1 (§1.14).

## 12. Aprendido al implementar

- **ruff 0.17 formatea también Markdown** (pieza 2, 2026-10-20): por
  defecto, `ruff format` revisa los bloques de código Python de los `.md`.
  Se deja así: los ejemplos de las docs siguen el mismo estilo que el código.
- **mypy falla si falta un directorio de `files`** (pieza 3, 2026-10-20):
  `tests: error: Cannot read file`. Por eso `tests/__init__.py` nace en la
  pieza 3 y no en la 5.
- **import-linter rompe si falta una capa** (pieza 4, 2026-10-20):
  `Missing layer in container 'mharness': module mharness.bootstrap does not
  exist`. `__main__` y `bootstrap` van entre paréntesis (capa opcional) hasta
  la pieza 7, que los quita. Probado a mano: detecta `domain → adapters` y un
  `config.py` sin capa.
- **El hook de gitleaks no mira el primer commit de un repo** (pieza 8,
  2026-10-20): usa `gitleaks git --pre-commit --staged`, que compara con
  `HEAD`, y sin commits no hay `HEAD`. En un repo desechable con un commit
  previo, el token inventado (`ghp_` + 36) bloquea el commit
  (`RuleID: github-pat`). A M-Harness no le afecta: ya tiene historial, y el
  CI revisa el historial entero.
- **La primera instalación de pre-commit tardó 25 s** (Go y gitleaks), no
  minutos.
- **Acciones del CI comprobadas el 2026-10-20** en sus releases de GitHub:
  los hashes de `checkout` v7.0.1, `setup-uv` v10.3.0 y `gitleaks-action`
  v3.0.0 son los de §1.1 y §1.11, y las tres siguen siendo la última versión.
- **actionlint 1.7.12 no conoce `ubuntu-26.04`** (pieza 9): su lista de
  runners está anticuada. El runner existe y no es beta (README de
  `actions/runner-images`, 2026-10-20). Sin más avisos.
- **Python 3.15 en local** (pieza 9): con `UV_PYTHON=3.15` pasan `uv sync
  --locked`, ruff, mypy, import-linter y pytest. El riesgo de §10 no se ha
  dado, de momento.
- **CI del PR #4, 2026-10-20:** `checks (3.14)`, `checks (3.15)` y
  `secrets` en verde. gitleaks-action funciona con `contents: read`: no hace
  falta `pull-requests: read` (riesgo de §10).
- **gitleaks-action no revisa todo el historial en un PR** (2026-10-20): en
  un PR solo mira sus commits (13 de 43 en el PR #4), y en un push, los
  commits del push. El historial entero, solo con `workflow_dispatch`. Como
  todo entra por PR, cada commit nuevo queda revisado. Los commits anteriores
  al CI se revisan una vez, a mano, tras integrar el PR 1 (`ESTADO`). §1.11
  decía "sobre todo el historial": eso es lo que hace con `workflow_dispatch`.
- **gitleaks-action instala gitleaks 8.24.3 por defecto** (CI manual sobre
  `main`, 2026-10-20), no la 8.30.1 de pre-commit. Se fija con la variable
  `GITLEAKS_VERSION: 8.30.1` (README de la acción, v3.0.0). Así el CI y
  pre-commit detectan lo mismo. Cambio añadido en el PR 2, con el visto bueno
  del mantenedor.
- **El workflow de release vuelve a pedir el tag anotado** (pieza 11):
  `actions/checkout` puede dejar el tag como una referencia ligera, sin su
  mensaje. Por eso hace `git fetch` del tag y comprueba que es anotado
  (`git cat-file -t` → `tag`). La lectura del título y las notas se probó en
  un repo desechable; la prueba real es el push de `v0.1.0`.
- **`uv version --short` no crea el entorno** (pieza 11): en un clon limpio
  solo lee `pyproject.toml`. El workflow de release no necesita `uv sync`.
- **Ruleset "main protegida", 2026-10-20** (humano, tras el PR 1): exige
  `checks (3.14)`, `checks (3.15)` y `secrets`, con "Require branches to be
  up to date before merging" activada. El CI lanzado a mano sobre `main`
  revisó con gitleaks 41 commits (el historial entero, sin contar merges
  vacíos): sin secretos.

- **Release `v0.1.0`, 2026-10-20:** el push del tag disparó `release.yml`,
  que pasó a la primera (12 s). Título y notas salieron del tag anotado, con
  la lista de PRs debajo. `uv tool install` desde el tag instala
  `maha 0.1.0`. Con esto, §7 queda completa.

Resumen: el hito se hizo en dos PRs (#4 y el de la release) con el orden de
§6, más un commit fuera de plan (versión de gitleaks en el CI). Ninguna
decisión de §11 cambió.
