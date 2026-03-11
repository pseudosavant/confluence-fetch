from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import tomli_w

from confluence_fetch.models import AppConfig


BUILTIN_TOKEN_ENV = "CONFLUENCE_TOKEN"


def default_config_path(home: Path | None = None) -> Path:
    base = home if home is not None else Path.home()
    return base / ".confluence-fetch" / "config.toml"


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path if path is not None else default_config_path()
    if not config_path.exists():
        return AppConfig()

    import tomllib

    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    defaults = raw.get("defaults", {})
    domains = raw.get("domains", {})
    domain_token_env_vars: dict[str, str] = {}
    domain_emails: dict[str, str] = {}

    for domain, values in domains.items():
        if isinstance(values, dict):
            env_var = values.get("token_env_var")
            if isinstance(env_var, str) and env_var:
                domain_token_env_vars[domain] = env_var
            email = values.get("email")
            if isinstance(email, str) and email:
                domain_emails[domain] = email

    default_token_env_var = defaults.get("token_env_var")
    if not isinstance(default_token_env_var, str) or not default_token_env_var:
        default_token_env_var = None
    default_email = defaults.get("email")
    if not isinstance(default_email, str) or not default_email:
        default_email = None

    return AppConfig(
        default_token_env_var=default_token_env_var,
        default_email=default_email,
        domain_token_env_vars=domain_token_env_vars,
        domain_emails=domain_emails,
        raw=raw,
    )


def write_config(config: AppConfig, path: Path | None = None) -> Path:
    config_path = path if path is not None else default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    raw: dict[str, Any] = dict(config.raw)
    defaults = dict(raw.get("defaults", {}))
    if config.default_token_env_var:
        defaults["token_env_var"] = config.default_token_env_var
    else:
        defaults.pop("token_env_var", None)
    if config.default_email:
        defaults["email"] = config.default_email
    else:
        defaults.pop("email", None)

    if defaults:
        raw["defaults"] = defaults
    else:
        raw.pop("defaults", None)

    domains = dict(raw.get("domains", {}))
    for domain, env_var in config.domain_token_env_vars.items():
        existing = domains.get(domain, {})
        domains[domain] = {**existing} if isinstance(existing, dict) else {}
        domains[domain]["token_env_var"] = env_var
    for domain, email in config.domain_emails.items():
        existing = domains.get(domain, {})
        domains[domain] = {**existing} if isinstance(existing, dict) else {}
        domains[domain]["email"] = email

    for domain in list(domains):
        if domain not in config.domain_token_env_vars:
            domains[domain].pop("token_env_var", None)
        if domain not in config.domain_emails:
            domains[domain].pop("email", None)
        if not domains[domain]:
            domains.pop(domain, None)

    if domains:
        raw["domains"] = domains
    else:
        raw.pop("domains", None)

    config_path.write_text(tomli_w.dumps(raw), encoding="utf-8", newline="\n")
    return config_path


def set_default_token_env_var(
    env_var: str,
    path: Path | None = None,
    home: Path | None = None,
) -> Path:
    config_path = path if path is not None else default_config_path(home)
    config = load_config(config_path)
    config.default_token_env_var = env_var
    return write_config(config, config_path)


def set_default_email(
    email: str,
    path: Path | None = None,
    home: Path | None = None,
) -> Path:
    config_path = path if path is not None else default_config_path(home)
    config = load_config(config_path)
    config.default_email = email
    return write_config(config, config_path)


def clear_default_email(path: Path | None = None, home: Path | None = None) -> Path:
    config_path = path if path is not None else default_config_path(home)
    config = load_config(config_path)
    config.default_email = None
    return write_config(config, config_path)


def set_domain_token_env_var(
    domain: str,
    env_var: str,
    path: Path | None = None,
    home: Path | None = None,
) -> Path:
    config_path = path if path is not None else default_config_path(home)
    config = load_config(config_path)
    config.domain_token_env_vars[domain] = env_var
    return write_config(config, config_path)


def set_domain_email(
    domain: str,
    email: str,
    path: Path | None = None,
    home: Path | None = None,
) -> Path:
    config_path = path if path is not None else default_config_path(home)
    config = load_config(config_path)
    config.domain_emails[domain] = email
    return write_config(config, config_path)


def remove_domain_email(domain: str, path: Path | None = None, home: Path | None = None) -> Path:
    config_path = path if path is not None else default_config_path(home)
    config = load_config(config_path)
    config.domain_emails.pop(domain, None)
    return write_config(config, config_path)


def remove_domain(domain: str, path: Path | None = None, home: Path | None = None) -> Path:
    config_path = path if path is not None else default_config_path(home)
    config = load_config(config_path)
    config.domain_token_env_vars.pop(domain, None)
    config.domain_emails.pop(domain, None)
    return write_config(config, config_path)


def resolve_token_env_name(
    host: str,
    config: AppConfig,
    token_env_override: str | None = None,
) -> str:
    if token_env_override:
        return token_env_override
    if host in config.domain_token_env_vars:
        return config.domain_token_env_vars[host]
    if config.default_token_env_var:
        return config.default_token_env_var
    return BUILTIN_TOKEN_ENV


def render_config_show(config_path: Path, config: AppConfig, env: dict[str, str] | None = None) -> str:
    current_env = env if env is not None else dict(os.environ)

    def state_for(name: str) -> str:
        value = current_env.get(name)
        return "set" if value else "missing"

    lines = [f"Config path: {config_path}"]
    default_name = config.default_token_env_var or BUILTIN_TOKEN_ENV

    if config.default_token_env_var:
        lines.append(f"Default token env: {default_name} ({state_for(default_name)})")
    else:
        lines.append(
            f"Default token env: {BUILTIN_TOKEN_ENV} ({state_for(BUILTIN_TOKEN_ENV)}) [built-in fallback]"
        )
    lines.append(f"Default email: {config.default_email or 'none'}")

    domains = sorted(set(config.domain_token_env_vars) | set(config.domain_emails))
    if domains:
        lines.append("Domain overrides:")
        for domain in domains:
            env_name = config.domain_token_env_vars.get(domain)
            email = config.domain_emails.get(domain)
            parts = [domain]
            if env_name:
                parts.append(f"token env {env_name} ({state_for(env_name)})")
            if email:
                parts.append(f"email {email}")
            lines.append(f"- {'; '.join(parts)}")
    else:
        lines.append("Domain overrides: none")

    return "\n".join(lines) + "\n"


def resolve_email(
    host: str,
    config: AppConfig,
    env: dict[str, str] | None = None,
) -> str | None:
    if host in config.domain_emails:
        return config.domain_emails[host]
    if config.default_email:
        return config.default_email
    current_env = env if env is not None else dict(os.environ)
    for key in ("CONFLUENCE_EMAIL", "confluence_email"):
        value = current_env.get(key, "")
        if value and value.strip():
            return value.strip()
    return None
