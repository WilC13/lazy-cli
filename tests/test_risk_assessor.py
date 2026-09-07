import asyncio
import json
import unittest

import httpx

from lazy_cli.config import UserConfig
from lazy_cli.core.generator import CloudContextConsentRequired
from lazy_cli.core.guardrail import RiskLevel
from lazy_cli.core.risk_assessor import SemanticRiskAssessor
from lazy_cli.settings import LazySettings


class SemanticRiskAssessorTests(unittest.TestCase):
    def test_uses_ollama_and_returns_typed_assessment(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/chat")
            self.assertEqual(json.loads(request.content)["messages"][1]["content"], "git status")
            return httpx.Response(200, json={"message": {"content": '{"level":"safe","reason":"Read-only."}'}})

        assessor = SemanticRiskAssessor(LazySettings(), UserConfig(), httpx.MockTransport(handler))
        assessment = asyncio.run(assessor.assess("git status"))
        self.assertEqual(assessment.level, RiskLevel.SAFE)

    def test_cloud_assessment_requires_consent_before_request(self) -> None:
        assessor = SemanticRiskAssessor(LazySettings(), UserConfig(provider="openai"), httpx.MockTransport(lambda _: self.fail("must not request")))
        with self.assertRaises(CloudContextConsentRequired):
            asyncio.run(assessor.assess("git status"))


if __name__ == "__main__":
    unittest.main()
