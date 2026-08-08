"""Docker image / runtime → Zerops service-type mappings.

This table is deliberately hand-curated (not LLM-generated) because accuracy of
the emitted zerops.yaml is the entire product. Extend it as we validate more
service types against the Zerops docs.
"""
from __future__ import annotations

from typing import Optional, Tuple

from .schema import (
    ROLE_API,
    ROLE_BROKER,
    ROLE_CACHE,
    ROLE_DATABASE,
    ROLE_SEARCH,
    ROLE_STORAGE,
)

# image prefix -> (zerops type, role, ha_capable)
MANAGED_IMAGE_MAP = {
    "postgres": ("postgresql@16", ROLE_DATABASE, True),
    "postgresql": ("postgresql@16", ROLE_DATABASE, True),
    "mariadb": ("mariadb@11", ROLE_DATABASE, True),
    "mysql": ("mariadb@11", ROLE_DATABASE, True),   # Zerops offers MariaDB
    "mongo": ("mongodb@7", ROLE_DATABASE, True),
    "mongodb": ("mongodb@7", ROLE_DATABASE, True),
    "redis": ("valkey@7", ROLE_CACHE, True),        # Zerops uses Valkey/KeyDB
    "valkey": ("valkey@7", ROLE_CACHE, True),
    "keydb": ("keydb@6", ROLE_CACHE, True),
    "elasticsearch": ("elasticsearch@8", ROLE_SEARCH, False),
    "meilisearch": ("meilisearch@1", ROLE_SEARCH, False),
    "typesense": ("typesense@0", ROLE_SEARCH, False),
    "rabbitmq": ("rabbitmq@3", ROLE_BROKER, False),
    "nats": ("nats@2", ROLE_BROKER, False),
    "kafka": ("kafka@3", ROLE_BROKER, False),
    "minio": ("object-storage", ROLE_STORAGE, False),
}

# runtime image prefix -> (zerops base, default_start_hint)
RUNTIME_IMAGE_MAP = {
    "node": ("nodejs@22", None),
    "nodejs": ("nodejs@22", None),
    "python": ("python@3.12", None),
    "golang": ("go@1", None),
    "go": ("go@1", None),
    "php": ("php@8.3", None),
    "ruby": ("ruby@3.3", None),
    "rust": ("rust@1", None),
    "openjdk": ("java@21", None),
    "eclipse-temurin": ("java@21", None),
    "dotnet": ("dotnet@8", None),
    "elixir": ("elixir@1", None),
    "nginx": ("nginx@1", None),
    "caddy": ("static", None),
}

# repo detection file -> (zerops base, role, start hint)
DETECT_FILES = {
    "package.json": ("nodejs@22", ROLE_API, "npm run start"),
    "requirements.txt": ("python@3.12", ROLE_API, "uvicorn app.main:app --host 0.0.0.0 --port 8000"),
    "pyproject.toml": ("python@3.12", ROLE_API, "uvicorn app.main:app --host 0.0.0.0 --port 8000"),
    "go.mod": ("go@1", ROLE_API, "./app"),
    "composer.json": ("php@8.3", ROLE_API, None),
    "Gemfile": ("ruby@3.3", ROLE_API, "bundle exec rails server -b 0.0.0.0"),
    "pom.xml": ("java@21", ROLE_API, "java -jar app.jar"),
    "Cargo.toml": ("rust@1", ROLE_API, "./target/release/app"),
}


def _strip_image(image: str) -> str:
    """`docker.io/library/postgres:16-alpine` -> `postgres`."""
    ref = image.split("/")[-1]
    return ref.split(":")[0].lower()


def match_managed(image: str) -> Optional[Tuple[str, str, bool]]:
    key = _strip_image(image)
    for prefix, val in MANAGED_IMAGE_MAP.items():
        if key == prefix or key.startswith(prefix):
            return val
    return None


def match_runtime(image: str) -> Optional[Tuple[str, Optional[str]]]:
    key = _strip_image(image)
    for prefix, val in RUNTIME_IMAGE_MAP.items():
        if key == prefix or key.startswith(prefix):
            return val
    return None
