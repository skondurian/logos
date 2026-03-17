# 12 — Standard Library Sketch

## Overview

The Logos standard library (`stdlib.core`) provides the built-in types, predicates, arithmetic operators, string operations, set and list operations, IO primitives, and mathematical functions that every Logos program can rely on without explicit import. This document sketches the intended contents of the standard library, with enough precision to guide both the language implementor and the self-hosting bootstrap compiler.

All declarations in this chapter live in the implicit module `stdlib.core`. They are available in every Logos program without an `import` statement. Programs may shadow any stdlib name with a local declaration; the stdlib name is then accessible via explicit qualification: `stdlib.core.before`.

---

## Built-in Types

### Primitive Types

| Type       | Description                                      | Literal form           |
|------------|--------------------------------------------------|------------------------|
| `Boolean`  | Truth value                                      | `true`, `false`        |
| `Integer`  | Arbitrary-precision signed integer               | `0`, `-42`, `1_000_000`|
| `Number`   | Arbitrary-precision decimal (rational)           | `3.14`, `-0.5`         |
| `Text`     | Unicode string                                   | `"hello"`, `""`        |
| `Symbol`   | Interned identifier (compile-time constant)      | `:ok`, `:error`        |
| `Bytes`    | Opaque byte sequence                             | `0x[deadbeef]`         |

All numeric types support exact arithmetic by default. Floating-point approximation is available via `Float32` and `Float64` for performance-sensitive computations.

### Composite Types

```logos
type Maybe<T>    : absent | present(T)
type Set<T>      : unordered collection of T, no duplicates
type List<T>     : ordered sequence of T, duplicates allowed
type Map<K, V>   : key-to-value mapping, unique keys
type Tuple<...>  : fixed-length heterogeneous product type
type Relation<T, U> : Set<Tuple<T, U>>
```

### Rich Domain Types

These types are semantically richer than primitives and carry built-in validation and domain-specific operations.

#### `HumanName`

```logos
type HumanName :
    given   : Text
    family  : Text
    middle  : Maybe<Text>
    prefix  : Maybe<Text>     // "Dr.", "Prof."
    suffix  : Maybe<Text>     // "Jr.", "III"
```

Operations:
```logos
name.full          // → Text: "John A. Smith"
name.initials      // → Text: "J.A.S."
name.formal        // → Text: "Smith, John A."
name.given         // → Text: "John"
name.family        // → Text: "Smith"
```

#### `Duration`

```logos
type Duration :
    nanoseconds : Integer   // canonical internal representation
```

Literal forms:
```logos
5 seconds
3 minutes
2 hours
7 days
1 week
6 months     // calendar-aware; 30.4375 days on average
1 year       // calendar-aware; 365.25 days on average
500 ms       // milliseconds
100 us       // microseconds
```

#### `Timestamp`

```logos
type Timestamp :
    epoch-nanoseconds : Integer    // nanoseconds since Unix epoch (UTC)
    timezone : Maybe<Timezone>     // if absent, interpreted as UTC
```

Literal form:
```logos
2026-03-16                   // date only (midnight UTC)
2026-03-16T09:30:00Z         // RFC 3339
2026-03-16T09:30:00-08:00    // with offset
```

#### `GeoLocation`

```logos
type GeoLocation :
    latitude  : Number   // degrees, -90 to 90
    longitude : Number   // degrees, -180 to 180
    altitude  : Maybe<Number>  // metres above sea level
```

Literal form:
```logos
geo(47.6062, -122.3321)           // Seattle
geo(51.5074, -0.1278, 11.0)       // London, 11m altitude
```

#### `URL`

```logos
type URL :
    scheme   : Text
    host     : Text
    port     : Maybe<Integer>
    path     : Text
    query    : Maybe<Text>
    fragment : Maybe<Text>
```

Parsed automatically from string literals:
```logos
url("https://example.com/path?q=1#section")
```

---

## Built-in Predicates

### Temporal Predicates (`Duration`, `Timestamp`)

```logos
before(a: Timestamp, b: Timestamp) → Boolean
after(a: Timestamp, b: Timestamp)  → Boolean
between(t: Timestamp, start: Timestamp, end: Timestamp) → Boolean
within(t: Timestamp, window: Duration) → Boolean   // t is within `window` of now
elapsed(since: Timestamp) → Duration               // time since a timestamp
at-most(d: Duration, limit: Duration) → Boolean
at-least(d: Duration, floor: Duration) → Boolean
```

Examples:
```logos
before(alice.birth-date, 2000-01-01)
within(last-login, 30 days)
elapsed(contract.start) >= 1 year
```

### Geographic Predicates (`GeoLocation`)

```logos
distance(a: GeoLocation, b: GeoLocation) → Number      // metres, great-circle
within-radius(point: GeoLocation, center: GeoLocation, radius: Number) → Boolean
within-region(point: GeoLocation, region: GeoRegion) → Boolean
near(a: GeoLocation, b: GeoLocation) → Boolean          // within 1 km (configurable)
far-from(a: GeoLocation, b: GeoLocation) → Boolean      // more than 50 km (configurable)
same-city(a: GeoLocation, b: GeoLocation) → Boolean
same-country(a: GeoLocation, b: GeoLocation) → Boolean
```

Examples:
```logos
within-radius(user.location, store.location, 5000)   // within 5 km
far-from(transaction.location, account.home-location)
same-country(visitor.location, site.host-location)
```

---

## Arithmetic Operators

### On `Number` and `Integer`

| Operator | Meaning           | Example             |
|----------|-------------------|---------------------|
| `+`      | Addition          | `a + b`             |
| `-`      | Subtraction       | `a - b`             |
| `*`      | Multiplication    | `a * b`             |
| `/`      | Division (exact)  | `a / b`             |
| `//`     | Integer division  | `a // b`            |
| `mod`    | Modulo            | `a mod b`           |
| `**`     | Exponentiation    | `a ** b`            |
| `-`      | Negation (unary)  | `-a`                |
| `abs`    | Absolute value    | `abs(a)`            |

Division by zero raises a `DivisionByZero` error at evaluation time; it is not a type error.

### On `Duration`

```logos
5 days + 3 hours              // → Duration: 5 days 3 hours
2 weeks - 1 day               // → Duration: 13 days
3 * 1 hour                    // → Duration: 3 hours
duration / 2                  // → Duration: half the duration
duration1 / duration2         // → Number: ratio
Timestamp + Duration          // → Timestamp: shifted forward
Timestamp - Duration          // → Timestamp: shifted backward
Timestamp - Timestamp         // → Duration: elapsed time
```

### Comparison Operators (all numeric types)

```logos
= != < <= > >=
```

All comparison operators return `Boolean` and work on `Number`, `Integer`, `Duration`, and `Timestamp`. `Timestamp` comparison uses chronological order.

---

## String Operations on `Text`

```logos
length(t: Text) → Integer                          // character count (Unicode codepoints)
bytes(t: Text) → Integer                           // UTF-8 byte count
concat(a: Text, b: Text) → Text                    // concatenation
concat-all(parts: List<Text>) → Text               // join without separator
join(parts: List<Text>, sep: Text) → Text          // join with separator
split(t: Text, sep: Text) → List<Text>
contains(t: Text, sub: Text) → Boolean
starts-with(t: Text, prefix: Text) → Boolean
ends-with(t: Text, suffix: Text) → Boolean
index-of(t: Text, sub: Text) → Maybe<Integer>      // 0-based, absent if not found
slice(t: Text, start: Integer, end: Integer) → Text
upper-case(t: Text) → Text
lower-case(t: Text) → Text
trim(t: Text) → Text                               // remove leading/trailing whitespace
trim-start(t: Text) → Text
trim-end(t: Text) → Text
replace(t: Text, from: Text, to: Text) → Text
matches(t: Text, pattern: Text) → Boolean          // pattern is a glob; use regex() for regex
regex-matches(t: Text, pattern: Text) → Boolean    // pattern is a PCRE regex
to-integer(t: Text) → Maybe<Integer>
to-number(t: Text) → Maybe<Number>
format(template: Text, values: Map<Text, Text>) → Text
```

String interpolation is a first-class syntax:

```logos
let msg = "Hello, {user.name}! You have {count} messages."
```

---

## Set Operations

`Set<T>` is an unordered collection with no duplicates. Equality of elements uses structural equality.

```logos
member-of(x: T, s: Set<T>) → Boolean
not-member-of(x: T, s: Set<T>) → Boolean
union(a: Set<T>, b: Set<T>) → Set<T>
intersection(a: Set<T>, b: Set<T>) → Set<T>
difference(a: Set<T>, b: Set<T>) → Set<T>        // elements in a but not b
subset-of(a: Set<T>, b: Set<T>) → Boolean
superset-of(a: Set<T>, b: Set<T>) → Boolean
disjoint(a: Set<T>, b: Set<T>) → Boolean
count(s: Set<T>) → Integer
empty(s: Set<T>) → Boolean
singleton(x: T) → Set<T>
to-list(s: Set<T>) → List<T>                     // arbitrary order
to-sorted-list(s: Set<T>) → List<T>              // requires T to be Orderable
insert(s: Set<T>, x: T) → Set<T>                 // immutable insert
remove(s: Set<T>, x: T) → Set<T>                 // immutable remove
```

Set literals:
```logos
let s = {1, 2, 3}
let empty-set = Set<Integer> {}
```

---

## List Operations

`List<T>` is an ordered sequence that allows duplicates.

```logos
length(l: List<T>) → Integer
head(l: List<T>) → Maybe<T>               // first element
tail(l: List<T>) → List<T>               // all but first
last(l: List<T>) → Maybe<T>
init(l: List<T>) → List<T>               // all but last
at(l: List<T>, i: Integer) → Maybe<T>    // 0-based index
concat(a: List<T>, b: List<T>) → List<T>
reverse(l: List<T>) → List<T>
sort(l: List<T>) → List<T>               // requires T Orderable
sort-by(l: List<T>, key: T → K) → List<T>
map(l: List<T>, f: T → U) → List<U>
filter(l: List<T>, pred: T → Boolean) → List<T>
fold(l: List<T>, init: U, f: (U, T) → U) → U     // left fold (reduce)
fold-right(l: List<T>, init: U, f: (T, U) → U) → U
any(l: List<T>, pred: T → Boolean) → Boolean
all(l: List<T>, pred: T → Boolean) → Boolean
find-first(l: List<T>, pred: T → Boolean) → Maybe<T>
flat-map(l: List<T>, f: T → List<U>) → List<U>
zip(a: List<T>, b: List<U>) → List<Tuple<T, U>>
take(l: List<T>, n: Integer) → List<T>
drop(l: List<T>, n: Integer) → List<T>
take-while(l: List<T>, pred: T → Boolean) → List<T>
drop-while(l: List<T>, pred: T → Boolean) → List<T>
to-set(l: List<T>) → Set<T>              // deduplicates
```

List literals:
```logos
let nums = [1, 2, 3, 4, 5]
let empty-list = List<Integer> []
```

---

## Map Operations

```logos
get(m: Map<K, V>, k: K) → Maybe<V>
put(m: Map<K, V>, k: K, v: V) → Map<K, V>       // immutable insert/update
remove(m: Map<K, V>, k: K) → Map<K, V>
contains-key(m: Map<K, V>, k: K) → Boolean
keys(m: Map<K, V>) → Set<K>
values(m: Map<K, V>) → List<V>
entries(m: Map<K, V>) → List<Tuple<K, V>>
map-values(m: Map<K, V>, f: V → W) → Map<K, W>
filter-keys(m: Map<K, V>, pred: K → Boolean) → Map<K, V>
count(m: Map<K, V>) → Integer
merge(a: Map<K, V>, b: Map<K, V>) → Map<K, V>    // b wins on key collision
```

Map literals:
```logos
let m = { "name" → "Alice", "age" → "30" }
let empty-map = Map<Text, Integer> {}
```

---

## IO Primitives

IO is restricted to designated IO blocks. Transforms and rules may not perform IO; only the program's top-level `main` block and explicitly marked `io` procedures may do so.

```logos
io procedure read-file [path: Text] → Maybe<Text> :
    // reads entire file as UTF-8 text; absent if file not found or unreadable

io procedure write-output [text: Text] :
    // writes text to standard output; no newline appended

io procedure write-line [text: Text] :
    // writes text + newline to standard output

io procedure write-file [path: Text, content: Text] :
    // writes content to file, creating or overwriting; raises IOError on failure

io procedure read-line [] → Maybe<Text> :
    // reads one line from standard input; absent on EOF

io procedure stderr [text: Text] :
    // writes text to standard error
```

IO in the main block:

```logos
main :
    let src = read-file "/etc/logos/config.logos"
    match src :
        absent  → write-line "Config not found"
        present(text) →
            write-output "Loaded: "
            write-line text
```

IO is intentionally minimal. Logos is a logic/inference language; extensive IO is delegated to the host environment via FFI or shell orchestration.

---

## Math Functions

```logos
floor(x: Number) → Integer
ceiling(x: Number) → Integer
round(x: Number) → Integer                  // round half to even (banker's rounding)
truncate(x: Number) → Integer              // toward zero
sqrt(x: Number) → Number                   // exact rational approximation; raises on negative
cbrt(x: Number) → Number
pow(base: Number, exp: Number) → Number
log(x: Number) → Number                    // natural log; raises on non-positive
log2(x: Number) → Number
log10(x: Number) → Number
exp(x: Number) → Number                    // e^x
sin(x: Number) → Number                    // radians
cos(x: Number) → Number
tan(x: Number) → Number
asin(x: Number) → Number
acos(x: Number) → Number
atan(x: Number) → Number
atan2(y: Number, x: Number) → Number
pi   : Number   // 3.14159265358979323846...
e    : Number   // 2.71828182845904523536...
min(a: T, b: T) → T                        // requires T Orderable
max(a: T, b: T) → T
clamp(x: T, lo: T, hi: T) → T             // min(max(x, lo), hi)
between(x: T, lo: T, hi: T) → Boolean     // lo <= x <= hi
sign(x: Number) → Integer                  // -1, 0, or 1
gcd(a: Integer, b: Integer) → Integer
lcm(a: Integer, b: Integer) → Integer
```

---

## Type Conversion

```logos
to-text(x: T) → Text              // default text representation of any type
to-integer(x: Number) → Integer   // truncates; raises on non-finite
to-number(x: Integer) → Number
to-boolean(x: Integer) → Boolean  // 0 → false, else true
parse-integer(t: Text) → Maybe<Integer>
parse-number(t: Text) → Maybe<Number>
parse-timestamp(t: Text) → Maybe<Timestamp>  // RFC 3339 / ISO 8601
parse-url(t: Text) → Maybe<URL>
```

---

## Identity and Equality

```logos
equal(a: T, b: T) → Boolean              // structural equality
not-equal(a: T, b: T) → Boolean
identical(a: T, b: T) → Boolean          // reference identity (only for FactNodes)
type-of(x: T) → TypeDescriptor
is-absent(x: Maybe<T>) → Boolean
is-present(x: Maybe<T>) → Boolean
unwrap(x: Maybe<T>) → T                  // raises AbsentError if absent
unwrap-or(x: Maybe<T>, default: T) → T
```

---

## Self-Hosting Bootstrap Notes

The following subset is the minimum required for the bootstrap compiler (written in Logos itself) to parse, type-check, and emit code:

| Category          | Required operations                                                  |
|-------------------|----------------------------------------------------------------------|
| Text              | `concat`, `split`, `length`, `slice`, `contains`, `to-integer`     |
| List              | `map`, `filter`, `fold`, `head`, `tail`, `length`, `at`            |
| Set               | `member-of`, `union`, `insert`, `count`                            |
| Map               | `get`, `put`, `keys`, `entries`                                    |
| Maybe             | `is-absent`, `is-present`, `unwrap`, `unwrap-or`                   |
| Integer/Number    | `+`, `-`, `*`, `//`, `mod`, `=`, `<`, `>`, `abs`                  |
| IO                | `read-file`, `write-output`, `write-line`, `stderr`                |
| Type conversion   | `to-text`, `parse-integer`                                         |

The bootstrap compiler need not implement geo predicates, math functions beyond basic arithmetic, or rich domain types (HumanName, GeoLocation, URL). These are added in subsequent passes once the compiler is self-hosted.

---

## Summary

- `stdlib.core` is implicitly available in all Logos programs.
- Built-in types include primitives (`Boolean`, `Integer`, `Number`, `Text`), composites (`Set`, `List`, `Map`, `Maybe`), and rich domain types (`HumanName`, `Duration`, `Timestamp`, `GeoLocation`, `URL`).
- Temporal predicates (`before`, `after`, `within`) and geographic predicates (`distance`, `within-radius`) operate on the domain types.
- Arithmetic, string, set, list, and map operations follow a pure functional style; all operations return new values.
- IO is gated to explicitly marked `io` procedures and the top-level `main` block.
- The bootstrap subset is a small, well-defined core sufficient for a self-hosting compiler.
