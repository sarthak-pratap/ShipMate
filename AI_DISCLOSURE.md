# AI Usage Disclosure

The Zerops Challenge allows AI assistance for code, debugging, tests, design and
documentation, but requires that (a) every AI tool used is disclosed, (b) there
is meaningful contribution of your own, and (c) you understand the code and can
explain the architecture and the decisions to the judges. This file is that
disclosure — mirror it into the submission form.

## Tool used

**One AI tool was used: Hyperagent — an autonomous AI coding agent (built on
Anthropic's Claude).** No other AI tools were used.

| Area | AI involvement |
|------|----------------|
| Architecture & product direction | Directed by me; the agent proposed options, I chose the approach (Zerops-native dev tool, five-service design, three input modes) |
| Implementation (`api/app/core/*`, FastAPI, worker, React UI) | Written by the agent under my direction |
| Tests | Written by the agent; I ran and reviewed them (`make test`) |
| Verification | I tested the tool against real repositories and confirmed the generated `zerops.yaml` and topology were correct |
| Documentation | Drafted by the agent, reviewed by me |
| Azure OpenAI (prompt mode) | A **runtime product feature**, not a build tool — see below |

## My contribution

- I set the product direction and made the design decisions: what to build, the
  five-service Zerops architecture, the three input modes, the neo-brutalist UI,
  and the UX iterations.
- I reviewed, ran, and verified the code, including testing it end-to-end
  against real public repositories.
- I understand how the system works and can explain every part of it to the
  judges — see [`ARCHITECTURE.md`](ARCHITECTURE.md) for the module-by-module
  walkthrough (the `Topology` IR, the compose parser, the repo/Dockerfile
  detector, the generator, and the linter).

## Note on the runtime LLM

Prompt mode calls Azure OpenAI **at runtime** to turn a natural-language
description into a structured service list. This is a feature of the product,
not a tool used to write ShipMate's source code — and the schema-correct
`zerops.yaml` is always produced by ShipMate's own deterministic generator, not
by the model.
