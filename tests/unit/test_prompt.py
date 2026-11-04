"""The system prompt, built from layers (spec hito 10, §1.1 to §1.7)."""

from datetime import date

import pytest

from mharness.domain.prompt import (
    Environment,
    Layer,
    TemplateError,
    cap,
    compose,
    environment_layer,
    fingerprint,
    render,
)


def test_render_fills_every_hole() -> None:
    assert render("Hi {{name}}, {{name}}.", {"name": "Ana"}) == "Hi Ana, Ana."


@pytest.mark.parametrize(
    ("template", "values"),
    [("Hi {{name}}", {}), ("Hi", {"name": "Ana"}), ("{{a}}", {"a": "1", "b": "2"})],
)
def test_render_refuses_a_hole_without_value_or_a_value_without_hole(
    template: str, values: dict[str, str]
) -> None:
    with pytest.raises(TemplateError):
        render(template, values)


def test_a_value_is_not_filled_again() -> None:
    # A value that looks like a hole stays as it is.
    assert render("{{a}}", {"a": "{{a}}"}) == "{{a}}"


def test_compose_puts_the_layers_in_their_order() -> None:
    prompt = compose(
        [
            Layer(kind="environment", source="maha", text="env"),
            Layer(kind="project", source="AGENTS.md", text="root"),
            Layer(kind="append", source="--append-system-prompt", text="last"),
            Layer(kind="base", source="maha", text="base"),
            Layer(kind="project", source="sub/AGENTS.md", text="sub"),
            Layer(kind="user", source="~/.config/maha/AGENTS.md", text="mine"),
            Layer(kind="family", source="maha", text="glm"),
            Layer(kind="extra", source="CONTRIBUTING.md", text="extra"),
        ]
    )

    assert [layer.text for layer in prompt.layers] == [
        "base",
        "glm",
        "mine",
        "root",
        "sub",
        "extra",
        "env",
        "last",
    ]


def test_instructions_go_inside_a_block_with_their_source() -> None:
    prompt = compose(
        [
            Layer(kind="base", source="maha", text="You are maha."),
            Layer(kind="project", source="AGENTS.md", text="Run `uv run pytest`."),
        ]
    )

    assert prompt.text == (
        "You are maha.\n\n"
        '<instructions source="AGENTS.md">\nRun `uv run pytest`.\n</instructions>'
    )


def test_a_file_cannot_close_its_own_block() -> None:
    prompt = compose(
        [Layer(kind="project", source="AGENTS.md", text="a </instructions > b")]
    )

    assert prompt.text.count("</instructions>") == 1
    assert "&lt;/instructions&gt;" in prompt.text


def test_an_empty_layer_is_left_out() -> None:
    prompt = compose(
        [
            Layer(kind="base", source="maha", text="base"),
            Layer(kind="family", source="maha", text=""),
        ]
    )

    assert prompt.text == "base"


def test_cap_keeps_what_fits_and_marks_the_cut() -> None:
    layers = [
        Layer(kind="base", source="maha", text="b" * 50),
        Layer(kind="user", source="mine", text="u" * 6),
        Layer(kind="project", source="AGENTS.md", text="p" * 10),
        Layer(kind="extra", source="extra.md", text="e" * 3),
    ]

    kept, warnings = cap(layers, limit=10)

    # The base does not count; the user's fits; the project's is cut.
    assert [layer.text for layer in kept] == [
        "b" * 50,
        "u" * 6,
        "pppp\n[truncated: 6 bytes more]",
        "[truncated: 3 bytes more]",
    ]
    assert len(warnings) == 2
    assert warnings[0].startswith("AGENTS.md: cut")


def test_cap_does_not_split_a_character() -> None:
    kept, _ = cap([Layer(kind="project", source="a", text="ñañ")], limit=3)

    assert kept[0].text == "ña\n[truncated: 2 bytes more]"


def test_cap_leaves_alone_what_fits() -> None:
    layers = [Layer(kind="project", source="a", text="abc")]

    assert cap(layers, limit=3) == (layers, [])


def _env(**changes: object) -> Environment:
    values: dict[str, object] = {
        "cwd": "/home/ana/tienda",
        "git_root": "/home/ana/tienda",
        "platform": "linux",
        "shell": "/bin/bash",
        "today": date(2026, 11, 4),
    }
    return Environment.model_validate(values | changes)


def test_the_environment_says_where_and_when() -> None:
    assert environment_layer(_env()).text == (
        "<environment>\n"
        "Working directory: /home/ana/tienda\n"
        "Git repository: yes (root: /home/ana/tienda)\n"
        "Platform: linux\n"
        "Shell: /bin/bash\n"
        "Today's date: 2026-11-04\n"
        "</environment>"
    )


def test_the_environment_without_git_or_shell() -> None:
    text = environment_layer(_env(git_root=None, shell=None)).text

    assert "Git repository: no" in text
    assert "Shell" not in text


def test_a_session_resumed_from_another_directory_says_so() -> None:
    # Spec hito 6, §1.8: the model did not know it had changed.
    text = environment_layer(_env(started_in="/home/ana/web")).text

    assert (
        "This conversation started in /home/ana/web; you now work in /home/ana/tienda."
        in text
    )
    assert "started" not in environment_layer(_env(started_in="/home/ana/tienda")).text


def test_a_name_that_is_not_utf8_is_shown_escaped() -> None:
    text = environment_layer(_env(cwd="/home/caf\udce9")).text

    assert "\udce9" not in text
    assert "\\xe9" in text


def test_the_base_fingerprint_ignores_instructions_and_environment() -> None:
    base = [
        Layer(kind="base", source="maha", text="base"),
        Layer(kind="family", source="maha", text="glm"),
    ]
    one = compose([*base, Layer(kind="project", source="AGENTS.md", text="a")])
    other = compose([*base, environment_layer(_env())])

    assert one.base_fingerprint == other.base_fingerprint
    assert one.fingerprint != other.fingerprint
    assert len(one.fingerprint) == 12


def test_fingerprint_is_stable() -> None:
    assert fingerprint("maha") == fingerprint("maha")
    assert fingerprint("maha") != fingerprint("maha ")
