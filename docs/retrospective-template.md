# Retrospective Step (project convention)

An optional step for ticket-driven work in this repo (e.g. a `subagent-execution`-style run): after an implementer subagent reports its work `DONE` — especially one that struggled, iterated, or hit a known gap — the controller may resume that same subagent (it still has full context of what it actually tried) and ask it to reflect, before moving on to the next ticket.

This is separate from ticket review (which checks the work) and separate from the diagram-generation pipeline's own LLM calls (`PythonFullStrategy.run()`'s script-writing model has no memory between calls and can't be "interrogated" — this step targets the Claude Code implementer subagent that drove a ticket, not the geometry LLM it was operating).

## When to use it

Controller's judgment, not mandatory per ticket. Good candidates:
- A ticket that needed more than one attempt to converge.
- A ticket that ended in a known-gap / accepted limitation rather than a clean pass.
- A ticket exploring genuinely new territory (first of its kind), where the implementer's experience is likely to generalize to later, similar tickets.

Skip it for mechanical tickets with no friction — there's nothing to learn.

## How to invoke it

`SendMessage` to the implementer's agent id (from the original dispatch), after its final `DONE`/report, with a message shaped like:

```
One more question, purely retrospective — not code, no action needed from you.

[1-2 sentences recapping what they did and where it got hard, so they don't
have to re-derive it]

1. [What specifically made this hard? Was it missing information, a missing
   tool, ambiguity in the task, or something else?]
2. If you'd had ONE additional tool/helper/piece of information available
   that you didn't have, what would it have been? Be concrete (a function
   signature, a value you'd want to query, an assertion you'd want to make)
   — not "better tooling" in the abstract.
3. Is this specific to this ticket, or would it plausibly help elsewhere?

A few sentences per question is plenty.
```

Tune the specifics to what the ticket actually involved, but keep the three-question shape: (1) what made it hard, (2) one concrete thing that would have helped, (3) how general is that finding.

## What to do with the answer

- Record it in the ledger (or, if the feature is closing out, in a durable `docs/specs/` writeup — `.scratch/<feature>/` is deleted at Close, so a retrospective finding worth keeping needs a permanent home before then).
- Look across multiple retrospectives from the same feature for convergence — the same finding showing up from unrelated tickets/agents is a much stronger signal than any single agent's opinion. Prefer acting on convergent findings over one-off suggestions.
- Treat every answer as a finding to evaluate, not a mandate to build — the same judgment applies as to any other suggestion (does the evidence support it, is it in scope, is it worth the complexity).

## Example

See `docs/specs/2026-09-04-diagram-kinds-retrospective-findings.md` for a worked example: five implementer subagents from the `diagram-kinds-poc` feature were asked this after their tickets closed, and their answers converged independently on the same missing capability (no way to verify a label's rendered position against canvas bounds before finishing) plus two smaller, well-scoped findings.
