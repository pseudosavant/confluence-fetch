from __future__ import annotations

from pathlib import Path

from confluence_fetch.config import (
    BUILTIN_TOKEN_ENV,
    clear_default_email,
    load_config,
    remove_domain,
    remove_domain_email,
    render_config_show,
    resolve_email,
    resolve_token_env_name,
    set_default_email,
    set_domain_email,
    set_default_token_env_var,
    set_domain_token_env_var,
)
from confluence_fetch.models import AppConfig


def test_config_updates_and_load_round_trip(tmp_path: Path) -> None:
    config_path = tmp_path / ".confluence-fetch" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('[other]\nvalue = "keep"\n', encoding="utf-8")

    set_default_token_env_var("DEFAULT_TOKEN", path=config_path)
    set_default_email("user@example.com", path=config_path)
    set_domain_token_env_var("sona-systems.atlassian.net", "SONA_TOKEN", path=config_path)
    set_domain_email("sona-systems.atlassian.net", "sona@example.com", path=config_path)
    config = load_config(config_path)

    assert config.default_token_env_var == "DEFAULT_TOKEN"
    assert config.default_email == "user@example.com"
    assert config.domain_token_env_vars == {"sona-systems.atlassian.net": "SONA_TOKEN"}
    assert config.domain_emails == {"sona-systems.atlassian.net": "sona@example.com"}
    assert config.raw["other"]["value"] == "keep"

    remove_domain_email("sona-systems.atlassian.net", path=config_path)
    remove_domain("sona-systems.atlassian.net", path=config_path)
    clear_default_email(path=config_path)
    config = load_config(config_path)
    assert config.domain_token_env_vars == {}
    assert config.domain_emails == {}
    assert config.default_email is None


def test_token_env_resolution_order() -> None:
    config = AppConfig(
        default_token_env_var="DEFAULT_TOKEN",
        default_email="user@example.com",
        domain_token_env_vars={"example.atlassian.net": "DOMAIN_TOKEN"},
        domain_emails={"example.atlassian.net": "domain@example.com"},
    )

    assert resolve_token_env_name("example.atlassian.net", config, "CLI_TOKEN") == "CLI_TOKEN"
    assert resolve_token_env_name("example.atlassian.net", config, None) == "DOMAIN_TOKEN"
    assert resolve_token_env_name("other.atlassian.net", config, None) == "DEFAULT_TOKEN"
    assert resolve_token_env_name("other.atlassian.net", AppConfig(), None) == BUILTIN_TOKEN_ENV
    assert resolve_email("example.atlassian.net", config, {}) == "domain@example.com"
    assert resolve_email("other.atlassian.net", config, {}) == "user@example.com"
    assert resolve_email("other.atlassian.net", AppConfig(), {"CONFLUENCE_EMAIL": "env@example.com"}) == "env@example.com"


def test_config_show_lists_env_names_without_values(tmp_path: Path) -> None:
    config_path = tmp_path / ".confluence-fetch" / "config.toml"
    config = AppConfig(
        default_token_env_var="DEFAULT_TOKEN",
        default_email="user@example.com",
        domain_token_env_vars={"example.atlassian.net": "DOMAIN_TOKEN"},
        domain_emails={"example.atlassian.net": "domain@example.com"},
    )
    output = render_config_show(
        config_path,
        config,
        env={"DEFAULT_TOKEN": "secret-default"},
    )

    assert "DEFAULT_TOKEN (set)" in output
    assert "Default email: user@example.com" in output
    assert "DOMAIN_TOKEN (missing)" in output
    assert "email domain@example.com" in output
    assert "secret-default" not in output
