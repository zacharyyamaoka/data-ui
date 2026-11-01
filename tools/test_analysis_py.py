"""The two readers of an analysis agree: packages/analysis/src/format.js (the page, the checker) and its Python twin
packages/analysis/python/data_ui_analysis.py (build scripts), on the same files (docs/peps/0007-analyses.md).

    python3 -m unittest tools/test_analysis_py.py
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "analysis" / "python"))
import data_ui_analysis as A  # noqa: E402

FILES = sorted((ROOT / "tests" / "fixtures" / "analysis").glob("*.md")) + sorted((ROOT / "gallery" / "examples" / "analyses").glob("*.md"))
HARNESS = """
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
const F = await import(pathToFileURL(process.argv[2]).href);
const out = {};
for (const file of process.argv.slice(3)) {
  const r = F.readAnalysis(readFileSync(file, 'utf8'));
  out[file] = { front: r.front, bodyLine: r.bodyLine, problems: r.problems, blocks: F.blocksOf(r.body, r.bodyLine),
    row: F.analysisRow('x', r.front, { url: '/x/', path: 'x.md' }) };
}
process.stdout.write(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "node runs format.js")
class Twins(unittest.TestCase):
    def test_same_front_problems_blocks_and_row(self):
        self.assertTrue(FILES)
        with tempfile.TemporaryDirectory() as tmp:
            script = pathlib.Path(tmp) / "h.mjs"
            script.write_text(HARNESS, encoding="utf-8")
            run = subprocess.run(["node", str(script), str(ROOT / "packages" / "analysis" / "src" / "format.js"), *map(str, FILES)],
                                 capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        js = json.loads(run.stdout)
        for file in FILES:
            with self.subTest(file=file.name):
                front, body, line, problems = A.read_analysis(file.read_text(encoding="utf-8"))
                want = js[str(file)]
                self.assertEqual(front, want["front"])
                self.assertEqual(line, want["bodyLine"])
                self.assertEqual([(p["line"], p["message"]) for p in problems], [(p["line"], p["message"]) for p in want["problems"]])
                blocks = A.blocks_of(body, line)
                self.assertEqual(blocks, [{k: v for k, v in b.items()} for b in want["blocks"]])
                self.assertEqual(A.analysis_row("x", front, url="/x/", path="x.md"), want["row"])


class GalleryRows(unittest.TestCase):
    def test_the_gallery_list_is_current_with_its_files(self):
        """gallery/examples/analyses/analyses.json is what source/build.py writes from the .md files today."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("analyses_build", ROOT / "gallery" / "examples" / "analyses" / "source" / "build.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        on_disk = json.loads((ROOT / "gallery" / "examples" / "analyses" / "analyses.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk, module.dataset(), "run: python3 gallery/examples/analyses/source/build.py")


if __name__ == "__main__":
    unittest.main()
