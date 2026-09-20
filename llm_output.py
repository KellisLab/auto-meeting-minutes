"""
llm_output.py - Request settings, output validation and retry policy for LLM summaries.

The pipeline talks to a reasoning model (GLM 5.3 behind sglang). Three things
must hold for a summary to be safe to publish:

1. The request must not disable sglang's reasoning/answer separation.
   ``chat_template_kwargs={"enable_thinking": False}`` does exactly that on
   GLM 5.3: the vendored chat template ignores the flag (the model still
   deliberates) while sglang stops splitting the deliberation out, so the whole
   chain of thought comes back as ``message.content``. We select the effort
   with ``reasoning_effort`` instead, which the template does honour.
2. The token budget must never shape the answer. Reasoning spends completion
   tokens before the answer starts, so a tight cap yields empty or cut-off
   summaries. The budget here is a runaway-protection ceiling far above any
   observed reply; a reply that still hits it is detected
   (finish_reason == "length"), retried with a larger budget, and never
   published truncated.
3. Whatever comes back is validated before it is written into minutes:
   structure (only well-formed topics survive), prompt echo (any run of the
   instructions repeated back), deliberation phrasing, draft restarts, and
   grounding of speakers and timestamps in the transcript. A rejected reply is
   retried and then reported as an error, never published.

Standard library only, so it can be tested without the pipeline's dependencies.
"""

import json
import os
import re
import time

# GLM 5.3 FP8 on the lab's sglang server, which serves it under this id.
DEFAULT_MODEL = "continuum-1"

# "low" | "high" | "max" on that server; empty string sends nothing. "high"
# reasons briefly before answering at close to the cost of "low"; "max" reasons
# at length (about 8x slower per batch).
DEFAULT_REASONING_EFFORT = "high"

_OPENAI_HOSTS = ("api.openai.com",)

# Runaway-protection ceilings for max_completion_tokens, not targets: the
# largest reply observed is ~13k tokens (a 15-minute batch at effort max).
_TOKEN_CEILINGS = {
    "batch": {"env": "LLM_MAX_TOKENS_BATCH", "default": 64000},
    "topic": {"env": "LLM_MAX_TOKENS_TOPIC", "default": 32000},
}
# A truncated reply is retried with the budget multiplied by this, up to the
# server's maximum output length.
_TRUNCATION_GROWTH = 2
_TOKEN_HARD_LIMIT = 96000

# Transient server failures (restarts, overload, dropped connections) are waited
# out: 2, 4, 8, ... seconds, capped, for LLM_TRANSIENT_RETRIES tries (~6 min).
_BACKOFF_FIRST_SECONDS = 2
_BACKOFF_CAP_SECONDS = 120
_DEFAULT_TRANSIENT_RETRIES = 8
_TRANSIENT_ERROR_NAMES = {
    "APIConnectionError", "APITimeoutError", "InternalServerError", "RateLimitError",
    "ConnectError", "ReadTimeout", "ConnectTimeout", "RemoteProtocolError",
    "ConnectionError", "TimeoutError",
}


class LLMOutputError(ValueError):
    """The model's reply is not a publishable summary (empty, truncated, malformed or leaked reasoning)."""


class LLMTruncatedError(LLMOutputError):
    """The reply stopped at the token budget (finish_reason == "length")."""


# -------------------------------------------------------------
# Request settings
# -------------------------------------------------------------

def reasoning_effort():
    """Configured reasoning effort ("" when none is sent)."""
    return os.getenv("LLM_REASONING_EFFORT", DEFAULT_REASONING_EFFORT).strip().lower()


def completion_token_limit(kind):
    """
    max_completion_tokens for a "batch" summary or a speaker "topic" summary.

    This is a ceiling against runaway generation, deliberately far above any
    real reply so that it never shapes one. LLM_MAX_TOKENS_BATCH /
    LLM_MAX_TOKENS_TOPIC override it; "0", "none" or "unlimited" removes the
    limit so that only the model's context window applies (returns None).
    """
    spec = _TOKEN_CEILINGS[kind]
    override = (os.getenv(spec["env"]) or "").strip().lower()
    if override in ("0", "none", "unlimited"):
        return None
    if override:
        return int(override)
    return spec["default"]


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


# -------------------------------------------------------------
# Leak detection
# -------------------------------------------------------------

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

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

# Scaffold of structured replies and of the prompts themselves.
_SCAFFOLD_RE = re.compile(
    r"PRIMARY_SPEAKER:|\[Brief descriptive title|\[Detailed summary in|"
    r"SPEAKER TIMESTAMPS|NON-NEGOTIABLE GUARDRAILS|INTERNAL SELF-CHECK|"
    r"</?(?:speaker_timestamps|transcript)\b"
)

# Quoted speech is where first person legitimately appears in minutes.
_QUOTED_RE = re.compile(r'"[^"\n]{0,300}"|“[^”\n]{0,300}”')

_WORD_RE = re.compile(r"[a-z0-9']+")
_ECHO_NGRAM = 8


def strip_reasoning(text):
    """Remove <think> blocks; an unmatched </think> means everything before it was reasoning."""
    text = _THINK_BLOCK_RE.sub("", text or "")
    if "</think>" in text.lower():
        text = re.split(r"</think>", text, flags=re.IGNORECASE)[-1]
    return text.strip()


def deliberation_markers(text, min_weak=2):
    """
    Evidence that text is model deliberation rather than a summary, lower-cased.

    Quoted speech is ignored. Any strong phrase or scaffold fragment counts;
    weak phrases count once at least `min_weak` distinct ones occur.
    """
    text = _QUOTED_RE.sub(" ", text or "")
    found = {m.group(0).lower() for m in _STRONG_RE.finditer(text)}
    found |= {m.group(0).lower() for m in _SCAFFOLD_RE.finditer(text)}
    weak = {m.group(0).lower() for m in _WEAK_RE.finditer(text)}
    if len(weak) >= min_weak:
        found |= weak
    return sorted(found)


def _ngrams(text, n=_ECHO_NGRAM):
    words = _WORD_RE.findall((text or "").lower())
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def prompt_echo(text, instructions):
    """
    Runs of `instructions` repeated in `text` (8 consecutive words or more).

    This is independent of any phrase list: a model that restates its rules,
    in whatever words the rules were given, is caught by the overlap itself.
    Pass only the instruction text, never the transcript, which a summary may
    legitimately share words with.
    """
    if not instructions:
        return []
    return sorted(_ngrams(text) & _ngrams(instructions))


# -------------------------------------------------------------
# Batch summaries: "**Topic - Speaker** (H:MM:SS): Content"
# -------------------------------------------------------------

# Header at the start of a line; the content follows on the same line or the next.
TOPIC_LINE_RE = re.compile(
    r"^\*\*(?P<title>[^*\n]+?)\s+-\s+(?P<speakers>[^*\n]+?)\*\*\s*"
    r"\((?P<time>\d{1,2}:\d{2}:\d{2})\)\s*:?[ \t]*(?P<inline>[^\n]*)$",
    re.MULTILINE,
)

# A short lead-in ("Here is the summary:") or sign-off is dropped silently;
# anything longer around the topics is treated as deliberation.
_MAX_STRAY_CHARS = 200
_MIN_CONTENT_CHARS = 40
_SPEAKER_SPLIT_RE = re.compile(r"\s*(?:,|&|/|\band\b)\s*", re.IGNORECASE)


def time_to_seconds(time_str):
    h, m, s = (int(p) for p in time_str.split(":"))
    return h * 3600 + m * 60 + s


def seconds_to_time(seconds):
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def parse_topics(text):
    """
    Split a reply into topics and stray text.

    Returns (topics, stray): each topic is a dict with title, speakers (the raw
    header field), time and content; stray is the list of text runs that belong
    to no topic.
    """
    headers = list(TOPIC_LINE_RE.finditer(text))
    if not headers:
        return [], ([text.strip()] if text.strip() else [])

    topics, stray = [], []
    lead = text[: headers[0].start()].strip()
    if lead:
        stray.append(lead)
    for i, h in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text[h.end():end]) if p.strip()]
        inline = h.group("inline").strip()
        if inline:
            content, extra = inline, paragraphs
        else:
            content, extra = (paragraphs[0] if paragraphs else ""), paragraphs[1:]
        stray.extend(extra)
        topics.append({
            "title": " ".join(h.group("title").split()),
            "speakers": " ".join(h.group("speakers").split()),
            "time": h.group("time"),
            "content": " ".join(content.split()),
        })
    return topics, stray


def _name_tokens(name):
    return {t for t in _WORD_RE.findall(name.lower()) if len(t) > 1}


def ground_topics(topics, entries):
    """
    Tie topics to the transcript they summarize.

    `entries` are the batch's transcript entries (name, seconds).
    - A header none of whose speakers unambiguously names someone in the batch
      names someone who did not speak: LLMOutputError.
    - A timestamp that is not in the transcript is snapped to the nearest real
      one, preferring the named speakers' own entries.
    - Topics are returned in chronological order without exact repeats.
    """
    by_speaker = {}
    for e in entries:
        by_speaker.setdefault(e["name"], []).append(e["seconds"])
    speaker_tokens = {name: _name_tokens(name) for name in by_speaker}
    all_seconds = sorted({e["seconds"] for e in entries})

    grounded = []
    for topic in topics:
        named = [n for n in _SPEAKER_SPLIT_RE.split(topic["speakers"]) if n.strip()]
        # A name is grounded by the exact spelling or by a shortened form
        # ("Alice") that fits exactly one speaker. A conflated name ("Alice
        # Sample" for Alice Example and Bob Sample) fits nobody.
        matched = []
        for n in named:
            tokens = _name_tokens(n)
            fits = [known for known, kt in speaker_tokens.items() if tokens and tokens <= kt]
            if n in by_speaker:
                matched.append(n)
            elif len(fits) == 1:
                matched.append(fits[0])
        if named and not matched:
            raise LLMOutputError(
                f"topic '{topic['title']}' names a speaker not in this batch: {topic['speakers']}"
            )

        seconds = time_to_seconds(topic["time"])
        if seconds not in all_seconds:
            pool = sorted({s for known in matched for s in by_speaker[known]}) or all_seconds
            seconds = min(pool, key=lambda s: abs(s - seconds))
            topic = dict(topic, time=seconds_to_time(seconds))
        grounded.append((seconds, topic))

    grounded.sort(key=lambda pair: pair[0])
    seen, result = set(), []
    for _, topic in grounded:
        key = (topic["time"], topic["title"].lower())
        if key not in seen:
            seen.add(key)
            result.append(topic)
    return result


def format_topics(topics):
    return "\n\n".join(
        f"**{t['title']} - {t['speakers']}** ({t['time']}): {t['content']}" for t in topics
    )


def extract_batch_summary(raw, entries=None, instructions=None):
    """
    Return the clean topic lines of a batch summary, or raise LLMOutputError.

    Only well-formed topics survive: text around them is dropped when it is a
    short lead-in or sign-off and rejected when it is deliberation. With
    `instructions` (the prompt's rules) any echo of them is rejected; with
    `entries` (the batch transcript) speakers and timestamps are grounded.
    """
    text = strip_reasoning(raw)
    if not text:
        raise LLMOutputError("empty response")

    topics, stray = parse_topics(text)
    if not topics:
        raise LLMOutputError("no '**Topic - Speaker** (H:MM:SS)' line in response")

    for run in stray:
        if len(run) > _MAX_STRAY_CHARS or deliberation_markers(run, min_weak=1):
            raise LLMOutputError(f"leaked reasoning around the topics ({len(run)} chars)")

    titles = [t["title"].lower() for t in topics]
    if len(set(titles)) < len(titles):
        raise LLMOutputError("topics restart (a draft and a final list in one reply)")

    for t in topics:
        if len(t["content"]) < _MIN_CONTENT_CHARS:
            raise LLMOutputError(f"topic '{t['title']}' has no content")
        markers = deliberation_markers(t["title"], min_weak=1) or deliberation_markers(t["content"])
        if markers:
            raise LLMOutputError(f"leaked reasoning in topic '{t['title'][:60]}': {markers[:5]}")

    echoed = prompt_echo(format_topics(topics), instructions)
    if echoed:
        raise LLMOutputError(f"the reply repeats its instructions: '{echoed[0]}'")

    if entries:
        topics = ground_topics(topics, entries)
    return format_topics(topics)


# -------------------------------------------------------------
# Speaker/topic summaries: a JSON object
# -------------------------------------------------------------

def extract_json_summary(raw, required=("title", "content"), instructions=None):
    """
    Return the JSON object of a speaker/topic summary, or raise LLMOutputError.

    Tolerates a code fence or a short lead-in around the object; rejects
    missing fields, deliberation inside any required field and echoes of
    `instructions`.
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
            data = json.loads(text[start:end + 1])
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
        echoed = prompt_echo(value, instructions)
        if echoed:
            raise LLMOutputError(f"'{key}' repeats its instructions: '{echoed[0]}'")
    return data


# -------------------------------------------------------------
# Calling the model
# -------------------------------------------------------------

def is_transient_error(exc):
    """Server restarts, overload and dropped connections: worth waiting out."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and (status >= 500 or status in (408, 409, 429)):
        return True
    return any(cls.__name__ in _TRANSIENT_ERROR_NAMES for cls in type(exc).__mro__)


def _transient_retries():
    value = (os.getenv("LLM_TRANSIENT_RETRIES") or "").strip()
    return int(value) if value else _DEFAULT_TRANSIENT_RETRIES


def create_validated_completion(client, extract, max_attempts=3, sleep=time.sleep, **create_kwargs):
    """
    Call chat.completions.create() until `extract` accepts the reply.

    `extract` takes message.content and returns the cleaned value or raises
    LLMOutputError. Only message.content is ever read: reasoning_content is the
    model's scratchpad and is never a substitute for an answer.

    - A transient server error is waited out with exponential backoff and does
      not count as an attempt.
    - A reply cut off by the token budget is never validated or published; the
      call is repeated with a larger budget.
    - After max_attempts rejected replies the last LLMOutputError is raised.
    """
    create_kwargs = {k: v for k, v in create_kwargs.items() if v is not None}
    transient_left = _transient_retries()
    backoff = _BACKOFF_FIRST_SECONDS
    last_error = None
    attempt = 0
    while attempt < max_attempts:
        try:
            response = client.chat.completions.create(**create_kwargs)
        except Exception as exc:
            if not is_transient_error(exc) or transient_left <= 0:
                raise
            transient_left -= 1
            print(f"Warning: LLM server unavailable ({type(exc).__name__}); retrying in {backoff}s")
            sleep(backoff)
            backoff = min(backoff * 2, _BACKOFF_CAP_SECONDS)
            continue

        attempt += 1
        choice = response.choices[0]
        content = choice.message.content or ""
        finish = getattr(choice, "finish_reason", None)
        try:
            if finish == "length":
                budget = create_kwargs.get("max_completion_tokens")
                if budget and budget < _TOKEN_HARD_LIMIT:
                    create_kwargs["max_completion_tokens"] = min(budget * _TRUNCATION_GROWTH, _TOKEN_HARD_LIMIT)
                raise LLMTruncatedError(f"reply cut off at the token budget ({budget})")
            if not content.strip():
                raise LLMOutputError(f"empty content (finish_reason={finish})")
            return extract(content)
        except LLMOutputError as exc:
            last_error = exc
            print(f"Warning: rejected LLM reply (attempt {attempt}/{max_attempts}): {exc}")
    raise last_error
