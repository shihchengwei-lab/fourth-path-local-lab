import importlib.util
import unittest
from pathlib import Path


SERVER_PATH = Path(__file__).resolve().parents[1] / "tools" / "adapter_public_bench_server.py"
SPEC = importlib.util.spec_from_file_location("adapter_public_bench_server", SERVER_PATH)
adapter_public_bench_server = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(adapter_public_bench_server)


class AdapterPublicBenchServerTests(unittest.TestCase):
    def test_normalized_chat_messages_accepts_openai_text_parts(self):
        messages = adapter_public_bench_server.normalized_chat_messages(
            [
                {"role": "system", "content": "Be brief."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "First"},
                        {"type": "image_url", "image_url": {"url": "ignored"}},
                        {"type": "text", "text": "Second"},
                    ],
                },
                {"role": "tool", "content": "Tool output"},
            ]
        )

        self.assertEqual(
            messages,
            [
                {"role": "system", "content": "Be brief."},
                {"role": "user", "content": "First\nSecond"},
                {"role": "user", "content": "Tool output"},
            ],
        )

    def test_generation_kwargs_turns_zero_temperature_into_greedy_decoding(self):
        options = adapter_public_bench_server.main.ModelOptions(
            num_predict=128,
            temperature=0.0,
            top_p=0.8,
            top_k=20,
        )

        kwargs = adapter_public_bench_server.generation_kwargs_from_options(
            options,
            fallback_max_new_tokens=512,
        )

        self.assertEqual(kwargs["max_new_tokens"], 128)
        self.assertFalse(kwargs["do_sample"])
        self.assertEqual(kwargs["top_p"], 0.8)
        self.assertEqual(kwargs["top_k"], 20)
        self.assertNotIn("temperature", kwargs)

    def test_generation_kwargs_keeps_positive_temperature_sampling(self):
        options = adapter_public_bench_server.main.ModelOptions(temperature=0.7)

        kwargs = adapter_public_bench_server.generation_kwargs_from_options(
            options,
            fallback_max_new_tokens=256,
        )

        self.assertEqual(kwargs["max_new_tokens"], 256)
        self.assertTrue(kwargs["do_sample"])
        self.assertEqual(kwargs["temperature"], 0.7)

    def test_request_model_options_maps_openai_request_limits(self):
        options = adapter_public_bench_server.request_model_options(
            {"max_tokens": 33, "temperature": 0.2, "top_p": 0.9},
            default_max_new_tokens=512,
        )

        self.assertEqual(options.num_predict, 33)
        self.assertEqual(options.temperature, 0.2)
        self.assertEqual(options.top_p, 0.9)

    def test_raw_state_uses_original_benchmark_messages(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def raw_chat(self, messages, request):
                self.calls.append((messages, request))
                return "raw answer"

        client = FakeClient()
        state = adapter_public_bench_server.AdapterBenchmarkState(
            runtime=adapter_public_bench_server.main.RUNTIME_PROFILES["qwen3-8b-local-max"],
            client=client,
            mode="raw",
            model_alias="A2",
            canon="C1\nC2\nC3",
            runs_dir=Path("runs"),
        )
        messages = [{"role": "user", "content": "Solve 2+2."}]

        self.assertEqual(state.generate("Solve 2+2.", messages, {"max_tokens": 16}), "raw answer")
        self.assertEqual(client.calls, [(messages, {"max_tokens": 16})])


if __name__ == "__main__":
    unittest.main()
