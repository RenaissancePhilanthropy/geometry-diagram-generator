import { compile, optimize, showError, toSVG } from "@penrose/core";
import style from "../geometry.style?raw";
import domain from "../geometry.domain?raw";

// ---------------------------------------------------------------------------
// Penrose diagram rendering
// ---------------------------------------------------------------------------

async function renderSubstance(substance) {
  console.log("Rendering substance:", substance);
  const compiled = await compile({
    substance,
    style,
    domain,
    variation: "penrose",
  });
  if (compiled.isErr()) {
    console.error(showError(compiled.error));
    addBubble("error", "Diagram error: " + showError(compiled.error));
    return;
  }
  const optimized = optimize(compiled.value);
  if (optimized.isErr()) {
    console.error(showError(optimized.error));
    addBubble("error", "Layout error: " + showError(optimized.error));
    return;
  }
  const penroseEl = document.getElementById("penrose");
  penroseEl.innerHTML = "";
  penroseEl.appendChild(await toSVG(optimized.value));
}

// ---------------------------------------------------------------------------
// Chat UI
// ---------------------------------------------------------------------------

const chat = document.getElementById("chat");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send-btn");

const threadId = crypto.randomUUID();
const history = []; // { id, role, content }

function addBubble(role, text = "") {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.textContent = text;
  chat.appendChild(el);
  el.scrollIntoView({ block: "end" });
  return el;
}

async function send() {
  const text = input.value.trim();
  if (!text) return;

  input.value = "";
  input.style.height = "";
  sendBtn.disabled = true;

  const userMsgId = crypto.randomUUID();
  history.push({ id: userMsgId, role: "user", content: text });
  addBubble("user", text);

  const assistantBubble = addBubble("assistant thinking", "…");
  let assistantMsgId = null;
  let assistantText = "";
  let started = false;

  // Tool call tracking for render_diagram
  let inRenderCall = false;
  let toolCallArgs = "";

  try {
    const res = await fetch("/api/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        threadId,
        runId: crypto.randomUUID(),
        state: {},
        messages: history,
        tools: [],
        context: [],
        forwardedProps: {},
      }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop();

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (!raw) continue;

        let evt;
        try {
          evt = JSON.parse(raw);
        } catch {
          continue;
        }

        switch (evt.type) {
          case "TEXT_MESSAGE_START":
            assistantMsgId = evt.messageId;
            assistantText = "";
            if (!started) {
              assistantBubble.classList.remove("thinking");
              assistantBubble.textContent = "";
              started = true;
            }
            break;

          case "TEXT_MESSAGE_CONTENT":
            if (evt.messageId === assistantMsgId) {
              assistantText += evt.delta;
              assistantBubble.textContent = assistantText;
              assistantBubble.scrollIntoView({ block: "end" });
            }
            break;

          case "TEXT_MESSAGE_END":
            if (assistantMsgId) {
              history.push({
                id: assistantMsgId,
                role: "assistant",
                content: assistantText,
              });
              assistantMsgId = null;
            }
            break;

          case "TOOL_CALL_START":
            if (evt.toolCallName === "render_diagram") {
              inRenderCall = true;
              toolCallArgs = "";
            }
            break;

          case "TOOL_CALL_ARGS":
            if (inRenderCall) toolCallArgs += evt.delta;
            break;

          case "TOOL_CALL_END":
            if (inRenderCall) {
              inRenderCall = false;
              try {
                const { substance } = JSON.parse(toolCallArgs);
                await renderSubstance(substance);
              } catch (e) {
                console.error(
                  "Failed to parse render_diagram args",
                  e,
                  toolCallArgs,
                );
              }
            }
            break;

          case "RUN_ERROR":
            assistantBubble.remove();
            addBubble("error", `Error: ${evt.message}`);
            break;
        }
      }
    }

    if (!started) assistantBubble.remove();
  } catch (err) {
    assistantBubble.remove();
    addBubble("error", `Failed to reach agent: ${err.message}`);
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
}

sendBtn.addEventListener("click", send);

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 128) + "px";
});
