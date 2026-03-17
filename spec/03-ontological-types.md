# Logos Language Specification — Chapter 3: Ontological Types

## 1. Overview

Logos's type system is **ontological**: types represent categories of real-world entities, not memory layouts or computational structures. A type in Logos is a named set of entities with a shared set of properties (fields), and types are organized into a **partial order (IS-A lattice)** that expresses subtype relationships.

The type system serves two purposes:

1. **Documentation and constraint** — Types describe what fields an entity may have, enabling editors and linters to catch errors.
2. **Inference** — The IS-A lattice enables inference rules that apply to a type to automatically apply to all subtypes.

The type system is **open**: you can always declare new types without modifying existing ones. This is the open-world design principle applied to the type level.

## 2. Type Declaration Syntax

```
TypeDecl     ::= 'type' TypeName ('IS-A' TypeName (',' TypeName)*)? NEWLINE
                 BLOCK-START TypeBody BLOCK-END

TypeBody     ::= FieldsBlock?

FieldsBlock  ::= 'fields' ':' NEWLINE
                 BLOCK-START FieldDecl+ BLOCK-END

FieldDecl    ::= FieldName ':' TypeExpr NEWLINE

TypeName     ::= PascalCase identifier
FieldName    ::= kebab-case identifier
TypeExpr     ::= TypeName | TypeName '?' | TypeName '+' | '[' TypeExpr ']' | TypeExpr '|' TypeExpr
```

### 2.1 Minimal Type Declaration

A type with no parent and no fields:

```logos
type Tag
```

### 2.2 Type with Parent

```logos
type Person IS-A Entity
```

### 2.3 Type with Multiple Parents (Multiple Inheritance)

```logos
type Employee IS-A Person, OrganizationMember
```

### 2.4 Type with Fields

```logos
type Person IS-A Entity
  fields:
    name: HumanName
    age: Duration
    nationality: Text
```

### 2.5 Full Example with Nested Hierarchy

```logos
type LegalEntity IS-A Entity
  fields:
    legal-name: Text
    jurisdiction: Text

type Organization IS-A LegalEntity
  fields:
    founded: Duration
    headquarters: Address

type Corporation IS-A Organization
  fields:
    ticker-symbol: Text?
    public: Boolean

type Person IS-A LegalEntity
  fields:
    name: HumanName
    date-of-birth: Date?
    nationality: Text

type Employee IS-A Person
  fields:
    employer: Organization
    title: Text
    start-date: Date
    salary: Money?

type Executive IS-A Employee
  fields:
    reports-to: Executive?
    budget-authority: Money?
```

## 3. Built-in Root Types

Logos provides a set of built-in types that are the roots of the type lattice. All user-defined types must eventually trace their IS-A ancestry to one of these roots.

### 3.1 Entity

`Entity` is the universal root type. Every named thing in the Logos knowledge graph is an `Entity`. Entities have a unique identifier within their namespace. `Entity` itself has no built-in fields; all fields come from subtypes.

```logos
// All of these are entities
alice :: Person   // alice is of type Person (which IS-A Entity)
acme-corp :: Corporation
```

### 3.2 Number

`Number` is the root of the numeric type hierarchy.

| Type | Description |
|------|-------------|
| `Number` | Abstract numeric root |
| `Integer` | Arbitrary-precision integer |
| `Float` | IEEE 754 double-precision float |
| `Ratio` | Exact rational number (numerator/denominator) |
| `Money` | Currency-denominated amount |
| `Percentage` | A `Ratio` constrained to [0, 1], displayed as % |

```logos
type Money IS-A Number
  fields:
    amount: Ratio
    currency: CurrencyCode

type Percentage IS-A Ratio
```

Numbers support the standard arithmetic operators and all comparison operators.

### 3.3 Text

`Text` is the root of the string/character type hierarchy.

| Type | Description |
|------|-------------|
| `Text` | Arbitrary Unicode string |
| `HumanName` | Structured personal name (see Section 3.4) |
| `Identifier` | A machine-readable identifier (no spaces) |
| `URL` | A well-formed URL |
| `CurrencyCode` | ISO 4217 currency code (e.g., `"USD"`, `"EUR"`) |

### 3.4 HumanName

`HumanName` is a structured type representing a personal name. It deserves special treatment because names are culturally complex: different cultures order components differently, some people have only one name, names may include honorifics, etc.

```logos
type HumanName IS-A Text
  fields:
    honorific: Text?          // "Dr.", "Prof.", "Mr.", "Ms."
    given-names: [Text]+      // list of given/first names
    family-name: Text?        // may be absent (some cultures)
    generation-suffix: Text?  // "Jr.", "III", "Sr."
    preferred: Text?          // preferred form of address
```

**HumanName literal syntax:**

```logos
// Short form (auto-parsed as given + family)
name of alice := { first: "Alice", last: "Smith" }

// Full form
name of alice := {
  honorific: "Dr."
  given-names: ["Alice", "Marie"]
  family-name: "Smith-Jones"
  generation-suffix: "Jr."
  preferred: "Ali"
}
```

**Rendering:** The `HumanName` type has a built-in `render` predicate that produces a display string using locale-appropriate name ordering conventions.

### 3.5 Duration

`Duration` represents a span of time. Duration literals are a first-class syntactic form (see Chapter 2, Section 7.4).

| Type | Description |
|------|-------------|
| `Duration` | Abstract duration root |
| `CalendarDuration` | Expressed in calendar units (years, months, days) |
| `ClockDuration` | Expressed in clock units (hours, minutes, seconds) |

**Duration Arithmetic:**

Duration values support `+` and `-` operators. The rules for calendar arithmetic are:

- **Year addition**: Add to the year component. If the resulting month-day does not exist, clamp to the last day of the month.
- **Month addition**: Add to the month component, carrying into years as needed. Apply the same day-of-month clamping rule.
- **Day/hour/minute/second addition**: Exact arithmetic.

```logos
// Duration arithmetic examples
age-threshold := 18 years
voting-cutoff := 18 years + 0 months  // same thing

// Adding durations
total-term := 4 years + 6 months
extended-term := total-term + 1 year  // 5 years + 6 months
```

**Duration comparison:**

Durations are converted to a canonical form for comparison. For comparisons involving calendar durations (years/months), the comparison is made in terms of days, using average day counts (365.25 days/year, 30.4375 days/month):

```logos
age of alice >= 18 years   // compares in days: age-in-days >= 6574
```

**Age computation:**

The built-in `age-as-of(entity, date)` function computes a Duration by subtracting the entity's `date-of-birth` from the given date, using calendar-aware subtraction.

### 3.6 Boolean

`Boolean` has exactly two values: `true` and `false`. Booleans are the result of comparison operators and logical operators.

### 3.7 Date

`Date` represents a calendar date (year, month, day). `DateTime` includes time-of-day and timezone.

| Type | Description |
|------|-------------|
| `Date` | ISO 8601 calendar date |
| `DateTime` | ISO 8601 date and time with timezone |
| `DateRange` | A `Date` interval (start inclusive, end exclusive) |

Date literals use the `@` prefix:

```logos
born-on of alice := @1995-06-15
```

Date arithmetic with Duration produces a new Date:

```logos
// Date + Duration → Date
next-birthday := @1995-06-15 + 30 years  // @2025-06-15
```

### 3.8 Set and List

| Type | Description |
|------|-------------|
| `List` | Ordered, indexed sequence of values |
| `Set` | Unordered collection of unique values |

Type expressions for collections:

```logos
type Person IS-A Entity
  fields:
    aliases: [Text]        // List of Text
    permissions: #{Text}   // Set of Text
```

## 4. Type Expressions

A type expression appears in field declarations and type ascriptions. Type expression forms:

| Expression | Meaning |
|------------|---------|
| `T` | Exactly type T |
| `T?` | Optional: T or absent |
| `T+` | Non-empty list of T |
| `[T]` | Possibly-empty list of T |
| `#{T}` | Set of T |
| `T \| U` | Union: T or U |
| `T & U` | Intersection: both T and U |

```logos
type Document IS-A Entity
  fields:
    title: Text
    author: Person | Organization   // union type
    tags: [Text]                    // list
    created: Date
    reviewed-by: Person?            // optional
    sections: Section+              // non-empty list
```

## 5. The IS-A Lattice

### 5.1 Multiple Inheritance

Logos supports **multiple inheritance** in the IS-A lattice. An entity can belong to multiple types, and a type can have multiple parent types.

```logos
type Person IS-A Entity
type Employee IS-A Person
type Citizen IS-A Person
  fields:
    country: Text

// A person can be both Employee and Citizen
alice :: Employee
alice :: Citizen
```

When a type has multiple parents, it inherits all fields from all parents. If two parents declare a field with the same name, it is an error unless both declarations are identical (same type expression).

### 5.2 Diamond Inheritance

When the same ancestor type appears via multiple inheritance paths (the "diamond problem"), Logos uses **C3 linearization** to determine field resolution order. In practice, because field types must be consistent, diamond inheritance rarely causes conflicts.

```logos
type Named IS-A Entity
  fields:
    name: Text

type Person IS-A Named
  fields:
    age: Duration

type Employee IS-A Named
  fields:
    employer: Organization

// Worker inherits `name` from Named (once, via both Person and Employee)
// and gets both `age` and `employer`
type Worker IS-A Person, Employee
```

### 5.3 IS-A Lattice Diagram Example

```
Entity
├── LegalEntity
│   ├── Person
│   │   ├── Employee
│   │   │   └── Executive
│   │   └── Citizen
│   └── Organization
│       ├── Corporation
│       └── NonProfit
├── Number
│   ├── Integer
│   ├── Float
│   ├── Ratio
│   │   └── Percentage
│   └── Money
├── Text
│   ├── HumanName
│   ├── Identifier
│   └── URL
├── Duration
│   ├── CalendarDuration
│   └── ClockDuration
└── Boolean
```

## 6. Field Inheritance

A subtype inherits all fields from its parent types. Inherited fields can be **narrowed** (replaced with a more specific type expression) but not widened.

```logos
type Animal IS-A Entity
  fields:
    name: Text
    lifespan: Duration

type Dog IS-A Animal
  fields:
    name: Text   // valid: same type (no change)
    breed: Text

type GoldenRetriever IS-A Dog
  fields:
    // Inherits name: Text, lifespan: Duration, breed: Text from ancestors
    // Can add new fields:
    coat-color: Text
```

**Narrowing example** (a subtype may narrow a field to a more specific type):

```logos
type Vehicle IS-A Entity
  fields:
    owner: Entity    // broad: any entity can own a vehicle

type RegisteredVehicle IS-A Vehicle
  fields:
    owner: Person    // narrowed: only Persons own registered vehicles
```

Narrowing is valid because `Person IS-A Entity`, so any rule that accepts a `Vehicle.owner` will accept a `RegisteredVehicle.owner` (Liskov substitution principle).

## 7. Type Ascription

An entity is associated with a type using the `::` operator:

```logos
alice :: Person
acme-corp :: Corporation
```

Type ascription is itself a fact in the knowledge graph, with provenance and confidence:

```logos
alice :: Employee [confidence: 0.9, source: "HR database"]
```

An entity can have multiple type ascriptions (it belongs to multiple types simultaneously):

```logos
alice :: Person
alice :: Employee
alice :: Citizen
```

The type of an entity is the **join** (most specific common supertype) of all its ascribed types.

## 8. Type Checking Rules

### 8.1 Field Type Checking

When a binding asserts a value for a field declared in a type, the value must conform to the field's type expression. The type checker resolves this at assertion time.

```logos
type Person IS-A Entity
  fields:
    age: Duration

age of alice := 30 years    // OK: 30 years is a Duration
age of alice := "thirty"    // ERROR: "thirty" is Text, not Duration
age of alice := 30          // ERROR: 30 is Integer, not Duration
```

### 8.2 Optional Fields

A field declared `T?` may be absent from an entity. Querying an absent optional field returns no binding (not an error).

```logos
type Person IS-A Entity
  fields:
    nickname: Text?

// alice has no nickname binding — this is valid, not an error
find nickname of alice  // returns: no binding found
```

### 8.3 Inference-Level Type Checking

Inference rules may constrain their variables to specific types:

```logos
can-retire(P) if:
  P :: Employee
  age of P >= 65 years
```

This rule only applies to entities ascribed as `Employee`. Attempting to query `can-retire(acme-corp)` will fail the `P :: Employee` check before evaluating the age condition.

### 8.4 Runtime Type Coercion

Logos does **not** perform implicit type coercions. All type conversions are explicit using built-in conversion functions:

```logos
// Explicit conversion
age-as-years of alice := years-of(age of alice)   // Duration → Integer
```

## 9. Structural vs. Nominal Typing

Logos uses **nominal typing**: a type is identified by its name, not by its structure. Two types with identical field declarations are distinct types and are not interchangeable without explicit IS-A relationships.

```logos
type Point2D IS-A Entity
  fields:
    x: Float
    y: Float

type Coordinate IS-A Entity
  fields:
    x: Float
    y: Float

// Point2D and Coordinate are NOT the same type,
// even though they have the same fields.
```

This matches ontological semantics: a GPS coordinate and a 2D geometric point may have the same data shape but different meanings.
