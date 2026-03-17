# 11 — Composition and Modules

> **Implementation Status:** The module system described in this chapter is **planned but not yet implemented**. The current runtime (v0.1) executes a single file at a time. `import` statements are not yet supported.

## Overview

Logos programs are composed from **modules** — named units of source code, each occupying its own file. Modules encapsulate fact schemas, rules, transforms, contexts, and type declarations. The `import` statement pulls declarations from another module into the current one, enabling code reuse, namespace isolation, and controlled sharing of the semantic graph.

---

## File-Based Module Resolution

Each Logos source file is a module. The module's name is derived from its file path relative to the project root, with path separators replaced by dots and the `.logos` extension removed:

```
src/rules/voting.logos   → module name: rules.voting
src/finance/payments.logos → module name: finance.payments
stdlib/core.logos        → module name: stdlib.core
```

The project root is determined by the nearest `logos.toml` manifest file walking up from the entry point. The manifest declares the source root:

```toml
[project]
name    = "my-project"
version = "1.0.0"
src     = "src"
```

Modules located outside `src` (such as imported packages) are resolved from the `packages` directory declared in the manifest or from the global package registry.

---

## The `import` Statement

### Full Module Import

```logos
import rules.voting
```

All public declarations from `rules.voting` are available under the module's namespace:

```logos
import rules.voting

query: rules.voting.can-vote(alice)?
```

### Selective Import

```logos
import can-vote, VotingAge from rules.voting
```

Only the named declarations are imported into the current namespace. They are available without the module prefix:

```logos
import can-vote from rules.voting

query: can-vote(alice)?     // no prefix needed
```

Multiple selective imports from the same module may be listed:

```logos
import can-vote, eligible-for-jury, VotingAge from rules.voting
```

### Aliased Import

An import may be given a local alias to avoid name collisions:

```logos
import can-vote as voting-eligible from rules.voting
import can-vote as payment-eligible from finance.rules

query: voting-eligible(alice)?
query: payment-eligible(alice)?
```

### Wildcard Import

```logos
import * from rules.voting
```

All public declarations are imported without prefix. This is convenient but may cause name collisions; the compiler emits a `WildcardImportWarning` to encourage explicit imports in production code.

---

## Namespace Isolation

Without import, declarations in one module are not visible in another. Each module has its own **namespace** — a flat mapping from declaration names to their definitions.

Within a module, all declarations share the same namespace and may reference each other freely. Between modules, declarations are only shared through explicit `import`.

```logos
// module: rules.voting
rule can-vote :
    if Person.age >= VotingAge.value and Person.citizen = true
    then can-vote(Person)

// module: main
// can-vote is NOT visible here without import
import can-vote from rules.voting
// now it is visible
```

### Public vs. Private Declarations

Declarations are **public** by default and importable. A declaration marked `private` is visible only within its own module:

```logos
private rule internal-age-check :
    if Person.age >= 18 then adult(Person)

rule can-vote :
    if adult(Person) and Person.citizen = true
    then can-vote(Person)
```

`internal-age-check` and `adult` cannot be imported. Only `can-vote` is exported.

---

## Re-export

A module may re-export imported declarations, making them available to its own importers:

```logos
// module: rules.public
import can-vote from rules.voting    export can-vote
import eligible  from rules.jury     export eligible
```

Importers of `rules.public` may then import `can-vote` and `eligible` from `rules.public` without knowing their ultimate source. The provenance chain retains the original source module.

Re-export uses the `export` keyword following the import:

```logos
import can-vote from rules.voting export can-vote
// or equivalently:
export import can-vote from rules.voting
```

A module may also re-export all its imports:

```logos
export import * from rules.voting
```

---

## How the Semantic Graph Merges on Import

When module B imports from module A, the following merge occurs in the SemanticGraph:

1. **Schema merge** — type declarations from A are added to the global type registry. If a type with the same name exists, the declarations must be structurally identical or a `TypeConflictError` is raised.

2. **Fact node merge** — all `assert` statements in A produce FactNodes tagged with `source-module: A`. These nodes are added to the global SemanticGraph and are visible to rules and queries in B.

3. **Rule merge** — inference rules from A are added to the rule set. Rules from different modules may interact: a rule in B may fire on facts asserted in A, and vice versa.

4. **Context merge** — context declarations from A are merged (see §08 for conflict resolution).

5. **Transform merge** — transforms from A are available to B's callers.

The merge is additive: importing never removes facts from the graph. A module's contribution to the semantic graph persists for the lifetime of the program, even if the `import` statement is in a nested lexical scope.

---

## Version-Tagged Provenance on Imported Facts

Every FactNode contributed by an imported module carries a version tag in its provenance:

```logos
ProvenanceStep {
    fact-id    : <id>
    source     : "rules.voting:can-vote:line-10"
    module     : "rules.voting"
    version    : "1.2.3"           // from the module's manifest
    confidence : 1.0
}
```

This allows auditors to trace a derived fact back not only to the source file and line but also to the specific published version of the module that contributed it. When a module is upgraded, the new version tag distinguishes new derivations from old ones in audit logs.

---

## Circular Import Detection

Circular imports are detected during the Load stage (see §09). If module A imports module B, and module B imports module A (directly or transitively), a `CircularImportError` is raised:

```
CircularImportError: import cycle detected
    main.logos → rules.voting → rules.base → main.logos
```

The error names the full cycle path. Circular imports are always illegal; they must be resolved by extracting shared declarations into a third module that both A and B import:

```logos
// Before (circular):
// A imports B, B imports A

// After (resolved):
// shared.logos: contains the shared declarations
// A imports shared
// B imports shared
// A and B do not import each other
```

---

## Module Initialization Order

Modules are initialized in dependency order: if A imports B, then B is initialized (loaded, type-checked, asserted) before A. This is the topological order of the import DAG.

The initialization order is deterministic: for modules at the same depth (no dependency between them), alphabetical order by module name is used.

---

## Practical Patterns

### The Three-Layer Architecture

```
stdlib.core          ← standard library (types, operators, predicates)
    ↑
domain.model         ← fact schemas and base type declarations
    ↑
domain.rules         ← inference rules (imports domain.model)
    ↑
app.main             ← assertions, queries, entry point
```

Each layer imports only the layer directly below it. This ensures clear dependency direction and prevents circular imports.

### Shared Rule Libraries

```logos
// module: rules.age-eligibility
import Person from domain.model

rule adult :
    if Person.age >= 18 then adult(Person)

rule senior :
    if Person.age >= 65 then senior(Person)
```

```logos
// module: rules.voting
import adult from rules.age-eligibility

rule can-vote :
    if adult(P) and P.citizen = true then can-vote(P)
```

```logos
// module: rules.discounts
import senior from rules.age-eligibility

rule senior-discount :
    if senior(P) then P.discount-rate = 0.15
```

Both `rules.voting` and `rules.discounts` share `adult`/`senior` without duplicating the age logic.

### Test Module Pattern

```logos
// module: test.voting
import can-vote from rules.voting

assert Person : name = "TestUser", age = 30, citizen = true
    tags : [test-fixture]

assert Person : name = "Minor", age = 15, citizen = true
    tags : [test-fixture]

query: can-vote(TestUser)?   // expected: true
query: can-vote(Minor)?      // expected: false
```

Test modules import production rules and inject controlled base facts. They are never imported by production modules.

---

## Import Statement Reference

| Syntax                                          | Effect                                                     |
|-------------------------------------------------|------------------------------------------------------------|
| `import module.name`                            | Full import, namespace-qualified access                    |
| `import decl from module.name`                  | Selective import, unqualified access                       |
| `import decl as alias from module.name`         | Selective import with local alias                          |
| `import * from module.name`                     | Wildcard import, unqualified access (discouraged)          |
| `import decl from module.name export decl`      | Selective import with re-export                            |
| `export import * from module.name`              | Full re-export of entire module                            |

---

## Compiler Warnings Related to Modules

| Warning                    | Condition                                                              |
|----------------------------|------------------------------------------------------------------------|
| `WildcardImportWarning`    | `import *` used outside of a test module                              |
| `UnusedImportWarning`      | An imported name is never referenced in the importing module          |
| `ShadowedImportWarning`    | A local declaration has the same name as an imported declaration       |
| `ContextConflictWarning`   | Two imported modules declare a context with the same name differently |
| `VersionSkewWarning`       | An imported module's version does not match the manifest constraint   |

---

## Summary

- Modules map one-to-one to source files; names derive from file paths relative to the project root.
- `import` selectively or fully imports declarations across module boundaries.
- Declarations are public by default; `private` restricts visibility to the declaring module.
- Re-export allows a module to act as a facade over deeper dependencies.
- On import, the semantic graph merges additively: schemas, facts, rules, contexts, and transforms all join the global graph.
- Imported facts carry version-tagged provenance for auditability.
- Circular imports are detected at load time and are always illegal; resolve them with a shared base module.
