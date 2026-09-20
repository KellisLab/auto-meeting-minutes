"""Regression tests for the reasoning leak: request settings and output validation."""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm_output import (  # noqa: E402
    LLMOutputError,
    completion_token_limit,
    create_validated_completion,
    extract_batch_summary,
    extract_json_summary,
    get_chat_completion_kwargs,
    strip_reasoning,
)

LOCAL = "https://kellis-h200-1.csail.mit.edu/agent/v1"

CLEAN = (
    "**Cache TTL Fix - Alice Example** (0:00:10): Alice Example reports that the "
    "<b>cache layer</b> drops entries after five minutes.\n"
    "**Invalidation Hook - Bob Sample** (0:04:32): Bob Sample proposes an "
    "<b>invalidation hook</b> on write and a one-hour TTL."
)

# The shape GLM 5.3 returned as message.content with enable_thinking=False.
LEAKED = (
    "Let me analyze this meeting transcript batch. The speakers are Alice Example "
    "and Bob Sample.\n\nKey topics discussed:\n\n1. Cache expiry\n2. Invalidation\n\n"
    "The format requires a single line per topic. I need to pick timestamps from "
    "the list. Let me draft:\n\n" + CLEAN + "\n\nWait, I should check the word count."
)


def reply(content, finish_reason="stop"):
    message = SimpleNamespace(content=content, reasoning_content="scratchpad")
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])


class FakeClient:
    def __init__(self, contents):
        self.calls = []
        queue = list(contents)

        def create(**kwargs):
            self.calls.append(kwargs)
            return reply(queue.pop(0))

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


class RequestSettings(unittest.TestCase):
    def test_never_sends_enable_thinking(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            kwargs = get_chat_completion_kwargs(base_url=LOCAL)
        template_kwargs = kwargs["extra_body"]["chat_template_kwargs"]
        self.assertNotIn("enable_thinking", template_kwargs)
        self.assertEqual(template_kwargs, {"reasoning_effort": "low"})

    def test_effort_is_configurable_and_can_be_disabled(self):
        with mock.patch.dict(os.environ, {"LLM_REASONING_EFFORT": "max"}, clear=True):
            kwargs = get_chat_completion_kwargs(base_url=LOCAL)
        self.assertEqual(kwargs["extra_body"]["chat_template_kwargs"]["reasoning_effort"], "max")
        with mock.patch.dict(os.environ, {"LLM_REASONING_EFFORT": ""}, clear=True):
            self.assertEqual(get_chat_completion_kwargs(base_url=LOCAL), {})

    def test_openai_gets_no_extra_body(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_chat_completion_kwargs(base_url="https://api.openai.com/v1"), {})

    def test_overrides_win(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            kwargs = get_chat_completion_kwargs(base_url=LOCAL, temperature=0.1)
        self.assertEqual(kwargs["temperature"], 0.1)


class TokenLimits(unittest.TestCase):
    def test_low_effort_keeps_the_historical_limits(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual((completion_token_limit("batch"), completion_token_limit("topic")), (10000, 800))

    def test_thinking_efforts_get_room_for_the_scratchpad(self):
        for effort in ("high", "max", ""):
            with mock.patch.dict(os.environ, {"LLM_REASONING_EFFORT": effort}, clear=True):
                self.assertEqual((completion_token_limit("batch"), completion_token_limit("topic")), (32000, 8000))

    def test_explicit_override_wins(self):
        env = {"LLM_REASONING_EFFORT": "max", "LLM_MAX_TOKENS_BATCH": "48000"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(completion_token_limit("batch"), 48000)
            self.assertEqual(completion_token_limit("topic"), 8000)


class BatchSummary(unittest.TestCase):
    def test_clean_summary_passes_unchanged(self):
        self.assertEqual(extract_batch_summary(CLEAN), CLEAN)

    def test_short_lead_in_is_dropped(self):
        self.assertEqual(extract_batch_summary("Here is the summary:\n\n" + CLEAN), CLEAN)

    def test_think_block_is_stripped(self):
        self.assertEqual(extract_batch_summary("<think>Let me plan.</think>\n" + CLEAN), CLEAN)
        self.assertEqual(strip_reasoning("Let me plan.</think>" + CLEAN), CLEAN)

    def test_leaked_deliberation_is_rejected(self):
        with self.assertRaisesRegex(LLMOutputError, "leaked reasoning"):
            extract_batch_summary(LEAKED)

    def test_deliberation_after_topics_is_rejected(self):
        with self.assertRaisesRegex(LLMOutputError, "summary body"):
            extract_batch_summary(CLEAN + "\n\nLet me double-check the timestamps.")

    def test_no_topic_line_is_rejected(self):
        with self.assertRaisesRegex(LLMOutputError, "no .*Topic"):
            extract_batch_summary("The meeting covered caching and invalidation.")
        with self.assertRaisesRegex(LLMOutputError, "empty"):
            extract_batch_summary("   ")

    def test_ordinary_minutes_are_not_flagged(self):
        # Shapes that occur in real minutes: quoted first person, "Team I should",
        # product talk about users, drafting as a topic.
        text = (
            "**PR Drafts - Alice Example** (0:10:00): Alice Example says the team will "
            'draft a PR and replies "I\'ll make it work, let me check" when asked about '
            "timing; Bob Sample suggests Team I should learn the method because the user "
            "wants to explore the correlation before the format is frozen."
        )
        self.assertEqual(extract_batch_summary(text), text)

    def test_two_first_person_phrases_outside_quotes_are_flagged(self):
        with self.assertRaisesRegex(LLMOutputError, "summary body"):
            extract_batch_summary(CLEAN + "\nI need to verify this. I should recount.")


class JsonSummary(unittest.TestCase):
    def test_plain_fenced_and_prefixed_json(self):
        obj = '{"title": "Cache TTL", "content": "Alice Example explains the <b>TTL</b>."}'
        for raw in (obj, "```json\n" + obj + "\n```", "Here you go: " + obj):
            self.assertEqual(extract_json_summary(raw)["title"], "Cache TTL")

    def test_rejects_leak_missing_field_and_garbage(self):
        with self.assertRaisesRegex(LLMOutputError, "leaked reasoning in 'title'"):
            extract_json_summary('{"title": "3-7 words - let me count", "content": "x"}')
        with self.assertRaisesRegex(LLMOutputError, "missing 'content'"):
            extract_json_summary('{"title": "Cache TTL"}')
        with self.assertRaisesRegex(LLMOutputError, "no JSON object"):
            extract_json_summary("Let me analyze this speaker.")


class ValidatedCompletion(unittest.TestCase):
    def test_retries_past_a_leak_and_returns_the_clean_reply(self):
        client = FakeClient([LEAKED, CLEAN])
        result = create_validated_completion(client, extract_batch_summary, model="m", messages=[])
        self.assertEqual(result, CLEAN)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[0], {"model": "m", "messages": []})

    def test_empty_content_never_falls_back_to_reasoning_content(self):
        client = FakeClient(["", "", ""])
        with self.assertRaisesRegex(LLMOutputError, "empty content"):
            create_validated_completion(client, extract_batch_summary, model="m", messages=[])
        self.assertEqual(len(client.calls), 3)

    def test_gives_up_with_an_error_instead_of_publishing_a_leak(self):
        client = FakeClient([LEAKED] * 3)
        with self.assertRaises(LLMOutputError):
            create_validated_completion(client, extract_batch_summary, model="m", messages=[])


if __name__ == "__main__":
    unittest.main()
