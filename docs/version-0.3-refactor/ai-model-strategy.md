For this project, I would use **GLM 5.2 as the primary coding agent**.

This refactor is not mainly about generating Python quickly. It requires the model to:

* preserve behavior across phases;
* follow long technical specifications without drifting into later work;
* reason across GUI threading, filesystem traversal, SQLAlchemy, Alembic, and Windows-specific behavior;
* make architectural changes across many files;
* maintain consistency over a long implementation session.

GLM 5.2 is specifically positioned for project-level software engineering, long-horizon agent workflows, tool use, and sustained adherence to engineering standards. It has a 1-million-token context window, which is useful once the repository, phase specification, tests, and prior implementation decisions accumulate. OpenRouter currently lists it near the top of its programming-model usage rankings. ([OpenRouter][1])

## My recommended model portfolio

| Role                     | Model               | Why                                                                       |
| ------------------------ | ------------------- | ------------------------------------------------------------------------- |
| **Primary implementer**  | **GLM 5.2**         | Best fit for long, phased, repository-wide work                           |
| **Independent reviewer** | **DeepSeek V4 Pro** | Strong codebase analysis at materially lower cost                         |
| **Focused code tasks**   | **Kimi K2.7 Code**  | Good for bounded implementation, debugging, and test repair               |
| **Cheap routine work**   | **Gemma 4 31B**     | Suitable for tests, documentation, small functions, and review assistance |

DeepSeek V4 Pro is also designed for full-codebase analysis and complex multi-step software work, with a 1-million-token context window. At current OpenRouter pricing, it is substantially cheaper than GLM 5.2: roughly **$0.435/$0.87 per million input/output tokens**, compared with **$0.77/$2.42** for GLM 5.2. ([OpenRouter][1])

## How I would actually run the project

Use **GLM 5.2 for Phase 0 first**. It should inspect the repository, implement the phase document, run tests, and stop.

Then give the completed work to **DeepSeek V4 Pro in a separate review session** with instructions to:

* audit the implementation against every acceptance criterion;
* identify scope creep;
* find threading, cancellation, path-handling, and test weaknesses;
* recommend fixes without redesigning later phases.

Return to GLM 5.2 for corrections.

That two-model loop is more reliable than asking one model to implement and certify its own work.

## Where Kimi K2.7 Code fits

Kimi K2.7 Code would be my second choice as the primary implementer when:

* the phase is tightly scoped;
* the architecture is already established;
* the work is mostly concrete code changes;
* you want to reduce cost or compare code acceptance.

I would be more comfortable using Kimi for later bounded tasks such as:

* implementing repository classes;
* repairing a migration;
* adding pytest fixtures;
* optimizing batch inserts;
* correcting a specific Windows API wrapper.

For Phase 0 and the initial architecture, I prefer GLM because the greater risk is **instruction and architectural drift**, not raw syntax generation.

## Gemma 4

I would not make Gemma 4 31B the sole lead agent for the entire refactor. It is inexpensive—currently listed around **$0.10 input and $0.35 output per million tokens**, with a 256K context window—and is described as strong in coding and agentic workflows. That makes it attractive for routine work, but this project has enough intertwined architectural constraints that I would reserve it for secondary tasks. ([OpenRouter][2])

**Final recommendation:** start with **GLM 5.2 at high reasoning**, use **DeepSeek V4 Pro as the reviewer**, and use **Kimi K2.7 Code for bounded corrective tasks**.

[1]: https://openrouter.ai/collections/programming "Best AI Models for Coding | OpenRouter"
[2]: https://openrouter.ai/google/gemma-4-31b-it?utm_source=chatgpt.com "Google: Gemma 4 31B - API Pricing & Benchmarks"
