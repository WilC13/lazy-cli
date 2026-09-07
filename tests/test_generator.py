import asyncio
import json
import unittest

import httpx

from lazy_cli.config import UserConfig
from lazy_cli.core.generator import CloudContextConsentRequired, OllamaGenerator, OpenAICompatibleGenerator
from lazy_cli.core.inspector import EnvironmentVariable, LocalContext


class GeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = LocalContext(
            working_directory="/workspace",
            environment_variables=[EnvironmentVariable(name="OPENAI_API_KEY", is_sensitive=True)],
        )

    def test_ollama_returns_a_structured_proposal(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/chat")
            payload = json.loads(request.content)
            self.assertIn("Local context", payload["messages"][1]["content"])
            return httpx.Response(200, json={"message": {"content": '{"command":"git status","explanation":"Shows status","assumptions":[]}'}})

        generator = OllamaGenerator("qwen2.5:7b", "http://ollama.local", UserConfig(), httpx.MockTransport(handler))
        proposal = asyncio.run(generator.generate("show git status", self.context))
        self.assertEqual(proposal.command, "git status")

    def test_cloud_provider_requires_consent_before_request(self) -> None:
        generator = OpenAICompatibleGenerator("openai", "gpt-4o-mini", "https://example.test", "key", UserConfig(provider="openai"), httpx.MockTransport(lambda _: self.fail("must not request")))
        with self.assertRaises(CloudContextConsentRequired):
            asyncio.run(generator.generate("show git status", self.context))

    def test_minimal_context_excludes_environment_variable_names(self) -> None:
        received_content = ""

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal received_content
            received_content = json.loads(request.content)["messages"][1]["content"]
            return httpx.Response(200, json={"message": {"content": '{"command":"pwd","explanation":"Shows directory"}'}})

        config = UserConfig(context_sharing="minimal")
        generator = OllamaGenerator("qwen2.5:7b", "http://ollama.local", config, httpx.MockTransport(handler))
        asyncio.run(generator.generate("where am I", self.context))
        self.assertNotIn("OPENAI_API_KEY", received_content)


if __name__ == "__main__":
    unittest.main()
