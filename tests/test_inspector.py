import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from lazy_cli.core.inspector import inspect_argparse, scan_local_context


class InspectorTests(unittest.TestCase):
    def test_extracts_literal_argparse_options(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory) / "main.py"
            source.write_text(
                """import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--output', '-o', required=True, help='Output file')
parser.add_argument('--retries', default=3, action='store')
parser.add_argument('--api-key', default='do-not-disclose')
""",
                encoding="utf-8",
            )

            arguments = inspect_argparse(source)

        self.assertEqual(arguments[0].flags, ["--output", "-o"])
        self.assertEqual(arguments[0].destination, "output")
        self.assertTrue(arguments[0].required)
        self.assertEqual(arguments[1].default, 3)
        self.assertIsNone(arguments[2].default)

    def test_context_includes_env_names_but_never_values(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "OPENAI_API_KEY=private-value\nMODE=development\n", encoding="utf-8"
            )

            context = scan_local_context(root)
            serialized = context.model_dump_json()

        names = {variable.name: variable for variable in context.environment_variables}
        self.assertIn("OPENAI_API_KEY", names)
        self.assertTrue(names["OPENAI_API_KEY"].is_sensitive)
        self.assertIn("MODE", names)
        self.assertNotIn("private-value", serialized)


if __name__ == "__main__":
    unittest.main()
