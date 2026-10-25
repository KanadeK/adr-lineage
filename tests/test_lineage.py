import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from adr_lineage.core import InputError, audit


class LineageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def adr(self, number, status, suffix="decision", body=""):
        name = f"{number:04d}-{suffix}.md"
        (self.root / name).write_text(
            f"# {number}. Decision\n\n## Status\n\n{status}\n\n## Context\n{body}\n",
            encoding="utf-8",
        )
        return name

    def codes(self):
        return {f["code"] for f in audit(self.root)["findings"]}

    def chain(self):
        self.adr(1, "Superseded by [2](0002-decision.md)")
        self.adr(2, "Superseded by [3](0003-decision.md)\nSupersedes [1](0001-decision.md)")
        self.adr(3, "Accepted\nSupersedes [2](0002-decision.md)")

    def test_transitive_resolution(self):
        self.chain()
        report = audit(self.root)
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["current"]["0001-decision.md"], ["0003-decision.md"])

    def test_multiple_successors(self):
        self.adr(1, "Superseded by [2](0002-decision.md), [3](0003-decision.md)")
        for n in (2, 3):
            self.adr(n, "Accepted\nSupersedes [1](0001-decision.md)")
        self.assertEqual(
            audit(self.root)["current"]["0001-decision.md"],
            ["0002-decision.md", "0003-decision.md"],
        )

    def test_missing_reciprocal(self):
        self.adr(1, "Superseded by [2](0002-decision.md)")
        self.adr(2, "Accepted")
        report = audit(self.root)
        self.assertIn("missing_reciprocal", self.codes())
        self.assertEqual(report["current"], {})

    def test_missing_target_line(self):
        self.adr(1, "Superseded by [2](0002-missing.md)")
        finding = next(f for f in audit(self.root)["findings"] if f["code"] == "missing_target")
        self.assertEqual(finding["line"], 5)
        self.assertIn("missing_replacement", self.codes())

    def test_cycle_witness(self):
        self.adr(1, "Superseded by [2](0002-decision.md)\nSupersedes [2](0002-decision.md)")
        self.adr(2, "Superseded by [1](0001-decision.md)\nSupersedes [1](0001-decision.md)")
        cycle = next(f for f in audit(self.root)["findings"] if f["code"] == "cycle")
        self.assertEqual(
            cycle["message"], "0001-decision.md -> 0002-decision.md -> 0001-decision.md"
        )

    def test_self_cycle(self):
        self.adr(1, "Superseded by [1](0001-decision.md)\nSupersedes [1](0001-decision.md)")
        self.assertIn("cycle", self.codes())

    def test_nonaccepted_replacement(self):
        self.adr(1, "Superseded by [2](0002-decision.md)")
        self.adr(2, "Proposed\nSupersedes [1](0001-decision.md)")
        self.assertIn("successor_status", self.codes())

    def test_accepted_predecessor(self):
        self.adr(1, "Accepted")
        self.adr(2, "Accepted\nSupersedes [1](0001-decision.md)")
        self.assertIn("predecessor_status", self.codes())

    def test_code_comments_context_ignored(self):
        self.adr(
            1,
            "Accepted\n<!-- Supersedes [x](0009-missing.md) -->\n"
            "```md\nSupersedes [x](0008-missing.md)\n```\n"
            "    Supersedes [x](0007-missing.md)",
            body="Supersedes [x](0006-missing.md)",
        )
        self.assertEqual(self.codes(), set())

    def test_unsupported_frontmatter_is_not_silently_accepted(self):
        (self.root / "0001-decision.md").write_text("---\nstatus: accepted\n---\n# Decision")
        self.assertIn("status_section", self.codes())

    def test_duplicate_id(self):
        self.adr(1, "Accepted")
        self.adr(1, "Accepted", suffix="other")
        self.assertIn("duplicate_id", self.codes())

    def test_duplicate_status_section(self):
        self.adr(1, "Accepted\n## Status\nAccepted")
        self.assertIn("status_section", self.codes())

    def test_conflicting_status(self):
        self.adr(1, "Accepted\nRejected")
        self.assertIn("status_value", self.codes())

    def test_deprecated_is_not_current(self):
        self.adr(1, "Deprecated")
        self.assertEqual(audit(self.root)["current"]["0001-decision.md"], [])

    def test_bad_links(self):
        for target in (
            "../0002-decision.md",
            "https://example.test/x",
            "C:/foo",
            "x.md#status",
            "..%2f0002-decision.md",
            "0002-decision.md?x",
        ):
            with self.subTest(target=target):
                self.adr(1, f"Superseded by [x]({target})")
                self.assertIn("unsafe_target", self.codes())

    def test_reference_link_reports_syntax(self):
        self.adr(1, "Superseded by [two][target]")
        self.assertIn("relation_syntax", self.codes())

    def test_malformed_url_does_not_crash(self):
        self.adr(1, "Superseded by [x](//[)")
        self.assertIn("unsafe_target", self.codes())

    def test_comment_marker_inside_fence_cannot_hide_relation(self):
        self.adr(1, "Accepted\n```html\n<!--\n```\nSupersedes [x](0009-missing.md)")
        self.assertIn("missing_target", self.codes())

    def test_utf8_bom_and_crlf(self):
        (self.root / "0001-decision.md").write_bytes(
            b"\xef\xbb\xbf# Decision\r\n\r\n## Status\r\n\r\nAccepted\r\n"
        )
        self.assertEqual(self.codes(), set())

    def test_symlink_rejected(self):
        target = self.root / "real.txt"
        target.write_text("# text")
        try:
            os.symlink(target, self.root / "0001-link.md")
        except OSError:
            self.skipTest("symlink privilege unavailable")
        with self.assertRaises(InputError):
            audit(self.root)

    def test_empty_directory(self):
        with self.assertRaises(InputError):
            audit(self.root)

    def test_invalid_utf8(self):
        (self.root / "0001-bad.md").write_bytes(b"\xff")
        with self.assertRaises(InputError):
            audit(self.root)

    def test_size_bound(self):
        (self.root / "0001-big.md").write_bytes(b"x" * (1024 * 1024 + 1))
        with self.assertRaises(InputError):
            audit(self.root)

    def test_cli_real_workflow_and_exit_codes(self):
        self.chain()

        def run(*args):
            return subprocess.run(
                [sys.executable, "-m", "adr_lineage", str(self.root), "--format", "json", *args],
                capture_output=True,
                text=True,
            )

        result = run("--resolve", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["resolution"]["current"], ["0003-decision.md"])
        self.adr(3, "Rejected\nSupersedes [2](0002-decision.md)")
        self.assertEqual(run().returncode, 1)
        self.assertEqual(run("--resolve", "99").returncode, 2)

    def test_deep_chain_no_recursion(self):
        for n in range(1, 1101):
            status = "Accepted" if n == 1100 else f"Superseded by [next]({n + 1:04d}-decision.md)"
            if n > 1:
                status += f"\nSupersedes [previous]({n - 1:04d}-decision.md)"
            self.adr(n, status)
        report = audit(self.root)
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["current"]["0001-decision.md"], ["1100-decision.md"])


if __name__ == "__main__":
    unittest.main()
