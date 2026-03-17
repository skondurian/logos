"""
Logos compiler driver: .logos source → native binary via C transpilation.

Pipeline:
  parse_file(.logos) → Program AST
  → Compiler.generate() → C source string
  → cc <generated.c> logos_runtime.c -o <output> -O2
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from logos.parser import parse_file
from logos.codegen import Compiler, CompilationError  # re-export CompilationError

__all__ = ["compile_file", "CompilationError"]


def compile_file(
    logos_path: str,
    output_path: str,
    cc: str = "cc",
    keep_c: bool = False,
    runtime_path: str | None = None,
) -> None:
    """Compile a .logos file to a native binary.

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

    program  = parse_file(logos_path)
    c_source = Compiler(program).generate()

    if keep_c:
        c_path = output_path + ".c"
        with open(c_path, "w") as fh:
            fh.write(c_source)
        _run_cc(c_path, output_path, cc, runtime_path)
    else:
        # Write to a temp file, compile, then delete
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
    cmd = [cc, c_path, runtime_path, f"-I{runtime_dir}", "-o", output_path, "-O2"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise CompilationError(
            f"C compiler exited with code {result.returncode}:\n{result.stderr}"
        )
