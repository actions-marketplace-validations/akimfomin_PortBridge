"""Protect the environment field that is actually submitted by the historical MCP pilot."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


class PilotPlatformTest(unittest.TestCase):
    def test_submitted_reports_record_the_detected_system(self):
        root = Path(__file__).resolve().parents[1]
        script = root / "audit" / "agent_pilot.py"
        runner = (
            "import runpy, sys; from unittest.mock import patch\n"
            "system, script, workspace = sys.argv[1:]\n"
            "sys.argv = [script, workspace]\n"
            "with patch('platform.system', return_value=system):\n"
            "    runpy.run_path(script, run_name='__main__')\n"
        )
        with TemporaryDirectory() as folder:
            for system in ("Linux", "Windows"):
                with self.subTest(system=system):
                    output = Path(folder) / system
                    subprocess.run([sys.executable, "-B", "-c", runner, system, str(script), str(output)],
                                   cwd=root, capture_output=True, check=True, timeout=120)
                    report = json.loads((output / "pilot.json").read_bytes())
                    self.assertEqual(len(report["cases"]), 3)
                    for case in report["cases"]:
                        self.assertEqual(case["report"]["environment"],
                                         f"Isolated {system} Python clients; public pinned sources")
                    self.assertIs(report["external_adoption"], False)
