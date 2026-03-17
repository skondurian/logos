# Logos Language Specification — Chapter 3: Ontological Types

## 1. Overview

Logos's type system is **ontological**: types represent categories of real-world entities, not memory layouts or computational structures. A type in Logos is a named set of entities with a shared set of properties (fields), and types are organized into a **partial order (IS-A lattice)** that expresses subtype relationships.

The type system serves two purposes:

1. **Documentation and constraint** — Types describe what fields an entity may have, enabling editors and linters to catch errors.
2. **Inference** — The IS-A lattice enables inference rules that apply to a type to automatically apply to all subtypes.

The type system is **open**: you can always declare new types without modifying existing ones. This is the open-world design principle applied to the type level.

## 2. Type Declaration Syntax

```
TypeDecl     ::= TypeName ':' NEWLINE BLOCK-START FieldDecl+ BLOCK-END
               | TypeName '(' TypeName (',' TypeName)* ')' ':' NEWLINE BLOCK-START FieldDecl+ BLOCK-END
               | TypeName '(' TypeName (',' TypeName)* ')' ':'   // no fields

FieldDecl    ::= FieldName ':' TypeExpr NEWLINE

TypeName     ::= PascalCase identifier
FieldName    ::= kebab-case or snake_case identifier
TypeExpr     ::= TypeName | 'List' '<' TypeExpr '>' | 'Set' '<' TypeExpr '>' | 'Optional' '<' TypeExpr '>'
```

A type with no parents implicitly has `Entity` as its root. Parent types are listed in parentheses immediately after the type name, before the colon.

### 2.1 Minimal Type Declaration

A type with no parent and no fields:

```logos
Tag:
```

> Note: A type with no fields still requires the colon. A body block (indented fields) is optional.

### 2.2 Type with Parent

```logos
Person (Entity):
  name: HumanName
  age: Duration
```

### 2.3 Type with Multiple Parents (Multiple Inheritance)

```logos
Employee (Person, OrganizationMember):
  title: Text
```

### 2.4 Type with Fields

```logos
Person (Entity):
  name: HumanName
  age: Duration
  nationality: Text
```

### 2.5 Full Example with Nested Hierarchy

```logos
LegalEntity:
  legal-name: Text
  jurisdiction: Text

Organization (LegalEntity):
  founded: Duration
  headquarters: Text

Corporation (Organization):
  ticker-symbol: Text
  public: Boolean

Person (LegalEntity):
  name: HumanName
  nationality: Text

Employee (Person):
  employer: Organization
  title: Text
  salary: Optional<Money>

Executive (Employee):
  budget-authority: Optional<Money>
```

## 3. Built-in Root Types

Logos provides a set of built-in types that are the roots of the type lattice. All user-defined types must eventually trace their IS-A ancestry to one of these roots.

### 3.1 Entity

`Entity` is the universal root type. Every named thing in the Logos knowledge graph is an `Entity`. Entities have a unique identifier within their namespace. `Entity` itself has no built-in fields; all fields come from subtypes.

> **Planned (not yet implemented):** Explicit type ascription using the `::` operator (`alice :: Person`) is not yet supported by the runtime. Currently, entities acquire their type implicitly by being the subject of field bindings declared for a given type.

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

Numbers support the standard arithmetic operators and all comparison operators.

### 3.3 Text

`Text` is the root of the string/character type hierarchy.

| Type | Description |
|------|-------------|
| `Text` | Arbitrary Unicode string |
| `HumanName` | Structured personal name |
| `Identifier` | A machine-readable identifier (no spaces) |
| `URL` | A well-formed URL |
| `CurrencyCode` | ISO 4217 currency code (e.g., `"USD"`, `"EUR"`) |

### 3.4 HumanName

`HumanName` is a structured type representing a personal name. It deserves special treatment because names are culturally complex: different cultures order components differently, some people have only one name, names may include honorifics, etc.

In the current runtime, `HumanName` values are stored as `Text` strings. The structured field breakdown below describes the intended semantics:

```logos
HumanName (Text):
  honorific: Optional<Text>       // "Dr.", "Prof.", "Mr.", "Ms."
  given-names: List<Text>         // list of given/first names
  family-name: Optional<Text>     // may be absent (some cultures)
  generation-suffix: Optional<Text>  // "Jr.", "III", "Sr."
  preferred: Optional<Text>       // preferred form of address
```

**HumanName literal syntax (current runtime):**

```logos
name of alice := "Alice Smith"
```

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

// Duration comparison
age of alice >= 18 years   // compares in days: age-in-days >= 6574
```

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

### 3.8 Set and List

| Type | Description |
|------|-------------|
| `List<T>` | Ordered, indexed sequence of values |
| `Set<T>` | Unordered collection of unique values |

Type expressions for collections:

```logos
Person (Entity):
  aliases: List<Text>
  permissions: Set<Text>
```

## 4. Type Expressions

A type expression appears in field declarations. Type expression forms supported by the current runtime:

| Expression | Meaning |
|------------|---------|
| `T` | Exactly type T |
| `Optional<T>` | Optional: T or absent |
| `List<T>` | Possibly-empty list of T |
| `Set<T>` | Set of T |

The following type expression forms are **planned but not yet implemented** in the runtime:

| Expression | Meaning |
|------------|---------|
| `T?` | Shorthand for `Optional<T>` |
| `T+` | Non-empty list of T |
| `#{T}` | Alternative set syntax |
| `T \| U` | Union: T or U |
| `T & U` | Intersection: both T and U |

```logos
Document (Entity):
  title: Text
  author: Text
  tags: List<Text>
  created: Date
```

## 5. The IS-A Lattice

### 5.1 Multiple Inheritance

Logos supports **multiple inheritance** in the IS-A lattice. An entity can belong to multiple types, and a type can have multiple parent types.

```logos
Person (Entity):
  name: HumanName

Employee (Person):
  employer: Text

Citizen (Person):
  country: Text

// A type can inherit from both Employee and Citizen
EmployedCitizen (Employee, Citizen):
```

When a type has multiple parents, it inherits all fields from all parents. If two parents declare a field with the same name, it is an error unless both declarations are identical (same type expression).

### 5.2 Diamond Inheritance

When the same ancestor type appears via multiple inheritance paths (the "diamond problem"), Logos uses **C3 linearization** to determine field resolution order. In practice, because field types must be consistent, diamond inheritance rarely causes conflicts.

```logos
Named (Entity):
  name: Text

Person (Named):
  age: Duration

Employee (Named):
  employer: Text

// Worker inherits `name` from Named (once, via both Person and Employee)
// and gets both `age` and `employer`
Worker (Person, Employee):
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
Animal (Entity):
  name: Text
  lifespan: Duration

Dog (Animal):
  breed: Text

GoldenRetriever (Dog):
  // Inherits name: Text, lifespan: Duration, breed: Text from ancestors
  // Can add new fields:
  coat-color: Text
```

**Narrowing example** (a subtype may narrow a field to a more specific type):

```logos
Vehicle (Entity):
  owner: Text    // broad: any text identifier

RegisteredVehicle (Vehicle):
  owner: Text    // narrowed semantics expressed via inference rules
```

## 7. Type Ascription

> **Planned (not yet implemented):** The `::` type ascription operator (`alice :: Person`) is not implemented in the current runtime. The syntax is reserved for a future version.

In the current runtime, entities are associated with types implicitly: when you assert a value for a field declared in a type, the entity is considered to be of that type for purposes of field lookup. Explicit type assertions and type-checking at bind time are planned features.

The intended future syntax is:

```logos
// Planned syntax — not yet implemented:
alice :: Person
acme-corp :: Corporation
alice :: Employee [confidence: 0.9, source: "HR database"]
```

## 8. Type Checking Rules

### 8.1 Field Type Checking

> **Planned (not yet implemented):** The current runtime does not validate binding values against declared field types. A binding such as `age of alice := "thirty"` is accepted without error even if `age` is declared as `Duration`. Type enforcement at assertion time is a planned feature.

The intended behavior once implemented:

```logos
Person (Entity):
  age: Duration

age of alice := 30 years    // OK: 30 years is a Duration
age of alice := "thirty"    // ERROR (planned): "thirty" is Text, not Duration
age of alice := 30          // ERROR (planned): 30 is Integer, not Duration
```

### 8.2 Optional Fields

A field declared `Optional<T>` may be absent from an entity. Querying an absent optional field returns no binding (not an error).

```logos
Person (Entity):
  nickname: Optional<Text>

// alice has no nickname binding — this is valid, not an error
find nickname of alice  // returns: no binding found
```

### 8.3 Inference-Level Type Checking

Inference rules may constrain their variables to specific types via the `::` condition syntax. This is implemented in the runtime:

```logos
can-retire(P) if:
  P.age >= 65 years
```

> **Note:** The `P :: Employee` type-guard form in rule conditions depends on the type ascription feature and is **planned (not yet implemented)**. Currently, rules match on field bindings rather than explicit type labels.

### 8.4 Runtime Type Coercion

Logos does **not** perform implicit type coercions. All type conversions are explicit using built-in conversion functions.

## 9. Structural vs. Nominal Typing

Logos uses **nominal typing**: a type is identified by its name, not by its structure. Two types with identical field declarations are distinct types and are not interchangeable without explicit IS-A relationships.

```logos
Point2D (Entity):
  x: Float
  y: Float

Coordinate (Entity):
  x: Float
  y: Float

// Point2D and Coordinate are NOT the same type,
// even though they have the same fields.
```

This matches ontological semantics: a GPS coordinate and a 2D geometric point may have the same data shape but different meanings.
