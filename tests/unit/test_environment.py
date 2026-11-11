"""The variables a command gets (spec mejora-2026-10-23-deuda-hito-5, B4 and
E1): a list of allowed names, not the environment minus known secrets."""

from mharness.domain.environment import NO_EDITOR, command_env

ENVIRON = {
    "PATH": "/usr/bin",
    "HOME": "/home/ane",
    "LANG": "es_ES.UTF-8",
    "LC_ALL": "es_ES.UTF-8",
    "XDG_CONFIG_HOME": "/home/ane/.config",
    "VIRTUAL_ENV": "/p/.venv",
    "TERM": "xterm-256color",
    "OPENCODE_API_KEY": "sk-inventada",
    "MI_CLAVE": "inventada",
    "SSH_AUTH_SOCK": "/tmp/ssh-agent.sock",
    "AWS_SECRET_ACCESS_KEY": "inventada",
    "PYTHONPATH": "/tmp/x",
}


def test_only_the_allowed_variables_pass() -> None:
    assert command_env(ENVIRON) == {
        "PATH": "/usr/bin",
        "HOME": "/home/ane",
        "LANG": "es_ES.UTF-8",
        "LC_ALL": "es_ES.UTF-8",
        "XDG_CONFIG_HOME": "/home/ane/.config",
        "VIRTUAL_ENV": "/p/.venv",
        "TERM": "xterm-256color",
        **NO_EDITOR,
    }


def test_an_allowed_prefix_never_lets_a_credential_through() -> None:
    environ = {"XDG_SESSION_TOKEN": "x", "LC_PASSWORD": "x", "LC_API_KEY": "x"}

    assert command_env(environ) == NO_EDITOR


def test_a_named_variable_is_dropped_even_if_allowed() -> None:
    # The provider's key could, in theory, be called anything.
    assert command_env({"PATH": "/bin", "TZ": "x"}, drop={"TZ"}) == {
        "PATH": "/bin",
        **NO_EDITOR,
    }


def test_no_editor_opens() -> None:
    # Without a terminal an editor fails with noise or waits (`code --wait`
    # in core.editor): `true` gives an empty text at once, and git stops
    # with a clear error (found 2026-10-27). GIT_EDITOR goes before
    # core.editor, VISUAL and EDITOR (git-var(1), git 2.53, 2026-10-27).
    environ = {"GIT_EDITOR": "vi", "VISUAL": "code --wait", "EDITOR": "nano"}

    assert command_env(environ) == {
        "GIT_EDITOR": "true",
        "VISUAL": "true",
        "EDITOR": "true",
    }


def test_the_runtime_folder_does_not_pass() -> None:
    # Audit after hito 10, H8: with it, the session bus is reachable (the
    # keyring, an SSH or GPG agent) at $XDG_RUNTIME_DIR/bus.
    environ = {"XDG_RUNTIME_DIR": "/run/user/1000", "XDG_DATA_HOME": "/d"}

    assert command_env(environ) == {"XDG_DATA_HOME": "/d", **NO_EDITOR}


def test_the_user_adds_variables() -> None:
    # Audit after hito 10, P5.
    environ = {"JAVA_HOME": "/opt/java", "HTTPS_PROXY": "http://p", "OTHER": "x"}

    assert command_env(environ, extra=["JAVA_HOME", "HTTPS_PROXY", "MISSING"]) == {
        "JAVA_HOME": "/opt/java",
        "HTTPS_PROXY": "http://p",
        **NO_EDITOR,
    }


def test_an_added_variable_never_lets_the_providers_key_through() -> None:
    environ = {"MI_CLAVE": "sk-inventada"}

    assert command_env(environ, drop=["MI_CLAVE"], extra=["MI_CLAVE"]) == NO_EDITOR
