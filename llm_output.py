"""
llm_output.py - Request settings and output validation for LLM summaries.

The pipeline talks to a reasoning model (GLM 5.3 behind sglang). Two things
must hold for a summary to be safe to publish:

1. The request must not disable sglang's reasoning/answer separation.
   ``chat_template_kwargs={"enable_thinking": False}`` does exactly that on
   GLM 5.3: the vendored chat template ignores the flag (the model still
   deliberates) while sglang stops splitting the deliberation out, so the whole
   chain of thought comes back as ``message.content``. We select the effort
   with ``reasoning_effort`` instead, which the template does honour.
2. Whatever comes back is validated before it is written into minutes, so a
   server-side change degrades to a retry and a visible error rather than to
   published deliberation.

Standard library only, so it can be tested without the pipeline's dependencies.
"""

import json
import os
import re

# GLM 5.3 FP8 on the lab's sglang server, which serves it under this id.
DEFAULT_MODEL = "continuum-1"

# "low" | "high" | "max" on that server; empty string sends nothing. "high"
# reasons briefly before answering at close to the cost of "low"; "max" reasons
# at length (about 8x slower per batch).
DEFAULT_REASONING_EFFORT = "high"

_OPENAI_HOSTS = ("api.openai.com",)

# max_completion_tokens per call kind. A reasoning model spends completion
# tokens on its scratchpad before the answer, so any effort that thinks needs
# room for both; with too little the answer comes back empty (finish=length).
_TOKEN_LIMITS = {
    "batch": {"env": "LLM_MAX_TOKENS_BATCH", "low": 10000, "thinking": 32000},
    "topic": {"env": "LLM_MAX_TOKENS_TOPIC", "low": 800, "thinking": 8000},
}


class LLMOutputError(ValueError):
    """The model's reply is not a publishable summary (empty, malformed or leaked reasoning)."""


def get_chat_completion_kwargs(base_url=None, **overrides):
    """
    Extra kwargs for chat.completions.create() against the configured endpoint.

    For a self-hosted OpenAI-compatible endpoint (sglang/vLLM) this selects the
    reasoning effort (default high) through the chat template. It never sends
    ``enable_thinking``: see the module docstring. The real OpenAI API rejects
    unknown body fields, so nothing extra is sent there.

    LLM_REASONING_EFFORT overrides the effort; set it to an empty value to send
    no chat_template_kwargs at all.

    Merge with caller-supplied kwargs by spreading the return value:
        client.chat.completions.create(..., **get_chat_completion_kwargs())
    """
    if base_url is None:
        base_url = os.getenv("OPENAI_BASE_URL") or ""
    effort = reasoning_effort()

    base = {}
    is_openai = any(host in base_url for host in _OPENAI_HOSTS)
    if effort and not is_openai:
        base["extra_body"] = {"chat_template_kwargs": {"reasoning_effort": effort}}
    base.update(overrides)
    return base


def reasoning_effort():
    """Configured reasoning effort ("" when none is sent)."""
    return os.getenv("LLM_REASONING_EFFORT", DEFAULT_REASONING_EFFORT).strip().lower()


def completion_token_limit(kind):
    """
    max_completion_tokens for a "batch" summary or a speaker "topic" summary.

    LLM_MAX_TOKENS_BATCH / LLM_MAX_TOKENS_TOPIC override it. Otherwise the limit
    follows the effort: a budget with room for the scratchpad at the default
    "high" and at "max", and the historical limits at "low" (no scratchpad).
    """
    spec = _TOKEN_LIMITS[kind]
    override = (os.getenv(spec["env"]) or "").strip()
    if override:
        return int(override)
    return spec["low"] if reasoning_effort() == "low" else spec["thinking"]


# -------------------------------------------------------------
# Output validation
# -------------------------------------------------------------

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

# "**Topic Title - Speaker Name** (H:MM:SS)" at the start of a line.
TOPIC_LINE_RE = re.compile(
    r"^\*\*[^*\n]+ - [^*\n]+\*\*\s*\(\d{1,2}:\d{2}:\d{2}\)", re.MULTILINE
)

# Phrases that only the model's scratchpad produces: planning aloud and
# restating the prompt. One is enough to reject a reply.
_STRONG_RE = re.compile(
    r"\b(?:let me|let's draft|the (?:format|prompt|instructions?) "
    r"(?:requires?|says?|asks?)|looking at the (?:transcript|segment|batch))\b",
    re.IGNORECASE,
)

# First-person and word-budget phrases. A third-person summary can contain one
# by accident ("Team I should learn this"), so it takes two distinct ones.
_WEAK_RE = re.compile(
    r"\b(?:I need to|I should|I'll|I will|I must|I have to|"
    r"the user (?:wants|asked|is asking) me|word count|\d+\s*-\s*\d+ words)\b"
)

# Quoted speech is where first person legitimately appears in minutes.
_QUOTED_RE = re.compile(r'"[^"\n]{0,300}"|\u201c[^\u201d\n]{0,300}\u201d')

# A short lead-in ("Here is the summary:") is dropped silently; anything longer
# in front of the first topic line is treated as deliberation.
_MAX_PREAMBLE_CHARS = 200


def strip_reasoning(text):
    """Remove <think> blocks; an unmatched </think> means everything before it was reasoning."""
    text = _THINK_BLOCK_RE.sub("", text or "")
    if "</think>" in text.lower():
        text = re.split(r"</think>", text, flags=re.IGNORECASE)[-1]
    return text.strip()


def deliberation_markers(text, min_weak=2):
    """
    Evidence that text is model deliberation rather than a summary, lower-cased.

    Quoted speech is ignored. Any strong phrase counts; weak phrases count once
    at least `min_weak` distinct ones occur.
    """
    text = _QUOTED_RE.sub(" ", text or "")
    strong = {m.group(0).lower() for m in _STRONG_RE.finditer(text)}
    weak = {m.group(0).lower() for m in _WEAK_RE.finditer(text)}
    if len(weak) < min_weak:
        weak = set()
    return sorted(strong | weak)


def extract_batch_summary(raw):
    """
    Return the topic lines of a batch summary, or raise LLMOutputError.

    Accepts only text whose body starts at a "**Topic - Speaker** (H:MM:SS)"
    line and carries no deliberation.
    """
    text = strip_reasoning(raw)
    if not text:
        raise LLMOutputError("empty response")

    first = TOPIC_LINE_RE.search(text)
    if not first:
        raise LLMOutputError("no '**Topic - Speaker** (H:MM:SS)' line in response")

    preamble = text[: first.start()].strip()
    if len(preamble) > _MAX_PREAMBLE_CHARS or deliberation_markers(preamble, min_weak=1):
        raise LLMOutputError(
            f"leaked reasoning before the first topic ({len(preamble)} chars)"
        )

    body = text[first.start():].strip()
    markers = deliberation_markers(body)
    if markers:
        raise LLMOutputError(f"leaked reasoning in summary body: {markers[:5]}")
    return body


def extract_json_summary(raw, required=("title", "content")):
    """
    Return the JSON object of a speaker/topic summary, or raise LLMOutputError.

    Tolerates a code fence or a short lead-in around the object; rejects
    missing fields and deliberation inside any required field.
    """
    text = strip_reasoning(raw)
    if not text:
        raise LLMOutputError("empty response")

    try:
        data = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise LLMOutputError("no JSON object in response")
        try:
            data = json.loads(text[start : end + 1])
        except ValueError as exc:
            raise LLMOutputError(f"invalid JSON in response: {exc}")

    if not isinstance(data, dict):
        raise LLMOutputError("JSON response is not an object")
    for key in required:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise LLMOutputError(f"missing '{key}' in JSON response")
        markers = deliberation_markers(value, min_weak=1)
        if markers:
            raise LLMOutputError(f"leaked reasoning in '{key}': {markers[:5]}")
    return data


def create_validated_completion(client, extract, max_attempts=3, **create_kwargs):
    """
    Call chat.completions.create() until `extract` accepts the reply.

    `extract` takes message.content and returns the cleaned value or raises
    LLMOutputError. Only message.content is ever read: reasoning_content is the
    model's scratchpad and is never a substitute for an answer. Raises the last
    LLMOutputError once max_attempts replies were rejected.
    """
    last_error = None
    for attempt in range(1, max_attempts + 1):
        response = client.chat.completions.create(**create_kwargs)
        choice = response.choices[0]
        content = choice.message.content or ""
        try:
            if not content.strip():
                raise LLMOutputError(
                    f"empty content (finish_reason={getattr(choice, 'finish_reason', None)})"
                )
            return extract(content)
        except LLMOutputError as exc:
            last_error = exc
            print(f"Warning: rejected LLM reply (attempt {attempt}/{max_attempts}): {exc}")
    raise last_error
