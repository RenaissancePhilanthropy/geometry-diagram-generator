from __future__ import annotations

import ast
import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional, TypedDict

from pydantic import BaseModel, Field, ValidationError
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage

from .base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from .llm import (
    get_chat_model, is_gemini_model, requires_raw_text_generation,
    requires_forced_function_calling, extract_usage, extract_cost, make_system_message,
)
from .instructions_python_full import build_python_full_instructions
from .ir_pipeline import StructuredRunResult, run_ir_pipeline
from .structured import dispatch_query
from ..ir.edit_diagnostics import check_edit_locality
from ..ir.errors import IRCompileError
from ..ir.render_util import build_entity_manifest
from ..ir.renderer import Renderer, SVGRenderer, TikZRenderer
from ..pydsl.patch import apply_script_patch
from ..pydsl.search_replace import apply_search_replace
from ..pydsl.hashline import apply_hashline_ops, render_hashline_view
from ..pydsl.line_number import apply_line_number_ops, render_line_number_view
from ..pydsl.sandbox import run_script

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
SANDBOX_TIMEOUT_SECONDS = 10.0  # vs. run_script's own 5.0 default — real LLM-generated
                                 # constructions may be larger than hand-authored test scripts.

_BUILD_AGENT_INSTRUCTIONS = """\
You are a geometry diagram assistant. Call render_diagram with a natural \
language description to create or edit a diagram — on the first call it \
creates a new diagram; on later calls it edits whatever was last \
rendered, using the previous script as context. Call query_diagram for \
read-only geometric facts (coordinates, distances, angles, lengths, \
areas, perimeters) about the most recently rendered diagram. Briefly \
explain what you did after each render_diagram call."""


class PydslScriptPatchOutput(BaseModel):
    patch: str = Field(description="A unified diff patch to apply to the previous script.")


async def _generate_patch(prompt: str, model: str, enable_cache: bool = False) -> str:
    """Single direct LLM call requesting a unified-diff patch (patch mode's
    generation step) — deliberately NOT the multi-attempt generate_script
    retry loop full_rewrite mode uses; a patch that doesn't apply is
    reported as a failed edit turn rather than retried with a fresh model
    call, per the design doc's caution around patch-mode robustness.

    Includes the same pydsl API reference (build_python_full_instructions)
    that full-script generation gets as a system message — without it, the
    model has no information about the actual API surface and hallucinates
    plausible-but-nonexistent calls (confirmed via live testing: draw()
    called with a fill_color/fill_opacity kwarg that doesn't exist — the
    real API is a separate fill(obj, color=...) call — and an AngleRef
    treated as having a .mark_right_angle() method, when the real API is
    the standalone mark_right_angle(ref) function)."""
    llm = get_chat_model(model, enable_cache=enable_cache)
    structured = llm.with_structured_output(PydslScriptPatchOutput, include_raw=False)
    messages = [
        make_system_message(build_python_full_instructions(), enable_cache=enable_cache, model_id=model),
        HumanMessage(content=prompt),
    ]
    response = await structured.ainvoke(messages)
    return response.patch


def build_patch_request_prompt(request: str, previous_script: str, manifest: dict) -> str:
    """Prompt for patch mode's single LLM call: same context as
    build_edit_prompt, but asking for a unified diff instead of a full
    script."""
    manifest_json = json.dumps(manifest, indent=2)
    return (
        f"{request}\n\n---\nPrevious script:\n```python\n{previous_script}\n```\n\n"
        f"Entity manifest:\n{manifest_json}\n---\n"
        "Respond with ONLY a unified diff patch (@@ hunk headers, then "
        "' '/'-'/'+' lines) to apply to the previous script — not a full "
        "script. Keep the exact same variable name for anything you are "
        "not intentionally changing."
    )


_SEARCH_MARKER = "<<<<<<< SEARCH"
_DIVIDER_MARKER = "======="
_REPLACE_MARKER = ">>>>>>> REPLACE"


def _parse_search_replace_blocks(text: str) -> list[dict]:
    """Parse Aider-style SEARCH/REPLACE marker blocks from raw model text
    into [{"old_string": ..., "new_string": ...}, ...].

    This plain-text, marker-delimited format replaced an earlier
    structured-output (Pydantic list-of-objects) design after direct
    reproduction confirmed Claude's native tool-calling sometimes
    hand-serializes that array as malformed text instead of a valid
    nested JSON array — both with raw embedded newlines AND unescaped
    inner quotes (e.g. `D.label("D")`'s quotes left unescaped), the
    second of which no JSON parser can safely recover (an unescaped `"`
    is genuinely ambiguous with the string's real closing quote). A
    marker-delimited format has no JSON escaping to get wrong at all:
    old/new content is copied verbatim between markers, newlines and
    quotes included, with no encoding step in between.
    """
    lines = text.splitlines()
    blocks: list[dict] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() != _SEARCH_MARKER:
            i += 1
            continue
        i += 1
        old_lines: list[str] = []
        while i < len(lines) and lines[i].strip() != _DIVIDER_MARKER:
            old_lines.append(lines[i])
            i += 1
        if i >= len(lines):
            raise ValueError("search_replace block missing '=======' divider")
        i += 1  # skip divider
        new_lines: list[str] = []
        while i < len(lines) and lines[i].strip() != _REPLACE_MARKER:
            new_lines.append(lines[i])
            i += 1
        if i >= len(lines):
            raise ValueError("search_replace block missing '>>>>>>> REPLACE' marker")
        i += 1  # skip replace marker
        blocks.append({"old_string": "\n".join(old_lines), "new_string": "\n".join(new_lines)})
    if not blocks:
        raise ValueError("no search/replace blocks found in response")
    return blocks


async def generate_search_replace(prompt: str, model: str, enable_cache: bool = False) -> list[dict]:
    """Single direct LLM call requesting SEARCH/REPLACE marker blocks as
    plain text (search_replace mode's generation step) — no structured
    output for this call; see _parse_search_replace_blocks's docstring
    for why. Still includes the pydsl API reference as a system message
    (omitting it is a confirmed way to get hallucinated API calls).

    Public: this is the one piece of a search_replace edit turn that
    isn't otherwise reconstructable from build_search_replace_request_prompt
    + apply_search_replace + run_script/run_ir_pipeline alone — a consumer
    building its own conversational agent around a search_replace tool
    (rather than PythonFullStrategy.build_agent()'s own ReAct agent) needs
    this exported to avoid depending on a private function."""
    llm = get_chat_model(model, enable_cache=enable_cache)
    messages = [
        make_system_message(build_python_full_instructions(), enable_cache=enable_cache, model_id=model),
        HumanMessage(content=prompt),
    ]
    response = await llm.ainvoke(messages)
    text = response.content if isinstance(response.content, str) else response.content[0].get("text", "")
    return _parse_search_replace_blocks(text)


def build_search_replace_request_prompt(request: str, previous_script: str, manifest: dict) -> str:
    """Prompt for search_replace mode's single LLM call: same context as
    build_edit_prompt/build_patch_request_prompt, but asking for
    SEARCH/REPLACE marker blocks (plain text, not JSON) instead of a full
    script or a diff."""
    manifest_json = json.dumps(manifest, indent=2)
    return (
        f"{request}\n\n---\nPrevious script:\n```python\n{previous_script}\n```\n\n"
        f"Entity manifest:\n{manifest_json}\n---\n"
        "Respond with one or more SEARCH/REPLACE blocks, in exactly this "
        "format and nothing else (no prose, no code fences around the "
        "blocks themselves):\n"
        f"{_SEARCH_MARKER}\n"
        "<exact text to find>\n"
        f"{_DIVIDER_MARKER}\n"
        "<replacement text>\n"
        f"{_REPLACE_MARKER}\n\n"
        "The search text of each block must be copied EXACTLY (verbatim, "
        "including whitespace) from the previous script above, and must "
        "be unique in it — if the exact text you want to change appears "
        "more than once, include enough surrounding context to make it "
        "unique. Blocks apply in order; an earlier block's replacement "
        "text can affect what a later block's search text matches "
        "against. Keep the exact same variable name for anything you are "
        "not intentionally changing."
    )


class HashlineOp(BaseModel):
    kind: str = Field(description='One of "insert", "delete", "replace", "block_replace".')
    tag: Optional[str] = Field(default=None, description="Line tag, for delete/replace ops.")
    after: Optional[str] = Field(default=None, description='Tag to insert after, or "start", for insert ops.')
    start_tag: Optional[str] = Field(default=None, description="First tag of the range, for block_replace.")
    end_tag: Optional[str] = Field(default=None, description="Last tag of the range, for block_replace.")
    content: Optional[str] = Field(default=None, description="New content, for insert/replace/block_replace.")


class PydslHashlineOutput(BaseModel):
    ops: list[HashlineOp] = Field(description="Hashline operations to apply in order.")


async def _generate_hashline_ops(prompt: str, model: str, enable_cache: bool = False) -> list[dict]:
    """Single direct LLM call requesting hashline ops (hashline mode's
    generation step) — mirrors _generate_patch/generate_search_replace's
    shape, including the pydsl API reference as a system message."""
    llm = get_chat_model(model, enable_cache=enable_cache)
    structured = llm.with_structured_output(PydslHashlineOutput, include_raw=False)
    messages = [
        make_system_message(build_python_full_instructions(), enable_cache=enable_cache, model_id=model),
        HumanMessage(content=prompt),
    ]
    response = await structured.ainvoke(messages)
    return [op.model_dump() for op in response.ops]


def build_hashline_request_prompt(request: str, hashline_view: str, manifest: dict) -> str:
    """Prompt for hashline mode's single LLM call: shows the tagged
    (annotated) script view instead of the plain script, and asks for
    structured line-anchored operations instead of a diff or search/replace
    blocks."""
    manifest_json = json.dumps(manifest, indent=2)
    return (
        f"{request}\n\n---\nPrevious script (each line tagged "
        f"line_number:hash):\n```\n{hashline_view}\n```\n\n"
        f"Entity manifest:\n{manifest_json}\n---\n"
        "Respond with a list of operations, each one of:\n"
        '- {"kind": "insert", "after": "<tag or \'start\'>", "content": "<new line>"}\n'
        '- {"kind": "delete", "tag": "<tag>"}\n'
        '- {"kind": "replace", "tag": "<tag>", "content": "<new line>"}\n'
        '- {"kind": "block_replace", "start_tag": "<tag>", "end_tag": "<tag>", "content": "<new lines>"}\n'
        "Reference lines ONLY by their exact tag as shown above — never by "
        "line number alone. If a line you need to reference isn't tagged "
        "exactly as shown, your operation will be rejected. Keep the exact "
        "same variable name for anything you are not intentionally "
        "changing."
    )


class LineNumberOp(BaseModel):
    kind: str = Field(description='One of "insert", "delete", "replace", "block_replace".')
    line: Optional[str] = Field(default=None, description="Line number (as shown in the numbered view), for delete/replace ops.")
    after: Optional[str] = Field(default=None, description='Line number to insert after, or "start", for insert ops.')
    start_line: Optional[str] = Field(default=None, description="First line number of the range, for block_replace.")
    end_line: Optional[str] = Field(default=None, description="Last line number of the range, for block_replace.")
    content: Optional[str] = Field(default=None, description="New content, for insert/replace/block_replace.")
    expected_content: Optional[str] = Field(
        default=None,
        description=(
            "Optional, for delete/replace ops only: the exact current text of "
            "the referenced line. If given and it doesn't match, the edit is "
            "rejected instead of silently editing the wrong line."
        ),
    )


class PydslLineNumberOutput(BaseModel):
    ops: list[LineNumberOp] = Field(description="Line-number operations to apply in order.")


async def _generate_line_number_ops(prompt: str, model: str, enable_cache: bool = False) -> list[dict]:
    """Single direct LLM call requesting line_number ops (line_number
    mode's generation step) — mirrors _generate_hashline_ops's shape,
    including the pydsl API reference as a system message."""
    llm = get_chat_model(model, enable_cache=enable_cache)
    structured = llm.with_structured_output(PydslLineNumberOutput, include_raw=False)
    messages = [
        make_system_message(build_python_full_instructions(), enable_cache=enable_cache, model_id=model),
        HumanMessage(content=prompt),
    ]
    response = await structured.ainvoke(messages)
    return [op.model_dump() for op in response.ops]


def build_line_number_request_prompt(request: str, line_number_view: str, manifest: dict) -> str:
    """Prompt for line_number mode's single LLM call: shows the numbered
    (annotated) script view instead of the plain script, and asks for
    structured line-anchored operations instead of a diff, search/replace
    blocks, or hash-tagged operations."""
    manifest_json = json.dumps(manifest, indent=2)
    return (
        f"{request}\n\n---\nPrevious script (each line numbered):\n"
        f"```\n{line_number_view}\n```\n\n"
        f"Entity manifest:\n{manifest_json}\n---\n"
        "Respond with a list of operations, each one of:\n"
        '- {"kind": "insert", "after": "<line number or \'start\'>", "content": "<new line>"}\n'
        '- {"kind": "delete", "line": "<line number>", "expected_content": "<optional: exact current text of that line>"}\n'
        '- {"kind": "replace", "line": "<line number>", "content": "<new line>", "expected_content": "<optional: exact current text of that line>"}\n'
        '- {"kind": "block_replace", "start_line": "<line number>", "end_line": "<line number>", "content": "<new lines>"}\n'
        "Reference lines ONLY by the exact number shown in the numbered "
        "view above — never guess or recount. Including expected_content "
        "on delete/replace ops is optional but recommended: if it doesn't "
        "match the line's real current text, your operation will be "
        "rejected instead of silently editing the wrong line. Keep the "
        "exact same variable name for anything you are not intentionally "
        "changing."
    )


class PydslScriptOutput(BaseModel):
    script: str = Field(description="A Python script using only the provided pydsl API.")


_CODE_FENCE_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def _extract_script_from_raw_text(text: "str | None") -> "str | None":
    """Salvage a usable script from a model's raw message text when
    with_structured_output failed to parse it as JSON — some models don't
    honor the structured-output/tool-calling contract and just write plain or
    markdown-fenced code instead. Prefers the contents of a ```python fenced
    block if present (stripping any surrounding prose); otherwise falls back
    to the raw text itself. Returns None if there's nothing usable at all."""
    if not text or not text.strip():
        return None
    match = _CODE_FENCE_RE.search(text)
    if match:
        fenced = match.group(1).strip()
        return fenced or None
    return text.strip()


def _unescape_literal_newlines(script: "str | None") -> "str | None":
    """Some models (observed: nvidia.nemotron-super-3-120b via Bedrock Mantle)
    intermittently emit every line break in their script field as a literal
    two-character "\\n" sequence instead of an actual newline, collapsing the
    whole script onto one line that fails to parse with "unexpected character
    after line continuation character". Verified against a corpus of 485 such
    failures from a 2026-08-06 curriculum run: 434/485 (89.5%) become valid,
    compilable Python after this exact substitution; the rest were separately
    truncated outputs (cut off mid-statement) that this doesn't and shouldn't
    touch. Gated on "zero real newlines AND at least one literal \\n" so this
    is a no-op on any already-well-formed script."""
    if script is None:
        return None
    if "\n" not in script and "\\n" in script:
        return script.replace("\\n", "\n")
    return script


_JSON_SCRIPT_ENVELOPE_RE = re.compile(r'\{\s*"script"\s*:\s*"')


_JSON_ESCAPE_MAP = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "/": "/"}


def _manually_unescape_json_string_body(body: str) -> str:
    """Undo JSON string escapes (\\n, \\", \\uXXXX, ...) by hand, without
    requiring the surrounding text to be valid JSON — used when a mangled
    envelope's json.loads has already failed (see
    _manually_extract_json_script_value below). A codecs "unicode_escape"
    round-trip would also mangle any real non-ASCII byte in the text (e.g.
    the em-dashes/smart quotes these models routinely emit), so this walks
    the string and only recognizes actual two-character JSON escapes."""
    out: list[str] = []
    i, n = 0, len(body)
    while i < n:
        c = body[i]
        if c == "\\" and i + 1 < n:
            nxt = body[i + 1]
            if nxt in _JSON_ESCAPE_MAP:
                out.append(_JSON_ESCAPE_MAP[nxt])
                i += 2
                continue
            if nxt == "u" and i + 6 <= n:
                try:
                    out.append(chr(int(body[i + 2 : i + 6], 16)))
                    i += 6
                    continue
                except ValueError:
                    pass
        out.append(c)
        i += 1
    return "".join(out)


def _manually_extract_json_script_value(text: str, match: "re.Match") -> "str | None":
    """Fallback for a JSON tool-envelope whose json.loads fails — observed
    (2026-08-09, gpt-oss-20b curriculum-eval failures) when generation
    stops mid-envelope (the "script" string's closing quote/brace never
    arrives) or trailing junk survives after it. The string VALUE itself is
    routinely still complete, well-escaped JSON-string content even though
    the wrapper around it is broken. Manually unescapes everything from
    right after the "script": " marker to the last quote/brace/comma/
    whitespace residue at the end of the text — never used unless the
    caller has already confirmed the result parses as Python."""
    body = text[match.end() :]
    body = re.sub(r'[\s"\'}\],]*$', "", body)
    unescaped = _manually_unescape_json_string_body(body)
    return unescaped if unescaped.strip() else None


def _unwrap_json_script_envelope(text: "str | None") -> "str | None":
    """Some models (observed: mantle:openai.gpt-oss-20b, ~80% of its curriculum-
    eval failures) emit their tool-call argument as a literal {"script": "..."}
    JSON envelope — often prefixed with junk like "# Set{" and/or wrapped in a
    ```python fence — instead of raw Python. Verified against a corpus of such
    failures (2026-08-07): the extracted "script" is a complete, runnable
    script once unwrapped. Finds the {"script": "..." pattern anywhere in the
    text, parses from there to the last '}' as JSON, and returns the inner
    script string. Returns the input unchanged if no such envelope is found or
    it doesn't parse as valid JSON — this must never make a good script worse."""
    if text is None:
        return None
    match = _JSON_SCRIPT_ENVELOPE_RE.search(text)
    if not match:
        return text
    candidate = text[match.start():]
    end = candidate.rfind("}")
    if end != -1:
        try:
            obj = json.loads(candidate[: end + 1])
        except json.JSONDecodeError:
            obj = None
        if obj is not None:
            script = obj.get("script")
            if isinstance(script, str) and script.strip():
                return script
    manual = _manually_extract_json_script_value(text, match)
    return manual if manual is not None else text


def _strip_whole_script_triple_quote_wrapper(script: "str | None") -> "str | None":
    """Some models (observed: gpt-oss-20b) wrap their entire script in a
    triple-quoted string, as if it were a module docstring rather than
    executable code — the sandbox then just evaluates one big string
    literal (a no-op — "Diagram has 0 definitions") instead of running any
    real statement, sometimes with leftover junk (a stray '}') after the
    closing quotes. If the script starts with a triple quote and the SAME
    triple-quote token reappears later, unwrap to whatever is between the
    first occurrence and the LAST (dropping any trailing residue after
    it) — but only if that inner body itself parses as Python."""
    if script is None:
        return None
    try:
        ast.parse(script)
        return script
    except SyntaxError:
        pass
    stripped = script.lstrip()
    for q in ('"""', "'''"):
        if not stripped.startswith(q):
            continue
        rest = stripped[len(q):]
        end = rest.rfind(q)
        if end == -1:
            continue
        body = rest[:end]
        try:
            ast.parse(body)
        except SyntaxError:
            continue
        return body
    return script


_BARE_FENCE_LANGUAGE_TAG_RE = re.compile(r"^(python|py)$", re.IGNORECASE)


def _strip_leading_junk_line(script: "str | None") -> "str | None":
    """Some models (observed: gpt-oss-20b) prefix their script with a single
    junk line before the real code starts — a bare markdown-fence language
    tag with no backticks ("python"), a filename, or a stray title line
    ("Full Geometry Script", "*** Begin Script ***"). Confirmed via real
    eval failures: removing exactly that one line recovers a script that
    otherwise parses cleanly. Keeps the fix only if it makes the WHOLE
    script parse; a genuine syntax error deeper in real code is untouched,
    and a script that's ALREADY just one broken line (nothing to recover)
    is left alone rather than reduced to an empty string.

    A bare "python"/"py" first line is stripped unconditionally (not gated
    on a SyntaxError): it parses as a harmless expression-statement
    (a name reference), so the general syntax-error-gated path below never
    even sees it as broken — the sandbox instead fails at runtime with
    "the variable `python` is not defined" (confirmed via real eval
    failures). It's never legitimate pydsl code either way, so dropping it
    is always safe."""
    if script is None:
        return None
    lines = script.splitlines(keepends=True)
    if lines and _BARE_FENCE_LANGUAGE_TAG_RE.match(lines[0].strip()):
        candidate = "".join(lines[1:])
        if candidate.strip():
            script = candidate
            lines = script.splitlines(keepends=True)
    try:
        ast.parse(script)
        return script
    except SyntaxError:
        pass
    if len(lines) < 2:
        return script
    candidate = "".join(lines[1:])
    try:
        ast.parse(candidate)
    except SyntaxError:
        return script
    return candidate


_TRAILING_JUNK_LINE_RE = re.compile(r'^([\s"\'}\],]+|```\w*)$')
_MAX_TRAILING_RESIDUE_LINES = 3


def _strip_trailing_envelope_residue(script: "str | None") -> "str | None":
    """Some models (observed: gpt-oss-20b) leave a stray junk-only line at
    the very end of an otherwise-complete, correct script: either a lone
    '}', '"', or '"}' left over from a JSON tool-envelope that survived
    every earlier unwrap attempt (e.g. because the envelope's OWN closing
    brace was duplicated inside the script's real content, so
    _unwrap_json_script_envelope's rfind('}') picked the wrong one and
    left one behind), or a bare closing ``` markdown fence with no matching
    opening fence left in the script (the opening fence line having
    already been stripped by an earlier fixup, or never having survived
    generation at all). Tries stripping up to a few trailing lines that
    match one of those two shapes, keeping the result only the moment the
    WHOLE script parses — real code never ends in a line built entirely
    from quote/brace/comma/whitespace characters (or a bare code-fence
    marker) with nothing else, so this can't mistake a genuine multi-line
    statement's closing line for residue and truncate real logic."""
    if script is None:
        return None
    try:
        ast.parse(script)
        return script
    except SyntaxError:
        pass
    lines = script.splitlines()
    for _ in range(_MAX_TRAILING_RESIDUE_LINES):
        if not lines or not _TRAILING_JUNK_LINE_RE.match(lines[-1]):
            break
        lines.pop()
        candidate = "\n".join(lines)
        try:
            ast.parse(candidate)
        except SyntaxError:
            continue
        return candidate
    return script


def _fix_trailing_stray_indentation(script: "str | None") -> "str | None":
    """Some models (observed: openai:gpt-5.6-luna, openrouter:kwaipilot/
    kat-coder-air-v2.5 — the identical signature in two unrelated models,
    pointing at a shared upstream formatting quirk rather than two
    independent mistakes) emit an otherwise-correct script where every line
    from some point onward — always observed as exactly the trailing
    draw()/draw_points() block — carries one stray leading space, while
    everything before it sits at column 0. A blanket textwrap.dedent() does
    nothing here (there's no common indent across the WHOLE script), and
    unconditionally stripping all leading whitespace would corrupt any
    script with a real indented block (e.g. inside a for loop).

    Instead: parse once; if that raises IndentationError, use its own
    reported line number to find exactly where the stray block starts,
    confirm every remaining line from there to EOF shares one uniform
    non-empty leading-whitespace prefix, strip only that exact prefix from
    only those lines, and re-parse. Keep the fix only if it makes the WHOLE
    script parse; otherwise return the script unchanged and let the real
    error surface normally."""
    if script is None:
        return None
    try:
        ast.parse(script)
        return script
    except IndentationError as exc:
        lineno = exc.lineno
    except SyntaxError:
        return script
    if lineno is None:
        return script

    lines = script.splitlines(keepends=True)
    start = lineno - 1
    if not (0 <= start < len(lines)):
        return script

    def _leading_ws(line: str) -> "str | None":
        stripped = line.lstrip(" ")
        content = stripped.strip()
        if not content or content.startswith("#"):
            # Blank or comment-only lines: Python's parser doesn't care about
            # their indentation at all, so they must not count as breaking
            # the uniform-prefix match — a model can (and does) leave
            # comments at column 0 while its real statements carry the
            # stray indent.
            return None
        return line[: len(line) - len(stripped)]

    prefix = _leading_ws(lines[start])
    if not prefix:
        return script
    for line in lines[start:]:
        ws = _leading_ws(line)
        if ws is not None and ws != prefix:
            return script

    fixed_lines = [
        line[len(prefix):] if (i >= start and _leading_ws(line) == prefix) else line
        for i, line in enumerate(lines)
    ]
    fixed_script = "".join(fixed_lines)
    try:
        ast.parse(fixed_script)
    except SyntaxError:
        return script
    return fixed_script


def _clean_script(script: "str | None") -> "str | None":
    """Apply all known script-salvage fixups, in order: unwrap a JSON
    envelope first (its own JSON string-escaping already normalizes any
    embedded \\n sequences), then catch any literal \\n that survives, then
    unwrap a whole-script triple-quote wrapper, strip a single leading junk
    line, fix a trailing stray-indentation block, then strip any trailing
    envelope-residue line. Each step is a no-op unless its own specific
    failure signature is present, so a script broken by only one of these
    is unaffected by the others; a script broken by more than one is fixed
    left-to-right without needing every fixup to independently rediscover
    the whole script from scratch."""
    script = _unwrap_json_script_envelope(script)
    script = _unescape_literal_newlines(script)
    script = _strip_whole_script_triple_quote_wrapper(script)
    script = _strip_leading_junk_line(script)
    script = _fix_trailing_stray_indentation(script)
    script = _strip_trailing_envelope_residue(script)
    return script


@dataclass
class PythonFullAttemptTrace:
    attempt: int
    script: "str | None"
    error: "str | None"
    stage: str  # "generation" | "sandbox" | "nothing_drawn" | "ir_pipeline" | "success"


@dataclass
class PythonFullMetadata:
    attempt_traces: list[PythonFullAttemptTrace] = field(default_factory=list)


class PythonFullPipelineState(TypedDict):
    prompt: str
    model_id: str
    enable_cache: bool
    attempt: int
    last_error: str
    script: Optional[str]
    result: Optional[StructuredRunResult]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    renderer: Optional[Any]
    metadata: PythonFullMetadata


async def _generate_script_node(state: PythonFullPipelineState) -> dict:
    """Call the LLM to generate a pydsl script from the prompt."""
    model_id = state["model_id"]
    enable_cache = state.get("enable_cache", False)
    attempt = state["attempt"]
    last_error = state.get("last_error", "")
    metadata = state["metadata"]

    prompt = state["prompt"]
    if attempt > 0 and last_error:
        prompt = f"{prompt}\n\nPrevious attempt failed: {last_error}\nPlease produce a corrected script."

    from langchain_core.messages import HumanMessage
    messages = [
        make_system_message(build_python_full_instructions(), enable_cache=enable_cache, model_id=model_id),
        HumanMessage(content=prompt),
    ]

    try:
        llm = get_chat_model(model_id, enable_cache=enable_cache)

        if requires_raw_text_generation(model_id):
            # This provider rejects both with_structured_output methods this
            # pipeline supports (see llm.py's _RAW_TEXT_ONLY_MODELS) — skip
            # structured output entirely and salvage from plain text, the
            # ONLY viable path here, not a fallback used only on parse failure.
            raw_msg = await llm.ainvoke(messages)
            in_tok, out_tok = extract_usage(raw_msg)
            cost = extract_cost(raw_msg)
            cost_usd = state["cost_usd"] + (cost or 0.0)
            raw_content = raw_msg.content if isinstance(raw_msg.content, str) else None
            salvaged = _clean_script(_extract_script_from_raw_text(raw_content))
            if salvaged is not None:
                metadata.attempt_traces.append(PythonFullAttemptTrace(
                    attempt=attempt + 1, script=salvaged, error=None, stage="generation",
                ))
                return {
                    "script": salvaged,
                    "last_error": "",
                    "input_tokens": state["input_tokens"] + in_tok,
                    "output_tokens": state["output_tokens"] + out_tok,
                    "cost_usd": cost_usd,
                }
            error_text = "No usable script in raw-text response"
            metadata.attempt_traces.append(PythonFullAttemptTrace(
                attempt=attempt + 1, script=None, error=error_text, stage="generation",
            ))
            return {
                "script": None,
                "last_error": error_text,
                "attempt": attempt + 1,
                "input_tokens": state["input_tokens"] + in_tok,
                "output_tokens": state["output_tokens"] + out_tok,
                "cost_usd": cost_usd,
            }

        if is_gemini_model(model_id):
            structured = llm.with_structured_output(PydslScriptOutput, method="json_mode", include_raw=True)
        elif requires_forced_function_calling(model_id):
            # Only for models confirmed to need it (see llm.py's
            # _FORCED_FUNCTION_CALLING_MODELS) — do NOT force this by default
            # for every model. Forcing it universally regressed
            # mantle-oa:google.gemma-4-31b from 84% to 57% pass rate
            # (2026-08-07): auto-detection is what most models, including
            # gemma, actually need; qwen3.7-flash is the confirmed exception.
            structured = llm.with_structured_output(
                PydslScriptOutput, method="function_calling", include_raw=True
            )
        else:
            structured = llm.with_structured_output(PydslScriptOutput, include_raw=True)

        response = await structured.ainvoke(messages)
        raw_msg = response.get("raw")
        parsed = response.get("parsed")
        in_tok, out_tok = extract_usage(raw_msg) if raw_msg else (0, 0)
        cost = extract_cost(raw_msg) if raw_msg else None
        cost_usd = state["cost_usd"] + (cost or 0.0)

        if parsed is None:
            # Some models don't honor the structured-output/tool-calling contract and
            # just write plain or markdown-fenced code instead of JSON — salvage that
            # rather than treating it as an unrecoverable parse failure.
            raw_content = getattr(raw_msg, "content", None) if raw_msg else None
            if not isinstance(raw_content, str):
                raw_content = None
            salvaged = _clean_script(_extract_script_from_raw_text(raw_content))
            if salvaged is not None:
                metadata.attempt_traces.append(PythonFullAttemptTrace(
                    attempt=attempt + 1, script=salvaged, error=None, stage="generation",
                ))
                return {
                    "script": salvaged,
                    "last_error": "",
                    "input_tokens": state["input_tokens"] + in_tok,
                    "output_tokens": state["output_tokens"] + out_tok,
                    "cost_usd": cost_usd,
                }

            parsing_error = response.get("parsing_error") or "Failed to parse script output"
            metadata.attempt_traces.append(PythonFullAttemptTrace(
                attempt=attempt + 1, script=None, error=str(parsing_error), stage="generation",
            ))
            return {
                "script": None,
                "last_error": str(parsing_error),
                "attempt": attempt + 1,
                "input_tokens": state["input_tokens"] + in_tok,
                "output_tokens": state["output_tokens"] + out_tok,
                "cost_usd": cost_usd,
            }

        fixed_script = _clean_script(parsed.script)
        metadata.attempt_traces.append(PythonFullAttemptTrace(
            attempt=attempt + 1, script=fixed_script, error=None, stage="generation",
        ))
        return {
            "script": fixed_script,
            "last_error": "",
            "input_tokens": state["input_tokens"] + in_tok,
            "output_tokens": state["output_tokens"] + out_tok,
            "cost_usd": cost_usd,
        }
    except Exception as exc:
        # For some models, with_structured_output doesn't gracefully return
        # parsed=None on a JSON-parse failure (the `if parsed is None` branch
        # above) — it raises a pydantic ValidationError directly instead. That
        # error's errors()[0]["input"] carries the full, untruncated raw text
        # that failed to parse as JSON (unlike str(exc), which pydantic
        # truncates for display) — salvage from it the same way.
        salvaged = None
        if isinstance(exc, ValidationError):
            for err in exc.errors():
                candidate = err.get("input")
                if isinstance(candidate, str):
                    salvaged = _clean_script(_extract_script_from_raw_text(candidate))
                    if salvaged is not None:
                        break
        if salvaged is not None:
            metadata.attempt_traces.append(PythonFullAttemptTrace(
                attempt=attempt + 1, script=salvaged, error=None, stage="generation",
            ))
            return {"script": salvaged, "last_error": ""}

        logger.warning(f"_generate_script_node attempt {attempt} failed: {exc}")
        metadata.attempt_traces.append(PythonFullAttemptTrace(
            attempt=attempt + 1, script=None, error=str(exc), stage="generation",
        ))
        return {
            "script": None,
            "last_error": str(exc),
            "attempt": attempt + 1,
        }


async def _run_script_node(state: PythonFullPipelineState) -> dict:
    """Run the sandboxed script, then the deterministic compile/check/render pipeline."""
    script = state["script"]
    renderer = state.get("renderer")
    metadata = state.get("metadata")

    if script is None:
        # _generate_script_node already incremented attempt on failure — don't double-count,
        # and don't touch the trace it already appended for this attempt.
        return {"last_error": "No script available to run"}

    result = await asyncio.to_thread(run_script, script, timeout_seconds=SANDBOX_TIMEOUT_SECONDS)

    if result.error is not None:
        # retry_message is None for ExecutionTimeoutError (sandbox.py's timeout branch never
        # sets it) — fall back to result.error so last_error is never empty on that path.
        error_text = result.retry_message or result.error
        if metadata is not None:
            metadata.attempt_traces[-1].stage = "sandbox"
            metadata.attempt_traces[-1].error = error_text
        return {
            "last_error": error_text,
            "attempt": state["attempt"] + 1,
            "result": None,
        }

    diagram_ir = result.diagram_ir
    if not diagram_ir.render:
        error_text = (
            f"Diagram has {len(diagram_ir.define)} definitions but nothing was "
            "drawn — call draw()/draw_points() on what should be visible before finishing."
        )
        if metadata is not None:
            metadata.attempt_traces[-1].stage = "nothing_drawn"
            metadata.attempt_traces[-1].error = error_text
        return {
            "last_error": error_text,
            "attempt": state["attempt"] + 1,
            "result": None,
        }

    try:
        pipeline_result = await run_ir_pipeline(diagram_ir, renderer)
        pipeline_result.retries = state["attempt"]
        # Strip leading/trailing blank lines from the STORED script (not the
        # executed one — a leading blank line is harmless to run). Left in,
        # a leading blank line is ambiguous once embedded in a later edit
        # prompt's markdown fence: it visually blends into the fence's own
        # line break, and the model consistently loses count of "line 1"
        # being blank — confirmed via live testing, where every single
        # patch-mode attempt against such a script failed identically at
        # line 1. Normalizing here gives every future prompt/patch an
        # unambiguous line 1.
        pipeline_result.script = script.strip("\n") + "\n"
        pipeline_result.variable_ids = result.variable_ids
        pipeline_result.entity_manifest = build_entity_manifest(
            diagram_ir, pipeline_result.sym_full, result.variable_ids,
        )
        if metadata is not None:
            metadata.attempt_traces[-1].stage = "success"
        return {"result": pipeline_result}
    except (IRCompileError, RuntimeError) as e:
        if metadata is not None:
            metadata.attempt_traces[-1].stage = "ir_pipeline"
            metadata.attempt_traces[-1].error = str(e)
        return {
            "last_error": str(e),
            "attempt": state["attempt"] + 1,
            "result": None,
        }


async def _run_from_script(script: str, renderer: "Renderer | None") -> StructuredRunResult:
    """Run the sandbox/compile/check/render pipeline directly on an
    already-final script (patch mode's output after apply_script_patch),
    skipping generate_script entirely. A failure here is NOT retried with
    a fresh LLM call, unlike full_rewrite mode — the caller sees the
    error and the state stack is left untouched (Global Constraints)."""
    state: PythonFullPipelineState = {
        "prompt": "", "model_id": "", "enable_cache": False,
        "attempt": 0, "last_error": "", "script": script, "result": None,
        "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
        "renderer": renderer,
        "metadata": PythonFullMetadata(attempt_traces=[
            PythonFullAttemptTrace(attempt=0, script=script, error=None, stage="generation"),
        ]),
    }
    update = await _run_script_node(state)
    result = update.get("result")
    if result is None:
        raise RuntimeError(f"patch-mode script failed: {update.get('last_error', 'unknown error')}")
    return result


def _pipeline_router(state: PythonFullPipelineState) -> str:
    if state.get("result") is not None:
        return END
    if state["attempt"] < MAX_RETRIES:
        return "generate_script"
    return END


def _build_python_full_graph() -> StateGraph:
    builder = StateGraph(PythonFullPipelineState)
    builder.add_node("generate_script", _generate_script_node)
    builder.add_node("run_script", _run_script_node)
    builder.add_edge(START, "generate_script")
    builder.add_edge("generate_script", "run_script")
    builder.add_conditional_edges("run_script", _pipeline_router)
    return builder.compile()


def build_edit_prompt(request: str, previous_script: str, manifest: dict) -> str:
    """Compose an edit-turn prompt: the user's request, the previous
    script verbatim, and its entity manifest, plus the naming contract
    that makes the locality diagnostic (edit_diagnostics.py) meaningful.
    Mirrors structured.py's _prepare_modification_prompt, adapted for a
    pydsl script rather than a raw DiagramIR."""
    manifest_json = json.dumps(manifest, indent=2)
    return (
        f"{request}\n\n"
        "---\n"
        "The user previously had this pydsl script rendered successfully. "
        "Treat it as the starting point and apply only the requested "
        "changes. For any variable you are NOT intentionally changing, "
        "keep the exact same variable name it already has — this is how "
        "we tell which entities you meant to touch.\n\n"
        f"Previous script:\n```python\n{previous_script}\n```\n\n"
        "Entity manifest (script variable -> type and approximate canvas "
        "position, plus unnamed labels/marks/fills by type/position/text):\n"
        f"{manifest_json}\n"
        "---"
    )


class PythonFullStrategy(SubstanceStrategy):
    """pydsl-based strategy: LLM writes a sandboxed Python script, compiled + rendered deterministically."""

    _partial_python_full_metadata: "PythonFullMetadata | None" = None
    _partial_input_tokens: int = 0
    _partial_output_tokens: int = 0
    _partial_cost_usd: "float | None" = None

    async def run(
        self,
        prompt: str,
        model: str = DEFAULT_AGENT_MODEL,
        renderer: Renderer | None = None,
    ) -> StructuredRunResult:
        graph = _build_python_full_graph()
        initial_state: PythonFullPipelineState = {
            "prompt": prompt,
            "model_id": model,
            "enable_cache": self.enable_cache,
            "attempt": 0,
            "last_error": "",
            "script": None,
            "result": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "renderer": renderer,
            "metadata": PythonFullMetadata(),
        }
        final_state = await graph.ainvoke(initial_state, config=self._run_config)

        # Expose partial metadata for the eval harness, before the possible raise below.
        self._partial_python_full_metadata = final_state.get("metadata")
        self._partial_input_tokens = final_state.get("input_tokens", 0)
        self._partial_output_tokens = final_state.get("output_tokens", 0)
        # cost_usd stays None (not 0.0) when the provider never reported cost
        # (e.g. Bedrock) — 0.0 accumulated tokens-side would misleadingly read
        # as "confirmed free" rather than "unknown."
        self._partial_cost_usd = final_state.get("cost_usd") or None

        if final_state.get("result") is None:
            raise RuntimeError(
                f"PythonFullStrategy failed after {MAX_RETRIES} attempts. "
                f"Last error: {final_state.get('last_error', 'unknown')}"
            )
        result = final_state["result"]
        result.python_full_metadata = final_state.get("metadata")
        result.input_tokens = final_state.get("input_tokens", 0)
        result.output_tokens = final_state.get("output_tokens", 0)
        result.cost_usd = self._partial_cost_usd
        return result

    def build_agent(
        self,
        model: str = DEFAULT_AGENT_MODEL,
        renderer=None,
        edit_generation_mode: str = "search_replace",
        hash_algorithm: str = "blake2s",
        retry_on_apply_failure: bool = False,
    ):
        """Conversational ReAct agent with render_diagram + query_diagram
        tools. State is a small stack of prior turns (not a single slot,
        and not per-conversation — see design doc, Component 5, and this
        plan's Global Constraints) kept in this closure.

        edit_generation_mode defaults to "search_replace" — per a
        cross-model eval comparison (2026-08-12) it won or tied for best
        on every model tested. "patch"/"hashline"/"line_number" remain
        fully functional for comparison but are no longer recommended for
        new usage; "full_rewrite" is a separate, always-works baseline."""
        _renderer = renderer if renderer is not None else SVGRenderer()
        _stack: list[dict] = []
        # Mutable box (not a plain variable) so it survives an apply-step
        # exception without needing `nonlocal` rebinding at the point of
        # failure: _edit_line_number writes into it before calling
        # apply_line_number_ops, so a failed apply still leaves the
        # attempted ops' metadata readable via closure introspection (see
        # evals/run_edit_chains.py's _closure_last_edit_ops_meta) — unlike
        # _stack, which a failed turn never appends to at all.
        _last_edit_ops_meta: dict = {"value": None}

        @tool
        async def render_diagram(request: str) -> str:
            """Create or edit the geometry diagram from a natural language
            description. The first call creates a new diagram; later calls
            edit the most recently rendered one.

            Args:
                request: Full description of the diagram or the requested edit.
            Returns:
                JSON with svg field on success, or error field on failure.
            """
            try:
                _last_edit_ops_meta["value"] = None
                if _stack:
                    top = _stack[-1]

                    async def _edit_full_rewrite(req: str) -> StructuredRunResult:
                        full_request = build_edit_prompt(req, top["script"], top["manifest"])
                        return await self.run(full_request, model=model, renderer=_renderer)

                    async def _edit_patch(req: str) -> StructuredRunResult:
                        patch_prompt = build_patch_request_prompt(req, top["script"], top["manifest"])
                        patch_text = await _generate_patch(patch_prompt, model)
                        patched_script = apply_script_patch(top["script"], patch_text)
                        return await _run_from_script(patched_script, _renderer)

                    async def _edit_search_replace(req: str) -> StructuredRunResult:
                        prompt = build_search_replace_request_prompt(req, top["script"], top["manifest"])
                        blocks = await generate_search_replace(prompt, model)
                        new_script = apply_search_replace(top["script"], blocks)
                        return await _run_from_script(new_script, _renderer)

                    async def _edit_hashline(req: str) -> StructuredRunResult:
                        hashline_view = render_hashline_view(top["script"], hash_algorithm)
                        prompt = build_hashline_request_prompt(req, hashline_view, top["manifest"])
                        ops = await _generate_hashline_ops(prompt, model)
                        new_script = apply_hashline_ops(top["script"], ops, hash_algorithm)
                        return await _run_from_script(new_script, _renderer)

                    async def _edit_line_number(req: str) -> StructuredRunResult:
                        view = render_line_number_view(top["script"])
                        prompt = build_line_number_request_prompt(req, view, top["manifest"])
                        ops = await _generate_line_number_ops(prompt, model)
                        delete_replace_ops = [op for op in ops if op.get("kind") in ("delete", "replace")]
                        # Written before apply_line_number_ops runs, so a
                        # failed apply still leaves this readable (see
                        # _last_edit_ops_meta's declaration above).
                        _last_edit_ops_meta["value"] = {
                            "delete_replace_ops": len(delete_replace_ops),
                            "with_expected_content": sum(
                                1 for op in delete_replace_ops if op.get("expected_content")
                            ),
                        }
                        new_script = apply_line_number_ops(top["script"], ops)
                        return await _run_from_script(new_script, _renderer)

                    _edit_handlers = {
                        "patch": _edit_patch,
                        "search_replace": _edit_search_replace,
                        "hashline": _edit_hashline,
                        "line_number": _edit_line_number,
                    }
                    handler = _edit_handlers.get(edit_generation_mode, _edit_full_rewrite)
                    try:
                        result = await handler(request)
                    except ValueError as e:
                        # Opt-in, off by default (Global Constraints) — only
                        # fires on the apply step's own error (a stale tag,
                        # a not-found/ambiguous search_replace block, or
                        # apply_script_patch's context mismatch), never a
                        # generation/API/sandbox error, and only once.
                        if not retry_on_apply_failure or edit_generation_mode == "full_rewrite":
                            raise
                        retry_request = (
                            f"{request}\n\n---\nYour previous attempt at this edit "
                            f"failed: {e}\nPlease produce a corrected edit that fixes "
                            "exactly this problem.\n---"
                        )
                        result = await handler(retry_request)

                    try:
                        locality_diagnostic = check_edit_locality(
                            top["manifest"], top["result"].diagram_ir, top["result"].sym_full,
                            result.entity_manifest, result.diagram_ir, result.sym_full,
                        )  # diagnostic only, per Global Constraints — never gates the turn
                    except Exception:
                        locality_diagnostic = None
                else:
                    result = await self.run(request, model=model, renderer=_renderer)
                    locality_diagnostic = None

                _stack.append({
                    "script": result.script,
                    "manifest": result.entity_manifest,
                    "result": result,
                    "locality_diagnostic": locality_diagnostic,
                    "edit_ops_meta": _last_edit_ops_meta["value"],
                })
                return json.dumps({"svg": result.svg})
            except Exception as e:
                return json.dumps({"error": str(e)})

        @tool
        def query_diagram(query_type: str, params: "dict[str, Any] | None" = None) -> str:
            """Query geometric properties of the most recently rendered diagram.

            Args:
                query_type: One of "list_objects", "coordinate", "distance",
                    "angle", "length", "radius", "area", "perimeter".
                params: Query arguments — call list_objects first to see valid IDs.
            Returns:
                JSON with query result or error.
            """
            if not _stack:
                return json.dumps({"error": "No diagram rendered yet"})
            return dispatch_query(_stack[-1]["result"].sym_full, query_type, params or {})

        llm = get_chat_model(model)
        return create_react_agent(llm, tools=[render_diagram, query_diagram], prompt=_BUILD_AGENT_INSTRUCTIONS)
