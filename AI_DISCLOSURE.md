# AI Usage Disclosure

The Zerops Challenge allows AI assistance for code, debugging, tests, design and
documentation, but requires that (a) every AI tool used is disclosed, (b) there
is meaningful original work of your own, and (c) you understand the code and can
explain the architecture and decisions to the judges. This file is that
disclosure — mirror it into the submission form.

> ⚠️ FILL IN before submitting: list the exact tools/models you used and adjust
> the notes to match reality. The table below reflects the tools used while
> preparing this repository; edit it to be accurate for you.

## Tools used

| Tool | Used for |
|------|----------|
| _e.g. Claude Code / Cursor / Codex_ | code scaffolding, refactoring, tests |
| _e.g. an AI assistant_ | architecture discussion, docs, UI design direction |
| Azure AI Foundry (GPT) | **a runtime feature** — prompt mode turns English into a service list (this is part of the product, not a build tool) |

## What is my own work / understanding

- The core logic — the `Topology` intermediate representation, the
  docker-compose parser, the repo/Dockerfile detector, the `zerops.yaml` +
  project-import generator, and the misconfig linter rules — is authored and
  understood by me. I can explain every module in `api/app/core/` and the
  reasoning behind the five-service Zerops architecture (see `ARCHITECTURE.md`).
- AI assistance was used for boilerplate, the React UI, tests, and
  documentation, and is disclosed above.
- No part of this project is an unmodified, unreviewed AI dump: I reviewed,
  ran (`make test`), and verified the behaviour against real repositories.

## Note on the runtime LLM

Prompt mode calls Azure OpenAI **at runtime** to propose a service list from a
natural-language description. This is a product feature, not a code-generation
tool used to build ShipMate — and the schema-correct YAML is always produced by
ShipMate's own deterministic generator, not by the model.
