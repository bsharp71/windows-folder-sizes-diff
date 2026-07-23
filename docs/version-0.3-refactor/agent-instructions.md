
You do not need to give the agent the original full multi-phase spec every time. The phase document already contains the relevant scope, architecture, exclusions, acceptance criteria, and coding-agent assignment for that phase.

Best workflow:

1. Start Phase 0 with the full Phase 0 document.
2. Let the agent complete it.
3. Review and commit the work.
4. Start Phase 1 with the full Phase 1 document.
5. Repeat for each phase.

A new chat for each phase is usually the cleanest approach because it reduces context drift and prevents the agent from prematurely implementing later phases. In the new chat, give it:

- the full phase document;
- access to the current repository;
- a brief note that prior phases are already implemented.

Use the original full spec only as a planning reference for yourself or when the agent needs to understand the broader architecture. It is not required for normal phase execution.

The Coding-Agent Assignment section alone is not enough for a fresh phase session. It is useful as a compact reminder during an ongoing session, but the full phase document should be the governing specification.

A clean kickoff message would be:

```
Implement Phase [N] using the attached specification as the governing document.

Before changing code:

1. Inspect the current repository and confirm the prerequisite phases are present.
2. Identify any conflicts or assumptions that differ from the specification.
3. Create a concise implementation checklist mapped to the acceptance criteria.
4. Implement only Phase [N]. Do not begin later-phase features.
5. Run the complete test suite and report any failures.
6. At completion, provide:

   * files added or changed;
   * architectural decisions made;
   * migrations or commands I must run;
   * test results;
   * acceptance criteria not fully satisfied;
   * any technical debt deferred to the next phase.

Preserve existing working behavior unless the specification explicitly changes it.
```
