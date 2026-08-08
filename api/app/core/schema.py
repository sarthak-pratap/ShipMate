"""Internal representation of a Zerops project topology.

Everything ShipMate does funnels through these dataclasses: the compose parser,
the repo detector and the LLM prompt-mode all emit a `Topology`, and the YAML
generator + linter + diagram all consume one. Keeping a single intermediate
representation is what lets three very different inputs share one output path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# High-level role of a service, used by the diagram to lay things out and by the
# linter to reason about what wiring should exist.
ROLE_FRONTEND = "frontend"
ROLE_API = "api"
ROLE_WORKER = "worker"
ROLE_DATABASE = "database"
ROLE_CACHE = "cache"
ROLE_STORAGE = "storage"
ROLE_BROKER = "broker"
ROLE_SEARCH = "search"


@dataclass
class Port:
    port: int
    http_support: bool = True


@dataclass
class Service:
    hostname: str                     # Zerops service hostname (private-net name)
    role: str                         # one of the ROLE_* constants
    type: str                         # Zerops managed type, e.g. "postgresql@16"
    # runtime services only ↓
    base: Optional[str] = None        # build/run base, e.g. "python@3.12"
    build_commands: List[str] = field(default_factory=list)
    start: Optional[str] = None
    ports: List[Port] = field(default_factory=list)
    deploy_files: str = "./"
    env: Dict[str, str] = field(default_factory=dict)
    # managed-service only ↓
    ha: bool = False                  # postgres/valkey/etc high-availability mode
    # graph wiring
    depends_on: List[str] = field(default_factory=list)
    public: bool = False              # exposed to public traffic (subdomain access)

    @property
    def is_runtime(self) -> bool:
        return self.role in (ROLE_FRONTEND, ROLE_API, ROLE_WORKER)

    @property
    def is_managed(self) -> bool:
        return not self.is_runtime


@dataclass
class Topology:
    project_name: str
    services: List[Service] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)   # parse-time notes

    def by_hostname(self, name: str) -> Optional[Service]:
        for s in self.services:
            if s.hostname == name:
                return s
        return None

    def runtimes(self) -> List[Service]:
        return [s for s in self.services if s.is_runtime]

    def managed(self) -> List[Service]:
        return [s for s in self.services if s.is_managed]
