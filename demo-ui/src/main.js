// ---------------------------------------------------------------------------
// Markdown + MathJax rendering
// ---------------------------------------------------------------------------
import { marked } from "marked";
import DOMPurify from "dompurify";

// Protect math expressions from markdown processing by replacing them with
// unique placeholders before parsing, then restoring them afterwards.
function renderMarkdown(text) {
  const mathBlocks = [];

  // Replacement helper — stores the match and returns a placeholder.
  const protect = (match) => {
    const id = mathBlocks.length;
    mathBlocks.push(match);
    return `\x02MATH${id}\x03`;
  };

  // Order matters: display math before inline to avoid partial matches.
  let safe = text
    .replace(/\$\$[\s\S]*?\$\$/g, protect)        // $$...$$
    .replace(/\\\[[\s\S]*?\\\]/g, protect)          // \[...\]
    .replace(/\$[^$\n]+?\$/g, protect)              // $...$
    .replace(/\\\([\s\S]*?\\\)/g, protect);         // \(...\)

  // Parse markdown.
  let html = marked.parse(safe, { breaks: true });

  // Restore math expressions.
  html = html.replace(/\x02MATH(\d+)\x03/g, (_, i) => mathBlocks[Number(i)]);

  return DOMPurify.sanitize(html);
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
  let renderCallId = null;

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
              assistantBubble.innerHTML = "";
              started = true;
            }
            break;

          case "TEXT_MESSAGE_CONTENT":
            if (evt.messageId === assistantMsgId) {
              assistantText += evt.delta;
              assistantBubble.innerHTML = renderMarkdown(assistantText);
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
              // Typeset math now that the full message is available.
              if (window.MathJax?.typesetPromise) {
                MathJax.typesetPromise([assistantBubble]).catch(console.error);
              }
            }
            break;

          case "TOOL_CALL_START":
            if (evt.toolCallName === "render_diagram") {
              renderCallId = evt.toolCallId;
            }
            break;

          case "TOOL_CALL_RESULT":
            if (evt.toolCallId === renderCallId) {
              renderCallId = null;
              try {
                const data = JSON.parse(evt.content);
                if (data.svg) {
                  document.getElementById("penrose").innerHTML = data.svg;
                }
              } catch (e) {
                console.error("Failed to parse render result:", e);
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
