"""
Verbalized-confidence elicitation + a FIXED read site for the metacognition probe.

The correctness probe's honest failure (see interp/analysis/confidence_vs_difficulty.py)
was the READ SITE: reading at an entity token means that token's own identity/position
co-varies with correctness, so pass/fail are already separable at layer 0 (the raw
embedding) and the deep layers add almost nothing. The fix is to read at a
CONTENT-NEUTRAL, fixed-context slot.

So we ask the model to end its answer with `Confidence: N` and read the residual
stream at the digit token. That slot always has the same local context ("Confidence:")
and is a bare number, so its embedding does NOT encode which entities exist -> layer 0
there should be ~chance, and any mid-late signal is genuinely computed self-assessment.

Bonus: the stated N is a VERBALIZED confidence we can calibrate against the grade and
compare to the internal probe (interp/analysis/verbalized_vs_internal.py).

Pure string/offset code -- no model or GPU; unit-tested offline (interp/test_confidence.py).
"""
from __future__ import annotations

import re

# Appended to the generation prompt when capturing with --elicit-confidence.
CONFIDENCE_INSTRUCTION = (
    "\n\nAfter the construction, on the FINAL line and with nothing after it, state "
    "how likely the construction is geometrically correct and valid, in exactly this "
    "format:\nConfidence: N\nwhere N is an integer from 0 (certain it is wrong) to "
    "100 (certain it is correct)."
)

# 'Confidence: 73' / 'confidence = 5' -> capture the integer.
_CONF_RE = re.compile(r"[Cc]onfidence\s*[:=]\s*(\d{1,3})")


def add_confidence_request(messages: list[dict]) -> list[dict]:
    """Append the confidence instruction to the last user message (returns a copy)."""
    out = [dict(m) for m in messages]
    for m in reversed(out):
        if m.get("role") == "user":
            m["content"] = (m.get("content") or "") + CONFIDENCE_INSTRUCTION
            return out
    out.append({"role": "user", "content": CONFIDENCE_INSTRUCTION.strip()})
    return out


# --- two-turn (follow-up) elicitation: the CLEAN design ---
# Used with capture.py --confidence-followup: the construction is generated in turn 1
# WITHOUT any confidence instruction (so it is never truncated), then this fixed query
# is asked in turn 2 with the construction in context. The read site (the token that
# generates N) then has identical local context on every record -> content-neutral.
CONFIDENCE_QUERY = (
    "Now assess the construction you just produced. On a scale of 0 to 100, how "
    "confident are you that it is geometrically correct and valid? Reply with exactly "
    "one line and nothing else:\nConfidence: N"
)


def build_confidence_followup(messages: list[dict], construction: str) -> list[dict]:
    """Turn-2 messages: the original turn + the model's construction as its assistant
    reply + the fixed CONFIDENCE_QUERY. Non-mutating."""
    return list(messages) + [
        {"role": "assistant", "content": construction or ""},
        {"role": "user", "content": CONFIDENCE_QUERY},
    ]


def parse_confidence(completion: str) -> int | None:
    """The integer the model stated (LAST 'Confidence: N'), clamped to 0..100, or
    None if it never emitted one."""
    matches = _CONF_RE.findall(completion or "")
    if not matches:
        return None
    return max(0, min(100, int(matches[-1])))


def confidence_positions(completion: str, offsets) -> list[int]:
    """Completion-token positions covering the confidence DIGITS (the answer slot),
    from the LAST 'Confidence: N' occurrence. Maps the digits' char span to tokens via
    the saved char offsets, exactly like geometry_labels.id_positions, so capture (to
    decide which positions to keep) and probe (to place the read) stay aligned."""
    if offsets is None or not completion:
        return []
    matches = list(_CONF_RE.finditer(completion))
    if not matches:
        return []
    m = matches[-1]
    s, e = m.start(1), m.end(1)               # char span of the digits themselves
    return [pos for pos, (cs, ce) in enumerate(offsets) if cs < e and ce > s]


def confidence_read_positions(completion: str, offsets):
    """Read sites for the metacognition probe, from the LAST 'Confidence: N'.

    Returns (decision_pos, digit_positions):
      decision_pos    the token whose activation GENERATES the first digit -- i.e. the
                      ':'/space token right before the number. This is the causal
                      read-out site (its residual stream is what the model uses to
                      choose the value) AND is content-neutral: the same local context
                      every record regardless of the value, so its layer-0 embedding
                      cannot encode the answer. The PREFERRED probe site.
      digit_positions the number's own tokens (the state AFTER committing the value) --
                      kept for a comparison read (label_correctness_conf_digit).

    Returns (None, []) if there is no confidence marker.
    """
    if offsets is None or not completion:
        return None, []
    matches = list(_CONF_RE.finditer(completion))
    if not matches:
        return None, []
    m = matches[-1]
    digit_positions = [pos for pos, (cs, ce) in enumerate(offsets)
                       if cs < m.end(1) and ce > m.start(1)]
    decision_pos = None
    if digit_positions:
        first = min(digit_positions)
        if first > 0:
            decision_pos = first - 1          # token immediately before the number
    return decision_pos, digit_positions
