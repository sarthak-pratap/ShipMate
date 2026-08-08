#!/usr/bin/env python3
"""ShipMate CLI — the fastest way to try the core locally, no server needed.

    python shipmate_cli.py compose ../examples/taskboard-compose.yml
    python shipmate_cli.py prompt "a notes app with postgres and a nightly digest worker"
    cat compose.yml | python shipmate_cli.py compose -

Prints the generated zerops.yaml, the project-import file, and lint findings.
"""
from __future__ import annotations

import sys

from app.core.compose_parser import parse_compose
from app.core.linter import lint
from app.core.zerops_generator import generate_all


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    mode = argv[0]
    if mode == "compose":
        topo = parse_compose(_read(argv[1]))
    elif mode == "prompt":
        from app.core import llm
        if not llm.available():
            print("Prompt mode needs AZURE_OPENAI_* env vars set.", file=sys.stderr)
            return 2
        topo = llm.topology_from_prompt(" ".join(argv[1:]))
    else:
        print(f"unknown mode '{mode}' (use: compose | prompt)", file=sys.stderr)
        return 2

    result = generate_all(topo)
    findings = lint(topo)

    print("=" * 60, "\n zerops.yaml\n", "=" * 60, sep="")
    print(result["zerops_yaml"])
    print("=" * 60, "\n zerops-project-import.yml\n", "=" * 60, sep="")
    print(result["import_yaml"])
    print("=" * 60, "\n lint (", len(findings), "findings)\n", "=" * 60, sep="")
    for f in findings:
        print(f"  [{f['severity'].upper():7}] {f['rule']} ({f['service']})")
        print(f"           → {f['fix']}")
    if result["warnings"]:
        print("\n warnings:")
        for w in result["warnings"]:
            print(f"  - {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
