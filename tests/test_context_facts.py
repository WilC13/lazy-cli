import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from lazy_cli.core.inspector import scan_local_context


class ContextFactsTests(unittest.TestCase):
    def test_reports_known_project_files_and_docker_fact(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text("{}", encoding="utf-8")
            (root / "Dockerfile").write_text("FROM python:3.13", encoding="utf-8")
            context = scan_local_context(root)

        self.assertEqual(context.files_present, ["package.json", "Dockerfile"])
        self.assertTrue(context.project_facts["docker_detected"])
        self.assertIsNone(context.git_status)


if __name__ == "__main__":
    unittest.main()
