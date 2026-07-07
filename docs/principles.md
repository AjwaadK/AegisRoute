# Aegis Product and Engineering Principles

## Product principles

- **Solve real developer pain.** Build features that remove repeated infrastructure work from AI teams.
- **Infrastructure should reduce operational burden.** Aegis should make systems easier to run, debug, and scale.
- **APIs are promises.** Public contracts should be stable, documented, and changed carefully.
- **User trust matters more than feature count.** Reliability, clear errors, and predictable behavior beat broad but shallow capabilities.
- **Self-host first, hosted later.** Prove the open-source gateway before building Aegis Cloud.
- **Platform capabilities matter more than repo count.** New products should exist because they solve a workflow or operations problem, not because they are exciting to name.

## Engineering principles

- **Correctness before reliability before observability before scalability before optimization before fancy features.** Use this ordering when tradeoffs are required.
- **Observability is a feature.** Logs, metrics, and traces are part of the product experience for operators.
- **Every abstraction must earn its keep.** Add abstractions when they reduce coupling or clarify boundaries, not because they might be useful later.
- **Design before implementation, but only enough to clarify boundaries.** Avoid both architecture-free coding and endless design.
- **Tests protect contracts.** Tests should verify behavior that users, callers, or operators depend on.
- **Logs should explain production behavior.** A useful log should help answer what happened, where, and why.
- **Failure modes should be explicit.** Provider failures, validation errors, timeouts, and internal errors should be distinguishable.
- **Avoid technology collecting.** Do not add tools because they are popular; add them because the product has a real need.
- **Measure before optimizing.** Optimization without measurement usually adds complexity without proof.
- **Defer complexity until evidence demands it.** Start with the simplest design that preserves important boundaries.
- **Use AI to accelerate implementation, not replace engineering judgment.** Engineers remain responsible for architecture, correctness, and review.

## AI-assisted engineering workflow

1. Understand the production problem.
2. Learn the relevant tool just-in-time.
3. Design interfaces and boundaries.
4. Identify failure cases.
5. Define logs, metrics, and tests.
6. Use Codex for implementation.
7. Review architecture and code.
8. Reflect and document decisions.

## Definition of Ready

A task is ready when:

- the user or engineering problem is clear
- the expected behavior is described
- key failure cases are identified
- the affected interfaces or boundaries are known
- test expectations are clear
- out-of-scope items are explicit

## Definition of Done

A task is done when:

- the behavior is implemented as requested
- relevant tests or checks are added or updated
- logs or errors are useful for operating the behavior
- documentation is updated when the change affects architecture or workflow
- unnecessary abstractions and unrelated changes are avoided
- known limitations are documented

## Code review checklist

Ask:

- Does this solve the stated customer or engineering problem?
- Is the public API contract preserved or intentionally changed?
- Are failure modes explicit and tested?
- Are logs useful for debugging production behavior?
- Is the abstraction level appropriate for current needs?
- Does the change avoid unrelated infrastructure or technology additions?
- Are tests focused on behavior rather than implementation details?
- Is there a simpler design that keeps the same boundaries?

## When to defer a feature

Defer a feature when:

- the customer problem is unclear
- the operational need is speculative
- the feature requires infrastructure that has not been justified yet
- the current architecture would become harder to understand
- the feature is better validated by logs, benchmarks, or manual workflows first
- the team cannot define how to test or operate it

## When to introduce a new abstraction

Introduce a new abstraction when:

- multiple concrete implementations already exist or are imminent
- tests require awkward monkeypatching of concrete dependencies
- a boundary represents a real product or engineering contract
- the abstraction makes failure modes easier to reason about
- the abstraction reduces coupling without hiding important behavior

Do not introduce an abstraction only because a future feature might need it.
