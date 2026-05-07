import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_PATH = Path(__file__).resolve().parents[1] / "tools" / "public_bench_server.py"
SPEC = importlib.util.spec_from_file_location("public_bench_server", SERVER_PATH)
public_bench_server = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(public_bench_server)


class PublicBenchServerTests(unittest.TestCase):
    def test_content_to_text_accepts_openai_text_parts(self):
        content = [
            {"type": "text", "text": "First"},
            {"type": "image_url", "image_url": {"url": "ignored"}},
            {"type": "text", "text": "Second"},
        ]

        self.assertEqual(public_bench_server.content_to_text(content), "First\nSecond")

    def test_prompt_from_chat_messages_preserves_multiturn_context(self):
        prompt = public_bench_server.prompt_from_chat_messages(
            [
                {"role": "system", "content": "Use concise answers."},
                {"role": "user", "content": "Question one"},
                {"role": "assistant", "content": "Answer one"},
                {"role": "user", "content": "Question two"},
            ]
        )

        self.assertIn("SYSTEM:\nUse concise answers.", prompt)
        self.assertIn("USER:\nQuestion one", prompt)
        self.assertIn("ASSISTANT:\nAnswer one", prompt)
        self.assertIn("USER:\nQuestion two", prompt)

    def test_prompt_from_chat_messages_uses_single_user_content_directly(self):
        self.assertEqual(
            public_bench_server.prompt_from_chat_messages([{"role": "user", "content": "Solve 2+2."}]),
            "Solve 2+2.",
        )

    def test_openai_chat_response_shape(self):
        data = public_bench_server.openai_chat_response("bench-model", "answer")

        self.assertEqual(data["object"], "chat.completion")
        self.assertEqual(data["model"], "bench-model")
        self.assertEqual(data["choices"][0]["message"]["role"], "assistant")
        self.assertEqual(data["choices"][0]["message"]["content"], "answer")
        self.assertEqual(data["choices"][0]["finish_reason"], "stop")
        self.assertIn("usage", data)

    def test_benchmark_state_turns_empty_ollama_message_into_empty_generation(self):
        class EmptyClient:
            def chat(self, **kwargs):
                raise public_bench_server.main.PipelineError("Ollama returned an empty assistant message.")

        state = public_bench_server.BenchmarkState(
            runtime=public_bench_server.main.RUNTIME_PROFILES["qwen3-8b-s2t-lite"],
            client=EmptyClient(),
            mode="main",
            model_alias="bench",
            canon="C1\nC2\nC3",
            runs_dir=Path("runs"),
        )

        self.assertEqual(state.generate("Question: 1+1?\nAnswer:", {"max_tokens": 256}), "")

    def test_main_state_returns_candidate_without_pipeline_verdict(self):
        class FakeClient:
            pass

        runtime = public_bench_server.main.RUNTIME_PROFILES["qwen3-8b-s2t-lite"]
        generation = public_bench_server.main.CandidateGeneration("candidate answer", {}, 1)
        state = public_bench_server.BenchmarkState(
            runtime=runtime,
            client=FakeClient(),
            mode="main",
            model_alias="A4",
            canon="C1\nC2\nC3",
            runs_dir=Path("runs"),
        )

        with patch.object(public_bench_server.main, "run_pipeline") as run_pipeline, patch.object(
            public_bench_server.main,
            "generate_candidate_result",
            return_value=generation,
        ) as generate_candidate_result:
            result = state.generate("Solve 2+2.", {"max_tokens": 16})

        self.assertEqual(result, "candidate answer")
        run_pipeline.assert_not_called()
        generate_candidate_result.assert_called_once()


if __name__ == "__main__":
    unittest.main()
