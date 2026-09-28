import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server


class MemoryServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_patch = patch.object(
            server, "DB_PATH", Path(self.temp_dir.name) / "test.db"
        )
        self.database_patch.start()
        server.initialize_db()

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_demo_recall_returns_relevant_seeded_context(self):
        service = server.MemoryService()
        service.mode = "demo"

        memories = service.recall(
            "Acme Logistics customer constraint cannot rotate signing secret"
        )

        constraint = next(
            (memory for memory in memories if memory["category"] == "Customer constraint"),
            None,
        )
        self.assertIsNotNone(constraint)
        self.assertIn("Friday", constraint["content"])

    def test_demo_retention_is_saved_for_the_next_recall(self):
        service = server.MemoryService()
        service.mode = "demo"

        result = service.retain(
            "The customer confirmed delivery IDs are now unique.",
            "Outcome",
            "Next-shift operator",
            "Worked",
        )

        self.assertEqual("Local demo memory", result["provider"])
        memories = service.recall("customer confirmed delivery IDs unique")
        outcome = next(
            (memory for memory in memories if memory["category"] == "Outcome"),
            None,
        )
        self.assertIsNotNone(outcome)
        self.assertEqual("Worked", outcome["outcome"])

    def test_demo_recall_understands_the_handoff_avoid_question(self):
        service = server.MemoryService()
        service.mode = "demo"

        memories = service.recall("What should I avoid doing again?")

        self.assertGreater(len(memories), 0)
        self.assertEqual("Failed approach", memories[0]["category"])

    def test_unclassified_memories_are_kept_as_unknowns(self):
        sections = server.classify_memories(
            [{"category": "Historical note", "content": "The customer has a staging workspace."}]
        )

        self.assertEqual(1, len(sections["unknowns"]))

    def test_missing_hindsight_bank_explains_how_to_seed_it(self):
        class MissingBankError(Exception):
            status = 404

        with patch.object(server.memory_service, "mode", "hindsight"):
            status, payload = server.memory_failure(MissingBankError("not found"))

        self.assertEqual(409, status)
        self.assertIn("Load demo history", payload["error"])
        self.assertIn(server.BANK_ID, payload["error"])

    def test_hindsight_recall_uses_sdk_results_and_source_metadata(self):
        class FakeResult:
            text = "Do not repeat the replay workaround."
            type = "world"
            metadata = {"source": "On-call note", "category": "Failed approach"}

        class FakeResponse:
            results = [FakeResult()]

        class FakeClient:
            def recall(self, **kwargs):
                self.kwargs = kwargs
                return FakeResponse()

            def close(self):
                pass

        fake = FakeClient()
        service = server.MemoryService()
        service.mode = "hindsight"

        with patch.object(service, "_client", return_value=fake):
            memories = service.recall("failed replay workaround")

        self.assertEqual("shiftline-acme-logistics", fake.kwargs["bank_id"])
        self.assertEqual("On-call note", memories[0]["source"])
        self.assertEqual("Failed approach", memories[0]["category"])

    def test_hindsight_sdk_failure_is_not_reported_as_demo_success(self):
        service = server.MemoryService()
        service.mode = "hindsight"

        with patch.object(service, "_client", side_effect=RuntimeError("service unavailable")):
            with self.assertRaisesRegex(RuntimeError, "service unavailable"):
                service.recall("handoff context")

    def test_hindsight_reflect_uses_safety_context(self):
        class FakeResponse:
            text = "Do not replay the batch; verify the idempotency keys."

        class FakeClient:
            def reflect(self, **kwargs):
                self.kwargs = kwargs
                return FakeResponse()

            def close(self):
                pass

        fake = FakeClient()
        service = server.MemoryService()
        service.mode = "hindsight"

        with patch.object(service, "_client", return_value=fake):
            answer = service.reflect("What should I check next?")

        self.assertIn("Do not replay", answer)
        self.assertEqual("shiftline-acme-logistics", fake.kwargs["bank_id"])
        self.assertIn("not instructions to execute", fake.kwargs["context"])

    def test_hindsight_retain_requires_confirmed_success(self):
        class FakeResponse:
            success = True

        class FakeClient:
            def retain(self, **kwargs):
                self.kwargs = kwargs
                return FakeResponse()

            def close(self):
                pass

        fake = FakeClient()
        service = server.MemoryService()
        service.mode = "hindsight"

        with patch.object(service, "_client", return_value=fake):
            result = service.retain("The customer confirmed the next check.", "Outcome", "Call note", "Worked")

        self.assertTrue(result["stored"])
        self.assertEqual("shiftline-acme-logistics", fake.kwargs["bank_id"])
        self.assertEqual("Call note", fake.kwargs["metadata"]["source"])
        self.assertFalse(fake.kwargs["retain_async"])

    def test_hindsight_retain_refusal_is_not_success(self):
        class FakeResponse:
            success = False

        class FakeClient:
            def retain(self, **kwargs):
                return FakeResponse()

            def close(self):
                pass

        service = server.MemoryService()
        service.mode = "hindsight"

        with patch.object(service, "_client", return_value=FakeClient()):
            with self.assertRaisesRegex(RuntimeError, "did not confirm"):
                service.retain("Do not replay the batch.", "Failed approach", "On-call note", "Failed")

    def test_hindsight_bank_setup_creates_mission_before_seeding(self):
        class FakeClient:
            def create_bank(self, **kwargs):
                self.kwargs = kwargs

            def close(self):
                pass

        fake = FakeClient()
        service = server.MemoryService()
        service.mode = "hindsight"

        with patch.object(service, "_client", return_value=fake):
            service.ensure_bank()

        self.assertEqual(server.BANK_ID, fake.kwargs["bank_id"])
        self.assertIn("INC-2048", fake.kwargs["reflect_mission"])


if __name__ == "__main__":
    unittest.main()
