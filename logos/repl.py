"""
Interactive REPL for Logos.

Uses prompt_toolkit for line editing, history, and multi-line input.
Uses Pygments for syntax highlighting.
Uses rich for pretty output with confidence color bands.
"""

from __future__ import annotations
import sys
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.styles import style_from_pygments_cls
from pygments.lexer import RegexLexer, words
from pygments.token import (
    Keyword, Name, Number, String, Operator, Punctuation, Comment, Text
)
from rich.console import Console
from rich.table import Table
from rich.text import Text as RichText

from logos.executor import Executor, QueryOutput
from logos.confidence import ConfidenceValue


# ─── Syntax highlighter ───────────────────────────────────────────────────────

class LogosLexer(RegexLexer):
    name = "Logos"
    aliases = ["logos"]
    filenames = ["*.logos"]

    tokens = {
        "root": [
            (r"//.*", Comment.Single),
            (r'"[^"]*"', String),
            (r"\b(if|where|find|query|import|from|not|retract|context|"
             r"transform|within|true|false|True|False|absolute|"
             r"confidence|provenance|fallback|considering|maximize|"
             r"minimize|require|intent|extends|of|and|or)\b", Keyword),
            (r"\b(years?|months?|days?|hours?|minutes?|seconds?)\b",
             Keyword.Type),
            (r"[A-Z][A-Za-z0-9_-]*", Name.Class),
            (r"[a-z][a-zA-Z0-9_-]*", Name),
            (r"-?[0-9]+(\.[0-9]+)?", Number),
            (r":=|→|->", Operator),
            (r"[><=!]+|[+\-*/|]", Operator),
            (r"[:.,()\[\]{}<>?]", Punctuation),
            (r"\s+", Text),
        ]
    }


# ─── Output rendering ─────────────────────────────────────────────────────────

def confidence_color(cv: ConfidenceValue) -> str:
    """Map confidence to a rich color name."""
    p = cv.point
    if p >= 0.99:
        return "bright_green"
    if p >= 0.8:
        return "green"
    if p >= 0.6:
        return "yellow"
    if p >= 0.4:
        return "dark_orange"
    return "red"


def render_query_output(console: Console, output: QueryOutput):
    if output.is_true:
        color = confidence_color(output.confidence)
        if not output.results or output.results == [{}]:
            line = RichText()
            line.append(f"{output.query_text}", style="bold")
            line.append("  →  ", style="dim")
            line.append("TRUE", style=f"bold {color}")
            line.append(
                f"  [confidence: {output.confidence.point:.3f}]",
                style=color
            )
            console.print(line)
        else:
            table = Table(title=output.query_text, show_header=True)
            # Determine columns from first result
            cols = [k for k in output.results[0] if k != "__confidence__"]
            for c in cols:
                table.add_column(c, style="cyan")
            table.add_column("confidence", style="dim")
            for row in output.results:
                vals = [str(row.get(c, "")) for c in cols]
                conf = row.get("__confidence__", output.confidence)
                conf_str = f"{conf.point:.3f}" if isinstance(conf, ConfidenceValue) else "?"
                table.add_row(*vals, conf_str)
            console.print(table)
    else:
        line = RichText()
        line.append(f"{output.query_text}", style="bold")
        line.append("  →  ", style="dim")
        line.append("FALSE / not found", style="bold red")
        console.print(line)


# ─── REPL ─────────────────────────────────────────────────────────────────────

BANNER = """
[bold cyan]Logos[/bold cyan] [dim]v0.1.0 — AI-native language[/dim]
Type Logos expressions. Multi-line: end with a blank line.
Commands: [green]:help[/green]  [green]:graph[/green]  [green]:types[/green]  [green]:rules[/green]  [green]:exit[/green]
"""

HELP_TEXT = """
[bold]Logos REPL commands:[/bold]

  :help          Show this help
  :graph         Show all facts in the semantic graph
  :types         List all registered types
  :rules         List all inference rules
  :exit / :quit  Exit the REPL

[bold]Logos syntax (quick reference):[/bold]

  Person:                          // type declaration
    name: HumanName
    age: Duration

  age of alice := 30 years         // semantic binding
    confidence: absolute
    provenance: "birth-record"

  can-vote(P) if:                  // inference rule
    P.age >= 18 years
    P.citizenship = "US"

  query: can-vote(alice)?          // boolean query
  find P where can-vote(P)         // find query
"""


class LogosREPL:

    def __init__(self, executor: Optional[Executor] = None):
        self.executor = executor or Executor()
        self.console = Console()
        self.session: PromptSession = PromptSession(
            history=InMemoryHistory(),
            lexer=PygmentsLexer(LogosLexer),
        )

    def run(self):
        self.console.print(BANNER)
        while True:
            try:
                text = self._read_input()
            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[dim]Goodbye.[/dim]")
                break

            text = text.strip()
            if not text:
                continue

            if text.startswith(":"):
                self._handle_command(text)
                continue

            try:
                outputs = self.executor.load_source(text)
                for out in outputs:
                    render_query_output(self.console, out)
            except Exception as exc:
                self.console.print(f"[bold red]Error:[/bold red] {exc}")

    def _read_input(self) -> str:
        """Read one or more lines. Blank line terminates multi-line input."""
        lines = []
        prompt = "logos> "
        while True:
            line = self.session.prompt(prompt)
            if line == "" and lines:
                break
            lines.append(line)
            if not lines:
                continue
            prompt = "  ...  "
            # Single-line statements end with newline
            joined = "\n".join(lines)
            if not _needs_continuation(joined):
                break
        return "\n".join(lines)

    def _handle_command(self, cmd: str):
        cmd = cmd.lower().strip()
        if cmd in (":exit", ":quit", ":q"):
            raise EOFError
        elif cmd == ":help":
            self.console.print(HELP_TEXT)
        elif cmd == ":graph":
            self._show_graph()
        elif cmd == ":types":
            self._show_types()
        elif cmd == ":rules":
            self._show_rules()
        else:
            self.console.print(f"[dim]Unknown command: {cmd}[/dim]")

    def _show_graph(self):
        table = Table(title="Semantic Graph", show_header=True)
        table.add_column("Subject", style="cyan")
        table.add_column("Predicate", style="green")
        table.add_column("Value")
        table.add_column("Confidence", style="dim")
        table.add_column("Provenance", style="dim")
        for fact in self.executor.graph.all_active_facts():
            conf = f"{fact.confidence.point:.3f}"
            prov = ", ".join(p.source for p in fact.provenance)
            table.add_row(fact.subject, fact.predicate,
                          str(fact.value), conf, prov)
        self.console.print(table)

    def _show_types(self):
        table = Table(title="Type Lattice", show_header=True)
        table.add_column("Type", style="cyan")
        table.add_column("Parents", style="green")
        table.add_column("Fields", style="dim")
        for name in self.executor.type_lattice.all_type_names():
            t = self.executor.type_lattice.get(name)
            if t:
                parents = ", ".join(t.parents) or "—"
                fields = ", ".join(f.name for f in t.own_fields) or "—"
                table.add_row(name, parents, fields)
        self.console.print(table)

    def _show_rules(self):
        if not self.executor.rules:
            self.console.print("[dim]No inference rules defined.[/dim]")
            return
        for rule in self.executor.rules:
            args = ", ".join(str(a) for a in rule.head.args)
            head = f"{rule.head.name}({args})"
            conds = "\n  ".join(str(c) for c in rule.conditions)
            self.console.print(f"[bold]{head}[/bold] if:\n  {conds}\n")


def _needs_continuation(text: str) -> bool:
    """Return True if the text looks like it needs more lines (block open)."""
    stripped = text.rstrip()
    return stripped.endswith(":")


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="logos")
    sub = ap.add_subparsers(dest="command")
    sub.add_parser("repl", help="Start interactive REPL")
    run_cmd = sub.add_parser("run", help="Run a .logos file")
    run_cmd.add_argument("file", help="Path to .logos file")
    interp_cmd = sub.add_parser("interpret", help="Run a .logos file via interpreter.logos (self-hosting)")
    interp_cmd.add_argument("file", help="Path to .logos file to interpret")
    compile_cmd = sub.add_parser("compile", help="Compile a .logos file to a native binary")
    compile_cmd.add_argument("file", help="Path to .logos file")
    compile_cmd.add_argument("-o", "--output", help="Output binary path (default: file without extension)")
    compile_cmd.add_argument("--cc", default="cc", help="C compiler to use (default: cc)")
    compile_cmd.add_argument("--keep-c", action="store_true", help="Keep generated .c file")
    args = ap.parse_args()

    if args.command == "compile":
        import os
        from logos.compiler import compile_file, CompilationError
        output = args.output
        if output is None:
            output = os.path.splitext(args.file)[0]
        try:
            compile_file(args.file, output, cc=args.cc, keep_c=args.keep_c)
            print(f"Compiled: {output}")
        except CompilationError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "repl" or args.command is None:
        LogosREPL().run()
    elif args.command == "run":
        from logos.executor import Executor
        import os
        console = Console()
        executor = Executor(search_path=[os.path.dirname(os.path.abspath(args.file))])
        outputs = executor.load_file(args.file)
        console.print(f"[dim]Loaded {args.file} — {len(executor.graph)} active facts[/dim]")
        for out in outputs:
            render_query_output(console, out)
    elif args.command == "interpret":
        import os
        from logos.executor import Executor
        from logos.ast_nodes import PredicateCall
        logos_dir = os.path.join(os.path.dirname(__file__))
        ex = Executor()
        ex.load_file(os.path.join(logos_dir, "parser.logos"))
        ex.load_file(os.path.join(logos_dir, "evaluator.logos"))
        ex.load_file(os.path.join(logos_dir, "interpreter.logos"))
        target = os.path.abspath(args.file)
        goal = PredicateCall(name="interpret", args=[target])
        results = list(ex.engine.prove_all([goal]))
        if not any(r.success for r in results):
            print(f"interpret({args.file}): failed", file=sys.stderr)
            sys.exit(1)
