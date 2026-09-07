import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from lazy_cli.core.archiver import WikiArchiver
from lazy_cli.core.executor import ExecutionRefused, ExecutionResult, SafeExecutor


class ExecutorTests(unittest.TestCase):
    def test_executes_argv_without_a_shell_and_streams_output(self) -> None:
        lines: list[str] = []
        result = SafeExecutor().execute("printf hello", Path.cwd(), lines.append)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.output, "hello")
        self.assertEqual(lines, ["hello"])

    def test_refuses_blocked_and_shell_operator_commands(self) -> None:
        executor = SafeExecutor()
        with self.assertRaises(ExecutionRefused):
            executor.execute("rm -rf /", Path.cwd())
        with self.assertRaises(ExecutionRefused):
            executor.execute("echo hello | cat", Path.cwd())


class ArchiverTests(unittest.TestCase):
    def test_archives_only_successful_sanitized_results(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.md"
            archiver = WikiArchiver(path)
            archiver.archive("use API_KEY=super-secret", ExecutionResult(command="echo TOKEN=private", exit_code=0, output="Bearer abc.def"))
            archiver.archive("failed action", ExecutionResult(command="false", exit_code=1, output="failure"))
            content = path.read_text(encoding="utf-8")

        self.assertIn("[REDACTED]", content)
        self.assertNotIn("super-secret", content)
        self.assertNotIn("private", content)
        self.assertNotIn("failed action", content)


if __name__ == "__main__":
    unittest.main()
