"""
Logos compiler driver: .logos source → native binary via C transpilation.

Pipeline:
  parse_file(.logos) → Program AST
  → resolve_imports()  → flattened Program (no ImportStmt nodes)
  → Compiler.generate() → C source string
  → cc <generated.c> logos_runtime.c -o <output> -O2
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from logos.ast_nodes import ImportStmt, Program
from logos.parser import parse_file
from logos.codegen import Compiler, CompilationError  # re-export CompilationError

__all__ = ["compile_file", "flatten_file", "CompilationError", "resolve_imports"]


# ── Import flattening ─────────────────────────────────────────────────────────

def resolve_imports(
    program: Program,
    base_dir: str,
    _loaded: set[str] | None = None,
    _loading: set[str] | None = None,
) -> Program:
    """Return a new Program with all import statements replaced by the
    imported file's statements (recursive, deduplicated).

    Args:
        program:   The AST to flatten.
        base_dir:  Directory used to resolve relative import paths.
        _loaded:   Set of already-inlined canonical paths (dedup across files).
        _loading:  Set of paths currently on the DFS stack (cycle detection).

    Raises:
        CompilationError: On circular imports or missing files.
    """
    if _loaded is None:
        _loaded = set()
    if _loading is None:
        _loading = set()

    result = []
    for stmt in program.statements:
        if not isinstance(stmt, ImportStmt):
            result.append(stmt)
            continue

        # Resolve canonical path
        src = stmt.source
        if not os.path.isabs(src):
            src = os.path.join(base_dir, src)
        if not src.endswith(".logos"):
            src += ".logos"
        canon = os.path.normpath(src)

        if canon in _loading:
            raise CompilationError(f"Circular import: {canon}")
        if canon in _loaded:
            continue          # already inlined — skip duplicate
        if not os.path.isfile(canon):
            raise CompilationError(f"Import not found: {canon}")

        _loading.add(canon)
        imported_prog  = parse_file(canon)
        imported_dir   = os.path.dirname(canon)
        flattened      = resolve_imports(imported_prog, imported_dir,
                                         _loaded, _loading)
        _loading.discard(canon)
        _loaded.add(canon)

        result.extend(flattened.statements)

    return Program(statements=result)


# ── Source flattening ─────────────────────────────────────────────────────────

def _collect_source_paths(
    program: Program,
    base_dir: str,
    _loaded: set[str] | None = None,
    _loading: set[str] | None = None,
) -> list[str]:
    """Return ordered list of canonical source file paths (imports before importer).

    Mirrors resolve_imports() DFS traversal so the concatenated source order
    matches the AST flattening order.
    """
    if _loaded is None:
        _loaded = set()
    if _loading is None:
        _loading = set()

    result = []
    for stmt in program.statements:
        if not isinstance(stmt, ImportStmt):
            continue

        src = stmt.source
        if not os.path.isabs(src):
            src = os.path.join(base_dir, src)
        if not src.endswith(".logos"):
            src += ".logos"
        canon = os.path.normpath(src)

        if canon in _loading:
            raise CompilationError(f"Circular import: {canon}")
        if canon in _loaded:
            continue
        if not os.path.isfile(canon):
            raise CompilationError(f"Import not found: {canon}")

        _loading.add(canon)
        imported_prog = parse_file(canon)
        imported_dir  = os.path.dirname(canon)
        result.extend(_collect_source_paths(imported_prog, imported_dir, _loaded, _loading))
        _loading.discard(canon)
        _loaded.add(canon)
        result.append(canon)

    return result


def flatten_file(logos_path: str, output_path: str | None = None) -> str:
    """Inline all imports into a single .logos source string.

    Produces a self-contained file with no import statements that can be
    compiled directly by the self-hosted logos_compile binary.

    Args:
        logos_path:   Entry-point .logos file.
        output_path:  If given, write the result there; otherwise return only.

    Returns:
        The flattened source text.

    Raises:
        CompilationError: On circular imports or missing files.
    """
    logos_path = os.path.abspath(logos_path)
    base_dir   = os.path.dirname(logos_path)
    program    = parse_file(logos_path)

    dep_paths  = _collect_source_paths(program, base_dir)
    all_paths  = dep_paths + [logos_path]   # entry file goes last

    chunks = [f"// Flattened by logos flatten — do not edit by hand\n"
              f"// Source: {logos_path}\n"]
    for path in all_paths:
        rel = os.path.relpath(path, start=os.path.dirname(logos_path))
        chunks.append(f"\n// ── {rel} ──────────────────────────────────────────────────\n")
        with open(path) as fh:
            for line in fh:
                if line.lstrip().startswith("import "):
                    continue
                chunks.append(line)

    source = "".join(chunks)

    if output_path is not None:
        with open(output_path, "w") as fh:
            fh.write(source)

    return source


# ── Compile entry point ───────────────────────────────────────────────────────

def compile_file(
    logos_path: str,
    output_path: str,
    cc: str = "cc",
    keep_c: bool = False,
    runtime_path: str | None = None,
) -> None:
    """Compile a .logos file to a native binary via the Python codegen.

    Args:
        logos_path:   Path to the .logos source file.
        output_path:  Destination path for the compiled binary.
        cc:           C compiler command (default: "cc").
        keep_c:       If True, also write the generated C to <output_path>.c.
        runtime_path: Path to logos_runtime.c; defaults to the bundled copy.

    Raises:
        CompilationError: If compilation fails (parse error or C compiler error).
    """
    if runtime_path is None:
        runtime_path = str(
            Path(__file__).parent / "runtime" / "logos_runtime.c"
        )

    base_dir = os.path.dirname(os.path.abspath(logos_path))
    program  = parse_file(logos_path)
    program  = resolve_imports(program, base_dir)
    c_source = Compiler(program).generate()

    if keep_c:
        c_path = output_path + ".c"
        with open(c_path, "w") as fh:
            fh.write(c_source)
        _run_cc(c_path, output_path, cc, runtime_path)
    else:
        fd, tmp_c = tempfile.mkstemp(suffix=".c")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(c_source)
            _run_cc(tmp_c, output_path, cc, runtime_path)
        finally:
            if os.path.exists(tmp_c):
                os.unlink(tmp_c)


def _run_cc(c_path: str, output_path: str, cc: str, runtime_path: str) -> None:
    """Invoke the C compiler and raise CompilationError on failure."""
    runtime_dir = str(Path(runtime_path).parent)
    primitives_path = str(Path(runtime_path).parent / "logos_primitives.c")
    meta_path       = str(Path(runtime_path).parent / "logos_meta.c")
    lexer_path      = str(Path(runtime_path).parent / "logos_lexer.c")
    import sys as _sys
    # On macOS, increase the default stack size (8 MB → 256 MB) to handle deep
    # CPS recursion in parser/compiler rules without segfaulting.
    stack_flags = ["-Wl,-stack_size,0x10000000"] if _sys.platform == "darwin" else []
    cmd = [cc, c_path, runtime_path, primitives_path, meta_path, lexer_path,
           f"-I{runtime_dir}", "-o", output_path, "-O2", "-lm"] + stack_flags
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise CompilationError(
            f"C compiler exited with code {result.returncode}:\n{result.stderr}"
        )
