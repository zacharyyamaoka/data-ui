"""Every gallery producer that imports a shared helper (gallery/tools/, e.g. public_paths) finds it the way its
documented command runs it: `python3 -I <producer>`, where -I keeps the script's own directory off sys.path, so the
producer's own `sys.path.insert(...)` line is the only way in.

WHY (judge round 3 #1, reports/media/audits/2026-10-28-dashboards-judge-r3.md): the round-2 shim inserted
`parents[3] / "gallery" / "tools"`, and parents[3] of gallery/examples/<case>/source/x.py is already gallery/, so all
12 producers died with ModuleNotFoundError: public_paths while every other test stayed green. This test evaluates each
producer's own insert expression with its real __file__ and imports the helper from exactly those directories in an
isolated interpreter. Stdlib only, so `python3 -m unittest discover -s tools` runs it with no venv."""

import ast
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOLS = ROOT / "gallery" / "tools"
HELPERS = {p.stem for p in TOOLS.glob("*.py")}


def producers():
    """Every .py under gallery/examples/ that imports a module living in gallery/tools/."""
    out = []
    for path in sorted((ROOT / "gallery" / "examples").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        wanted = sorted({n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module in HELPERS}
                        | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names if a.name in HELPERS})
        if wanted:
            out.append((path, tree, wanted))
    return out


def inserted_dirs(path, tree):
    """The directories the producer's own `sys.path.insert(i, <expr>)` calls add, evaluated with its real __file__."""
    dirs = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "insert"
                and isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "path" and len(node.args) == 2):
            expr = ast.Expression(node.args[1])
            ast.fix_missing_locations(expr)
            dirs.append(str(eval(compile(expr, str(path), "eval"), {"__file__": str(path), "__builtins__": __builtins__})))
    return dirs


class ProducerHelperImports(unittest.TestCase):
    def test_there_are_producers_to_check(self):
        # the gate must not pass by finding nothing: the 12 round-2 producers import public_paths
        self.assertGreaterEqual(len(producers()), 12, [str(p) for p, _, _ in producers()])

    def test_each_producer_imports_its_helpers_from_its_own_sys_path_line(self):
        failures = []
        for path, tree, wanted in producers():
            rel = path.relative_to(ROOT)
            dirs = inserted_dirs(path, tree)
            if not dirs:
                failures.append(f"{rel}: imports {wanted} but adds no sys.path entry (python3 -I cannot see gallery/tools)")
                continue
            for d in dirs:
                if not pathlib.Path(d).is_dir():
                    failures.append(f"{rel}: its sys.path line adds {d}, which does not exist")
            code = "import sys; sys.path[:0] = sys.argv[1:]\n" + "".join(f"import {m}\n" for m in wanted)
            r = subprocess.run([sys.executable, "-I", "-c", code, *dirs], capture_output=True, text=True)
            if r.returncode != 0:
                failures.append(f"{rel}: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else r.returncode}")
        self.assertEqual(failures, [], "\n" + "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
