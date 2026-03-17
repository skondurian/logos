# Logos Language Specification — Chapter 2: Lexical Structure

## 1. Character Set

Logos source files are encoded in **UTF-8**. The full Unicode character set is permitted in string literals and comments. Identifiers are restricted to a subset of Unicode as described in Section 3.

Line endings may be LF (`\n`) or CRLF (`\r\n`); the lexer normalizes both to LF. A file that ends without a trailing newline is valid.

## 2. Whitespace and Indentation

Logos is **indentation-significant**. Indentation delimits blocks; explicit block delimiters (`{` `}`) are not used except inside value literals.

### 2.1 Indentation Rules

- Indentation must be **spaces only** (tab characters are a lexical error).
- The indentation unit within a file must be consistently either **2 spaces** or **4 spaces**. Mixing is a lexical error.
- The indentation level of the first indented line in a file establishes the indentation unit for that file.
- A **BLOCK-START** token is emitted when indentation increases by exactly one unit.
- A **BLOCK-END** token is emitted for each level decrease.
- A **NEWLINE** token is emitted at the end of each logical line.

### 2.2 Blank Lines

Blank lines (lines containing only whitespace) are ignored by the lexer. They do not affect block structure.

### 2.3 Indentation Examples

```logos
// 2-space indentation
Person (Entity):  // BLOCK-START follows the colon
  name: HumanName   // indented 2 spaces
  age: Duration

Animal (Entity):  // back to column 0 → previous BLOCK-END, new BLOCK-START
  lifespan: Duration
```

## 3. Line Continuation

A logical line may be continued on the next physical line by ending the physical line with a backslash `\` immediately before the newline. The continuation line may be indented to any column; leading whitespace on continuation lines is consumed.

```logos
find P where \
  age of P > 18 years \
  nationality of P == "American"
```

Alternatively, any open bracket `(`, `[`, or `{` suspends newline significance until the matching close bracket. This is the preferred style for multi-line expressions:

```logos
age of alice := 30 years [
  confidence: 0.95
  source: "passport"
]
```

## 4. Comments

Logos supports only **line comments**. A line comment begins with `//` and extends to the end of the physical line. There are no block comments.

```logos
// This is a comment
age of alice := 30 years  // inline comment
```

Comment text is ignored by the parser. Comments may contain any Unicode characters.

**Rationale:** Block comments create ambiguity in indentation-significant languages. Line comments are unambiguous and sufficient.

## 5. Identifiers

### 5.1 Preferred Style: kebab-case

Logos **strongly prefers kebab-case** for all identifiers: lowercase words separated by hyphens. This matches the natural reading of semantic bindings as English-like prose.

```logos
age-of-majority
first-name
can-vote
is-citizen
```

### 5.2 Permitted Style: camelCase

camelCase identifiers are permitted for compatibility with systems that use camelCase conventions (e.g., JSON field names, external APIs).

```logos
firstName
ageOfMajority
```

### 5.3 Type Names: PascalCase

Type names use **PascalCase** by convention. This distinguishes types from values and predicates.

```logos
HumanName
Person
Employee
FinancialInstrument
```

### 5.4 Variables: UPPERCASE or PascalCase

In inference rule conditions, **free variables** are conventionally written in UPPERCASE or PascalCase to visually distinguish them from bound entity names. This is a convention, not a syntactic requirement; the parser uses scoping rules to determine what is a variable.

```logos
can-vote(P) if:
  age of P >= 18 years
  nationality of P == "American"
```

### 5.5 Identifier Grammar

```
identifier      ::= identifier-start identifier-continue*
identifier-start ::= letter | '_'
identifier-continue ::= letter | digit | '-' | '_'
letter          ::= [a-zA-Z] | unicode-letter
digit           ::= [0-9]
```

A hyphen is a valid identifier character when it appears between two identifier characters. A leading or trailing hyphen is not valid in an identifier (it would be parsed as a unary or binary minus operator).

### 5.6 Identifier Namespacing

Identifiers in Logos are not globally unique; they are resolved within a **semantic scope** (see Chapter 8). However, within a single file, all top-level identifiers are in the file's default namespace.

## 6. Keywords

The following words are **reserved keywords** and may not be used as identifiers:

| Keyword | Usage |
|---------|-------|
| `type` | Type declaration |
| `IS-A` | Type inheritance |
| `fields` | Field block in type declaration |
| `if` | Rule condition block |
| `not` | Negation-as-failure |
| `find` | Query expression |
| `where` | Query condition block |
| `retract` | Fact retraction |
| `confidence` | Confidence annotation key |
| `source` | Provenance annotation key |
| `asserted-at` | Provenance timestamp key |
| `asserted-by` | Provenance agent key |
| `import` | Module import *(reserved, not yet implemented)* |
| `module` | Module declaration *(reserved)* |
| `and` | Explicit conjunction in conditions |
| `or` | Explicit disjunction in conditions |
| `true` | Boolean literal |
| `false` | Boolean literal |
| `absolute` | Confidence shorthand for certainty |

Keywords are case-sensitive. `Type` and `TYPE` are valid identifiers; `type` is not.

## 7. Literals

### 7.1 Integer Literals

Integer literals are sequences of decimal digits, optionally separated by underscores for readability. Underscores may appear between digits only, not at the start or end.

```logos
0
42
1_000_000
67_000_000
```

Hexadecimal literals use the `0x` prefix:

```logos
0xFF
0xDEAD_BEEF
```

Binary literals use the `0b` prefix:

```logos
0b1010_1101
```

The type of an integer literal is inferred from context. In the absence of context, it defaults to `Integer`.

### 7.2 Float Literals

Float literals include a decimal point and an optional exponent. The decimal point must be surrounded by digits on both sides.

```logos
3.14
2.718_281_828
1.0e10
6.022e23
1.5e-3
```

A trailing `%` suffix converts a float to a percentage (equivalent to dividing by 100 and annotating as a ratio):

```logos
1.5%    // equivalent to 0.015 as a Ratio
99.9%
```

### 7.3 String Literals

String literals are enclosed in **double quotes** only. Single quotes are not string delimiters.

```logos
"Alice"
"New York"
"Hello, world!"
```

Escape sequences within strings:

| Escape | Meaning |
|--------|---------|
| `\"` | Double quote |
| `\\` | Backslash |
| `\n` | Newline |
| `\t` | Tab |
| `\r` | Carriage return |
| `\uXXXX` | Unicode code point (4 hex digits) |
| `\UXXXXXXXX` | Unicode code point (8 hex digits) |

Multi-line strings use triple-double-quote delimiters:

```logos
description of project := """
  This is a multi-line
  string literal.
  Leading indentation is stripped.
"""
```

In a triple-quoted string, the indentation of the closing `"""` determines how much leading whitespace is stripped from each line.

### 7.4 Duration Literals

Duration literals are a first-class literal type in Logos. They consist of an integer or float quantity followed by a duration unit keyword.

```
duration-literal ::= number duration-unit
duration-unit    ::= 'years' | 'year' | 'months' | 'month' | 'weeks' | 'week'
                   | 'days' | 'day' | 'hours' | 'hour' | 'minutes' | 'minute'
                   | 'seconds' | 'second' | 'milliseconds' | 'millisecond'
```

Singular and plural forms are equivalent:

```logos
30 years
1 year
6 months
2 weeks
90 days
24 hours
45 minutes
30 seconds
500 milliseconds
```

Duration literals can be composed with the `+` operator:

```logos
1 year + 6 months
30 years + 3 months + 12 days
```

Duration arithmetic is **calendar-aware**: adding `1 month` to January 31 yields the last day of February, not February 31 (which does not exist). Duration arithmetic is described fully in Chapter 3.

### 7.5 Date Literals

Date literals follow ISO 8601 format with a `@` prefix to distinguish them from identifiers:

```logos
@2026-03-16
@2026-03-16T14:30:00Z
@2026-03-16T14:30:00+05:30
```

### 7.6 Boolean Literals

```logos
true
false
```

### 7.7 Entity Reference Literals

An unquoted identifier used as a value in a binding position is an **entity reference** — a reference to a named entity in the knowledge graph:

```logos
employer of alice := acme-corp   // acme-corp is an entity reference
```

This is distinct from a string literal `"acme-corp"` (which is a text value, not an entity reference).

### 7.8 Structured Value Literals (Records)

Record literals use brace syntax:

```logos
name of alice := { first: "Alice", last: "Smith" }
address of alice := {
  street: "123 Main St"
  city: "Springfield"
  state: "IL"
  zip: "62701"
}
```

Record literal keys are identifiers; values are any literal or entity reference.

### 7.9 List Literals

```logos
aliases of alice := ["Ali", "Ally", "A. Smith"]
scores of alice  := [98, 95, 87, 92]
```

Lists are ordered and may be heterogeneous (though homogeneous lists are preferred for type safety).

### 7.10 Set Literals

```logos
permissions of alice := #{"read", "write", "execute"}
```

The `#{}` syntax denotes an unordered set. Duplicate elements are silently deduplicated.

## 8. Operators

### 8.1 Comparison Operators

| Operator | Meaning |
|----------|---------|
| `==` | Equal |
| `!=` | Not equal |
| `<` | Less than |
| `<=` | Less than or equal |
| `>` | Greater than |
| `>=` | Greater than or equal |

Duration and numeric values support all comparison operators. Text values support `==` and `!=`. Entity references support `==` and `!=` (identity comparison).

### 8.2 Arithmetic Operators

| Operator | Meaning |
|----------|---------|
| `+` | Addition (numeric or duration) |
| `-` | Subtraction (numeric or duration) |
| `*` | Multiplication (numeric) |
| `/` | Division (numeric) |
| `%` | Modulo (numeric) |

### 8.3 Logical Operators

| Operator | Meaning |
|----------|---------|
| `and` | Logical conjunction (same as newline in a condition block) |
| `or` | Logical disjunction (creates alternative rule branches) |
| `not` | Negation-as-failure |

### 8.4 Binding Operator

| Operator | Meaning |
|----------|---------|
| `:=` | Semantic binding assertion |

### 8.5 Fallback Chain Operator

| Operator | Meaning |
|----------|---------|
| `\|` | Fallback: use left operand if bound, otherwise right operand |

```logos
display-name of alice := (nickname of alice | name of alice | "Unknown")
```

### 8.6 Type Operators

| Operator | Meaning |
|----------|---------|
| `(Parent)` | Type inheritance — parent list in parens after type name |
| `::` | Type ascription — **Planned (not yet implemented)** |

```logos
// Planned syntax — not yet implemented:
alice :: Person
```

## 9. Delimiters

| Delimiter | Usage |
|-----------|-------|
| `(` `)` | Grouping; rule head parameters |
| `[` `]` | Annotation blocks; list literals |
| `{` `}` | Record literals |
| `#{` `}` | Set literals |
| `:` | Field separator in type declarations and record literals |
| `,` | Element separator in list and set literals |
| `//` | Line comment start |
| `\` | Line continuation |

## 10. Numeric Separators

Underscores may appear within numeric literals as visual separators:

```logos
1_000_000
3.141_592_653
0xFF_AA_BB_CC
```

Underscores are stripped during lexing and have no semantic significance.

## 11. Significance of Identifier Casing

While casing conventions are not enforced by the parser, the **standard toolchain** (formatter, linter, language server) will warn on violations:

| Convention | Form | Example |
|------------|------|---------|
| Types | PascalCase | `HumanName`, `FinancialInstrument` |
| Entities | kebab-case | `alice`, `acme-corp` |
| Predicates/fields | kebab-case | `age-of-majority`, `first-name` |
| Variables in rules | UPPERCASE | `P`, `PERSON`, `AGE` |
| Rule names | kebab-case | `can-vote`, `is-eligible` |
