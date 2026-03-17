"""
Parser for Logos — hand-written recursive descent.

Takes the token list from lexer.tokenize() and produces an AST (Program node).

We use a hand-written parser rather than the Lark grammar for now because:
  1. Indentation-sensitive grammars are tricky in Lark
  2. We need fine-grained error messages
  3. The language is small enough that hand-writing is faster

The Lark grammar (grammar.lark) remains the authoritative spec reference.
"""

from __future__ import annotations
from typing import Any, Optional

from logos.lexer import Token, tokenize
from logos.ast_nodes import (
    Program, Statement, TypeDecl, TypeExpr, FieldDecl,
    SemanticBinding, Retraction, Annotations, ConfidenceAnnotation,
    ProvenanceAnnotation, FallbackEntry,
    InferenceRule, PredicateCall, Comparison, NegatedPredicate, Variable,
    TransformDecl, TransformDirective, Param,
    ContextDecl, ContextDirective,
    BoolQuery, FindQuery,
    ImportStmt,
    Path, DurationLit, SetLit, ListLit, ArithExpr,
)
from logos import errors as err


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    # ── Token navigation ──────────────────────────────────────────────────────

    def peek(self, offset: int = 0) -> Token:
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return Token("EOF", "", 0, 0)

    def advance(self) -> Token:
        t = self.peek()
        self.pos += 1
        return t

    def expect(self, *types_or_values: str) -> Token:
        t = self.peek()
        for tv in types_or_values:
            if t.type == tv or t.value == tv:
                return self.advance()
        raise err.ParseError(
            f"Line {t.line}: expected {types_or_values!r}, got {t.type}={t.value!r}"
        )

    def match(self, *types_or_values: str) -> Optional[Token]:
        t = self.peek()
        for tv in types_or_values:
            if t.type == tv or t.value == tv:
                return self.advance()
        return None

    def skip_newlines(self):
        while self.peek().type == "NEWLINE":
            self.advance()

    def at_eof(self) -> bool:
        return self.peek().type == "EOF"

    # ── Entry point ───────────────────────────────────────────────────────────

    def parse(self) -> Program:
        stmts = []
        self.skip_newlines()
        while not self.at_eof():
            stmt = self.parse_statement()
            if stmt is not None:
                stmts.append(stmt)
            self.skip_newlines()
        return Program(statements=stmts)

    def parse_statement(self) -> Optional[Statement]:
        t = self.peek()

        # Type declaration: IdentifierWithUpper + ":" or "IdentifierWithUpper (Parent) :"
        if t.type == "VARIABLE" and self.peek(1).type in ("COLON", "LPAREN"):
            return self.parse_type_decl()

        if t.type == "KEYWORD":
            if t.value == "retract":
                return self.parse_retraction()
            if t.value == "context":
                return self.parse_context_decl()
            if t.value == "transform":
                return self.parse_transform_decl()
            if t.value == "query":
                return self.parse_bool_query()
            if t.value == "find":
                return self.parse_find_query()
            if t.value == "import":
                return self.parse_import()

        # Inference rule: identifier "(" ... ")" "if"
        if t.type == "IDENTIFIER" and self._is_rule_head():
            return self.parse_inference_rule()

        # Semantic binding: path ":="
        if self._is_binding_start():
            return self.parse_semantic_binding()

        # Unknown — skip
        self.advance()
        return None

    # ── Type declarations ─────────────────────────────────────────────────────

    def parse_type_decl(self) -> TypeDecl:
        name = self.expect("VARIABLE").value
        parents = []
        # Optional parent list in parens — before the colon
        if self.peek().type == "LPAREN":
            self.advance()
            parents.append(self.expect("VARIABLE").value)
            while self.match("COMMA"):
                parents.append(self.expect("VARIABLE").value)
            self.expect("RPAREN")
        self.expect("COLON")
        self.skip_newlines()
        fields = []
        if self.peek().type == "INDENT":
            self.advance()
            while self.peek().type not in ("DEDENT", "EOF"):
                if self.peek().type == "NEWLINE":
                    self.advance()
                    continue
                fd = self.parse_field_decl()
                if fd:
                    fields.append(fd)
            if self.peek().type == "DEDENT":
                self.advance()
        return TypeDecl(name=name, parents=parents, fields=fields)

    def parse_field_decl(self) -> Optional[FieldDecl]:
        if self.peek().type not in ("IDENTIFIER",):
            self.advance()
            return None
        name = self.advance().value
        self.expect("COLON")
        te = self.parse_type_expr()
        self.skip_newlines()
        return FieldDecl(name=name, type_expr=te)

    def parse_type_expr(self) -> TypeExpr:
        name = self.advance().value
        params = []
        if self.peek().type == "OP_LT":
            self.advance()
            params.append(self.parse_type_expr())
            while self.match("COMMA"):
                params.append(self.parse_type_expr())
            self.expect("OP_GT")
        return TypeExpr(name=name, params=params)

    # ── Semantic bindings ─────────────────────────────────────────────────────

    def _is_binding_start(self) -> bool:
        """Detect 'path :=' or 'keyword of identifier :='."""
        saved = self.pos
        try:
            self._skip_path_tokens()
            if self.peek().type == "ASSIGN":
                return True
            return False
        finally:
            self.pos = saved

    def _skip_path_tokens(self):
        """Advance past a path expression (for lookahead)."""
        t = self.peek()
        if t.type in ("IDENTIFIER", "VARIABLE"):
            self.advance()
            # "of" form
            if self.peek().value == "of":
                self.advance()
                if self.peek().type in ("IDENTIFIER", "VARIABLE"):
                    self.advance()
            # dot chain
            while self.peek().type == "DOT":
                self.advance()
                self.advance()

    def parse_semantic_binding(self) -> SemanticBinding:
        path = self.parse_path()
        self.expect("ASSIGN")
        value = self.parse_value()
        self.skip_newlines()
        annotations = Annotations()
        if self.peek().type == "INDENT":
            self.advance()
            annotations = self.parse_annotations()
        return SemanticBinding(path=path, value=value, annotations=annotations)

    def parse_path(self) -> Path:
        t = self.advance()
        parts = [t.value]
        # "X of Y" → Path(["Y", "X"])
        if self.peek().value == "of":
            self.advance()
            subject = self.advance().value
            return Path(parts=[subject, parts[0]])
        # dot chain
        while self.peek().type == "DOT":
            self.advance()
            parts.append(self.advance().value)
        return Path(parts=parts)

    def parse_annotations(self) -> Annotations:
        ann = Annotations()
        while self.peek().type not in ("DEDENT", "EOF"):
            if self.peek().type == "NEWLINE":
                self.advance()
                continue
            kw = self.peek().value
            if kw == "confidence":
                self.advance()
                self.expect("COLON")
                ann.confidence = ConfidenceAnnotation(
                    raw=self.parse_confidence_value()
                )
                self.skip_newlines()
            elif kw == "provenance":
                self.advance()
                self.expect("COLON")
                ann.provenance = ProvenanceAnnotation(
                    source=self.parse_string()
                )
                self.skip_newlines()
            elif kw == "fallback":
                self.advance()
                self.expect("COLON")
                fb_path = self.parse_path()
                fb_conf = None
                if self.peek().type == "LBRACKET":
                    self.advance()
                    self.expect("confidence")
                    self.expect("COLON")
                    fb_conf = float(self.expect("NUMBER").value)
                    self.expect("RBRACKET")
                ann.fallbacks.append(FallbackEntry(path=fb_path, confidence=fb_conf))
                self.skip_newlines()
            elif kw == "context":
                self.advance()
                self.expect("COLON")
                ann.context_name = self.advance().value
                self.skip_newlines()
            else:
                break
        if self.peek().type == "DEDENT":
            self.advance()
        return ann

    def parse_confidence_value(self):
        t = self.peek()
        if t.value == "absolute":
            self.advance()
            return "absolute"
        if self.peek().type == "LBRACKET":
            self.advance()
            lo = float(self.expect("NUMBER").value)
            self.expect("COMMA")
            hi = float(self.expect("NUMBER").value)
            self.expect("RBRACKET")
            return (lo, hi)
        return float(self.expect("NUMBER").value)

    # ── Values ────────────────────────────────────────────────────────────────

    def parse_value(self) -> Any:
        t = self.peek()

        # Set literal
        if t.type == "LBRACE":
            return self.parse_set_lit()

        # List literal
        if t.type == "LBRACKET":
            return self.parse_list_lit()

        # Boolean
        if t.value in ("true", "True"):
            self.advance()
            return True
        if t.value in ("false", "False"):
            self.advance()
            return False

        # String
        if t.type == "STRING":
            return self.parse_string()

        # Number (possibly duration)
        if t.type == "NUMBER":
            num = float(self.advance().value)
            if self.peek().type == "DURATION_UNIT":
                unit = self.advance().value
                return DurationLit(amount=num, unit=unit)
            return num

        # Identifier / path
        if t.type in ("IDENTIFIER", "VARIABLE"):
            # Could be identifier followed by operator → ArithExpr
            path = self.parse_path()
            if self.peek().type in ("OP_GEQ", "OP_LEQ", "OP_GT", "OP_LT",
                                    "OP_EQ", "OP_NEQ", "OP_PLUS", "OP_MINUS",
                                    "OP_STAR", "OP_SLASH"):
                op = self.advance().value
                right = self.parse_value()
                return ArithExpr(left=path, op=op, right=right)
            return path

        self.advance()
        return None

    def parse_string(self) -> str:
        s = self.expect("STRING").value
        return s[1:-1]  # strip quotes

    def parse_set_lit(self) -> SetLit:
        self.expect("LBRACE")
        elements = []
        if self.peek().type != "RBRACE":
            elements.append(self.parse_value())
            while self.match("COMMA"):
                elements.append(self.parse_value())
        self.expect("RBRACE")
        return SetLit(elements=elements)

    def parse_list_lit(self) -> ListLit:
        self.expect("LBRACKET")
        elements = []
        if self.peek().type != "RBRACKET":
            elements.append(self.parse_value())
            while self.match("COMMA"):
                elements.append(self.parse_value())
        self.expect("RBRACKET")
        return ListLit(elements=elements)

    # ── Retraction ────────────────────────────────────────────────────────────

    def parse_retraction(self) -> Retraction:
        self.expect("retract")
        self.expect("COLON")
        path = self.parse_path()
        self.skip_newlines()
        return Retraction(path=path)

    # ── Inference rules ───────────────────────────────────────────────────────

    def _is_rule_head(self) -> bool:
        """Detect 'identifier(...)' followed by 'if'."""
        saved = self.pos
        try:
            self.advance()  # identifier
            if self.peek().type != "LPAREN":
                return False
            depth = 1
            self.advance()
            while depth > 0 and not self.at_eof():
                t = self.advance()
                if t.type == "LPAREN":
                    depth += 1
                elif t.type == "RPAREN":
                    depth -= 1
            return self.peek().value == "if"
        finally:
            self.pos = saved

    def parse_inference_rule(self) -> InferenceRule:
        head = self.parse_predicate_call()
        self.expect("if")
        self.expect("COLON")
        self.skip_newlines()
        conditions = []
        if self.peek().type == "INDENT":
            self.advance()
            while self.peek().type not in ("DEDENT", "EOF"):
                if self.peek().type == "NEWLINE":
                    self.advance()
                    continue
                cond = self.parse_condition()
                if cond is not None:
                    conditions.append(cond)
            if self.peek().type == "DEDENT":
                self.advance()
        return InferenceRule(head=head, conditions=conditions)

    def parse_predicate_call(self) -> PredicateCall:
        name = self.expect("IDENTIFIER").value
        self.expect("LPAREN")
        args = []
        if self.peek().type != "RPAREN":
            args.append(self.parse_arg())
            while self.match("COMMA"):
                args.append(self.parse_arg())
        self.expect("RPAREN")
        return PredicateCall(name=name, args=args)

    def parse_arg(self) -> Any:
        t = self.peek()
        if t.type == "VARIABLE":
            self.advance()
            return Variable(name=t.value)
        return self.parse_value()

    def parse_condition(self) -> Any:
        t = self.peek()
        # Negation
        if t.value == "not":
            self.advance()
            pred = self.parse_predicate_call()
            self.skip_newlines()
            return NegatedPredicate(predicate=pred)

        # Could be predicate call or comparison
        if t.type == "IDENTIFIER" and self.peek(1).type == "LPAREN":
            pred = self.parse_predicate_call()
            self.skip_newlines()
            return pred

        # Path comparison: P.age >= 18 years
        path = self.parse_path()
        if self.peek().type in ("OP_GEQ", "OP_LEQ", "OP_GT", "OP_LT",
                                 "OP_EQ", "OP_NEQ"):
            op = self.advance().value
            right = self.parse_value()
            self.skip_newlines()
            return Comparison(left=path, op=op, right=right)

        self.skip_newlines()
        return None

    # ── Transforms ────────────────────────────────────────────────────────────

    def parse_transform_decl(self) -> TransformDecl:
        self.expect("transform")
        name = self.expect("IDENTIFIER").value
        self.expect("LBRACKET")
        params = []
        if self.peek().type != "RBRACKET":
            params.append(self.parse_param())
            while self.match("COMMA"):
                params.append(self.parse_param())
        self.expect("RBRACKET")
        self.expect("ARROW")
        ret_type = self.parse_type_expr()
        self.expect("COLON")
        self.skip_newlines()
        directives = []
        if self.peek().type == "INDENT":
            self.advance()
            while self.peek().type not in ("DEDENT", "EOF"):
                if self.peek().type == "NEWLINE":
                    self.advance()
                    continue
                d = self.parse_transform_directive()
                if d:
                    directives.append(d)
            if self.peek().type == "DEDENT":
                self.advance()
        return TransformDecl(name=name, params=params,
                             return_type=ret_type, directives=directives)

    def parse_param(self) -> Param:
        name = self.advance().value
        self.expect("COLON")
        te = self.parse_type_expr()
        return Param(name=name, type_expr=te)

    def parse_transform_directive(self) -> Optional[TransformDirective]:
        t = self.peek()
        if t.value in ("intent",):
            self.advance()
            self.expect("COLON")
            val = self.parse_string()
            self.skip_newlines()
            return TransformDirective(kind=t.value, value=val)
        if t.value in ("maximize", "minimize"):
            kind = t.value
            self.advance()
            self.expect("COLON")
            val = self.advance().value
            self.skip_newlines()
            return TransformDirective(kind=kind, value=val)
        if t.value == "considering":
            self.advance()
            self.expect("COLON")
            paths = [self.parse_path()]
            while self.match("COMMA"):
                paths.append(self.parse_path())
            self.skip_newlines()
            return TransformDirective(kind="considering", value=paths)
        if t.value == "require":
            self.advance()
            self.expect("COLON")
            cond = self.parse_condition()
            return TransformDirective(kind="require", value=cond)
        self.advance()
        return None

    # ── Contexts ──────────────────────────────────────────────────────────────

    def parse_context_decl(self) -> ContextDecl:
        self.expect("context")
        name = self.advance().value
        self.expect("COLON")
        self.skip_newlines()
        directives = []
        if self.peek().type == "INDENT":
            self.advance()
            while self.peek().type not in ("DEDENT", "EOF"):
                if self.peek().type == "NEWLINE":
                    self.advance()
                    continue
                d = self.parse_context_directive()
                if d:
                    directives.append(d)
            if self.peek().type == "DEDENT":
                self.advance()
        return ContextDecl(name=name, directives=directives)

    def parse_context_directive(self) -> Optional[ContextDirective]:
        t = self.peek()
        if t.value == "confidence-threshold":
            self.advance()
            self.expect("COLON")
            val = float(self.expect("NUMBER").value)
            self.skip_newlines()
            return ContextDirective(kind="confidence-threshold", value=val)
        if t.value == "error-tolerance":
            self.advance()
            self.expect("COLON")
            val = self.advance().value
            self.skip_newlines()
            return ContextDirective(kind="error-tolerance", value=val)
        if t.value == "extends":
            self.advance()
            self.expect("COLON")
            val = self.advance().value
            self.skip_newlines()
            return ContextDirective(kind="extends", value=val)
        self.advance()
        return None

    # ── Queries ───────────────────────────────────────────────────────────────

    def parse_bool_query(self) -> BoolQuery:
        self.expect("query")
        self.expect("COLON")
        pred = self.parse_predicate_call()
        self.expect("QUESTION")
        self.skip_newlines()
        return BoolQuery(predicate=pred)

    def parse_find_query(self) -> FindQuery:
        self.expect("find")
        variables = []
        variables.append(Variable(name=self.expect("VARIABLE").value))
        while self.match("COMMA"):
            variables.append(Variable(name=self.expect("VARIABLE").value))
        self.expect("where")
        conditions = []
        cond = self.parse_find_condition()
        if cond:
            conditions.append(cond)
        while self.match("COMMA"):
            cond = self.parse_find_condition()
            if cond:
                conditions.append(cond)
        # Optional confidence filter
        conf_filter = None
        if self.peek().value == "confidence":
            self.advance()
            op = self.advance().value
            threshold = float(self.expect("NUMBER").value)
            conf_filter = (op, threshold)
        self.skip_newlines()
        return FindQuery(variables=variables, conditions=conditions,
                         confidence_filter=conf_filter)

    def parse_find_condition(self) -> Any:
        t = self.peek()
        if t.type == "IDENTIFIER" and self.peek(1).type == "LPAREN":
            return self.parse_predicate_call()
        # Comparison
        path = self.parse_path()
        if self.peek().type in ("OP_GEQ", "OP_LEQ", "OP_GT", "OP_LT",
                                 "OP_EQ", "OP_NEQ"):
            op = self.advance().value
            right = self.parse_value()
            return Comparison(left=path, op=op, right=right)
        return path

    # ── Import ────────────────────────────────────────────────────────────────

    def parse_import(self) -> ImportStmt:
        self.expect("import")
        if self.peek().value == "*":
            self.advance()
            name = None
        else:
            name = self.advance().value
        self.expect("from")
        source = self.parse_string()
        self.skip_newlines()
        return ImportStmt(name=name, source=source)


# ─── Public interface ─────────────────────────────────────────────────────────

def parse(source: str) -> Program:
    """Parse a Logos source string into a Program AST."""
    tokens = tokenize(source)
    parser = Parser(tokens)
    return parser.parse()


def parse_file(path: str) -> Program:
    """Read and parse a .logos file."""
    with open(path, encoding="utf-8") as f:
        source = f.read()
    return parse(source)
