const messagesEl = document.getElementById("messages");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const clearBtn = document.getElementById("clearBtn");
const toolsList = document.getElementById("toolsList");
const skillsList = document.getElementById("skillsList");
const rememberForm = document.getElementById("rememberForm");
const rememberKey = document.getElementById("rememberKey");
const rememberContent = document.getElementById("rememberContent");
const statusText = document.getElementById("statusText");
const metaInfo = document.getElementById("metaInfo");
const llmMeta = document.getElementById("llmMeta");
const messageTemplate = document.getElementById("messageTemplate");
const llmConfigForm = document.getElementById("llmConfigForm");
const llmPanelToggle = document.getElementById("llmPanelToggle");
const llmPanelBody = document.getElementById("llmPanelBody");
const llmSummary = document.getElementById("llmSummary");
const llmBaseUrl = document.getElementById("llmBaseUrl");
const llmModel = document.getElementById("llmModel");
const llmApiKey = document.getElementById("llmApiKey");
const llmApiKeyHint = document.getElementById("llmApiKeyHint");
const llmTimeout = document.getElementById("llmTimeout");
const llmSystemPrompt = document.getElementById("llmSystemPrompt");
const testLlmBtn = document.getElementById("testLlmBtn");
const toggleReasoningBtn = document.getElementById("toggleReasoningBtn");
const closeReasoningBtn = document.getElementById("closeReasoningBtn");
const reasoningPanel = document.getElementById("reasoningPanel");
const reasoningContent = document.getElementById("reasoningContent");
const reasoningHistory = document.getElementById("reasoningHistory");
const mainArea = document.querySelector(".main-area");

const sessionId = `web-${Date.now()}`;
let loading = false;
let reasoningTraces = [];
let activeReasoningId = null;

init();

async function init() {
  renderEmptyState();
  await Promise.all([loadTools(), loadSkills(), loadHistory(), loadLlmConfig()]);
  llmPanelToggle.addEventListener("click", toggleLlmPanel);
  llmConfigForm.addEventListener("submit", saveLlmConfig);
  testLlmBtn.addEventListener("click", testLlmConfig);
  toggleReasoningBtn.addEventListener("click", () => setReasoningPanelVisible(true));
  closeReasoningBtn.addEventListener("click", () => setReasoningPanelVisible(false));
}

function renderEmptyState() {
  messagesEl.innerHTML = `
    <div class="empty-state">
      <h3>开始与 BlueSnail Agent 对话</h3>
      <p>请先配置 LLM 服务，然后开始对话。支持工具调用，可在推理面板查看完整过程。</p>
    </div>
  `;
}

async function loadLlmConfig() {
  try {
    const response = await fetch("/api/llm/config");
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "加载 LLM 配置失败");
    }
    applyLlmConfigToForm(data);
  } catch (error) {
    showToast(`加载 LLM 配置失败：${error.message}`, true);
  }
}

function applyLlmConfigToForm(config) {
  llmBaseUrl.value = config.base_url || "";
  llmModel.value = config.model || "";
  llmTimeout.value = config.timeout || 60;
  llmSystemPrompt.value = config.system_prompt || "";
  llmApiKey.value = "";

  if (config.api_key_set && config.api_key_hint) {
    llmApiKeyHint.textContent = `已保存 Key：${config.api_key_hint}`;
  } else {
    llmApiKeyHint.textContent = "尚未配置 API Key";
  }

  updateLlmStatus(config);
}

function updateLlmStatus(config) {
  const model = config.model || "未设置模型";
  const keyHint = config.api_key_set ? "已配置 Key" : "未配置 Key";
  llmSummary.textContent = `${model} · ${keyHint}`;
  llmMeta.textContent = config.model ? ` · ${config.model}` : "";
}

function toggleLlmPanel() {
  const expanded = llmPanelToggle.getAttribute("aria-expanded") === "true";
  llmPanelToggle.setAttribute("aria-expanded", expanded ? "false" : "true");
  llmPanelBody.classList.toggle("collapsed", expanded);
}

function collectLlmPayload() {
  const payload = {
    base_url: llmBaseUrl.value.trim(),
    model: llmModel.value.trim(),
    timeout: Number(llmTimeout.value) || 60,
    system_prompt: llmSystemPrompt.value.trim(),
  };
  const apiKey = llmApiKey.value.trim();
  if (apiKey) {
    payload.api_key = apiKey;
  }
  return payload;
}

async function saveLlmConfig(event) {
  event.preventDefault();
  const payload = collectLlmPayload(false);

  try {
    const response = await fetch("/api/llm/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "保存失败");
    }
    applyLlmConfigToForm(data);
    showToast("LLM 配置已保存并应用");
    llmPanelBody.classList.add("collapsed");
    llmPanelToggle.setAttribute("aria-expanded", "false");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function testLlmConfig() {
  const payload = collectLlmPayload(false);
  testLlmBtn.disabled = true;
  testLlmBtn.textContent = "测试中...";

  try {
    const response = await fetch("/api/llm/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "测试失败");
    }
    showToast(`连接成功：${data.reply}`);
  } catch (error) {
    showToast(error.message, true);
  } finally {
    testLlmBtn.disabled = false;
    testLlmBtn.textContent = "测试连接";
  }
}

async function loadSkills() {
  try {
    const response = await fetch("/api/skills");
    const data = await response.json();
    skillsList.innerHTML = "";

    if (!data.skills?.length) {
      skillsList.innerHTML = "<li><span>暂无 Skill</span></li>";
      return;
    }

    for (const skill of data.skills) {
      const item = document.createElement("li");
      item.innerHTML = `
        <strong>${escapeHtml(skill.name)}</strong>
        <span>${escapeHtml(skill.description || "")}</span>
        ${
          skill.skill_dir
            ? `<span>${escapeHtml(skill.skill_dir)}</span>`
            : ""
        }
      `;
      skillsList.appendChild(item);
    }
  } catch (error) {
    showToast(`加载 Skills 失败：${error.message}`, true);
  }
}

async function loadTools() {
  try {
    const response = await fetch("/api/tools");
    const data = await response.json();
    toolsList.innerHTML = "";

    if (!data.tools?.length) {
      toolsList.innerHTML = "<li><span>暂无工具</span></li>";
      return;
    }

    for (const tool of data.tools) {
      const item = document.createElement("li");
      item.innerHTML = `
        <strong>${escapeHtml(tool.name)}</strong>
        <span>${escapeHtml(tool.description || "")}</span>
      `;
      toolsList.appendChild(item);
    }
  } catch (error) {
    showToast(`加载工具失败：${error.message}`, true);
  }
}

async function loadHistory() {
  try {
    const response = await fetch("/api/history");
    const data = await response.json();
    if (data.messages?.length) {
      messagesEl.innerHTML = "";
      for (const message of data.messages) {
        appendMessage(message);
      }
    }
  } catch (error) {
    showToast(`加载历史失败：${error.message}`, true);
  }
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = messageInput.value.trim();
  if (!text || loading) {
    return;
  }

  appendMessage({ role: "user", content: text });
  messageInput.value = "";
  setLoading(true);

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        session_id: sessionId,
      }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "请求失败");
    }

    const traceId = storeReasoningTrace(text, data.reasoning);
    appendAssistantResult(data, traceId);
    metaInfo.textContent = `迭代 ${data.iterations} 次 · 停止原因 ${data.stopped_reason}`;
    statusText.textContent = "就绪";
  } catch (error) {
    statusText.textContent = "出错";
    showToast(error.message, true);
  } finally {
    setLoading(false);
  }
});

clearBtn.addEventListener("click", async () => {
  try {
    await fetch("/api/clear", { method: "POST" });
    renderEmptyState();
    metaInfo.textContent = "";
    statusText.textContent = "对话已清空";
    reasoningTraces = [];
    activeReasoningId = null;
    renderReasoningHistory();
    renderReasoningContent(null);
  } catch (error) {
    showToast(`清空失败：${error.message}`, true);
  }
});

rememberForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const key = rememberKey.value.trim();
  const content = rememberContent.value.trim();
  if (!key || !content) {
    return;
  }

  try {
    const response = await fetch("/api/remember", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, content }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "保存失败");
    }
    rememberKey.value = "";
    rememberContent.value = "";
    showToast(`记忆已保存：${key}`);
  } catch (error) {
    showToast(error.message, true);
  }
});

messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

function appendAssistantResult(data, traceId = null) {
  appendMessage({ role: "assistant", content: data.answer }, traceId);

  for (const step of data.steps || []) {
    for (const result of step.skill_results || []) {
      appendMessage({
        role: "tool",
        name: `skill:${result.name}`,
        content: result.content,
        metadata: { is_error: result.is_error, kind: "skill" },
      });
    }
    for (const result of step.tool_results || []) {
      appendMessage({
        role: "tool",
        name: result.name,
        content: result.content,
        metadata: { is_error: result.is_error },
      });
    }
  }
}

function storeReasoningTrace(userInput, reasoning) {
  if (!reasoning) {
    return null;
  }
  const trace = {
    id: `trace-${Date.now()}-${reasoningTraces.length + 1}`,
    userInput,
    createdAt: new Date().toLocaleTimeString(),
    reasoning,
  };
  reasoningTraces.push(trace);
  activeReasoningId = trace.id;
  renderReasoningHistory();
  renderReasoningContent(trace);
  setReasoningPanelVisible(true);
  return trace.id;
}

function setReasoningPanelVisible(visible) {
  reasoningPanel.classList.toggle("hidden", !visible);
  mainArea.classList.toggle("show-reasoning", visible);
}

function renderReasoningHistory() {
  reasoningHistory.innerHTML = "";
  for (const trace of reasoningTraces) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `reasoning-tab${trace.id === activeReasoningId ? " active" : ""}`;
    button.textContent = truncateText(trace.userInput, 16) || trace.createdAt;
    button.title = trace.userInput;
    button.addEventListener("click", () => {
      activeReasoningId = trace.id;
      renderReasoningHistory();
      renderReasoningContent(trace);
      setReasoningPanelVisible(true);
    });
    reasoningHistory.appendChild(button);
  }
}

function renderReasoningContent(trace) {
  if (!trace) {
    reasoningContent.innerHTML =
      '<div class="reasoning-empty">发送消息后，可在此查看 Agent 的逐步推理过程。</div>';
    return;
  }

  const reasoning = trace.reasoning || {};
  const runContext = reasoning.run_context || {};
  const steps = reasoning.steps || [];

  reasoningContent.innerHTML = `
    <div class="reasoning-block">
      <h3>运行概览</h3>
      <div class="reasoning-meta">
        <div class="reasoning-meta-item">
          <span class="reasoning-meta-label">用户输入</span>
          ${escapeHtml(trace.userInput)}
        </div>
        <div class="reasoning-meta-item">
          <span class="reasoning-meta-label">停止原因</span>
          ${escapeHtml(reasoning.stopped_reason || "-")}
        </div>
        <div class="reasoning-meta-item">
          <span class="reasoning-meta-label">迭代次数</span>
          ${escapeHtml(String(reasoning.iterations || steps.length || 0))}
        </div>
        ${
          runContext.recall_context
            ? `<div class="reasoning-meta-item">
                <span class="reasoning-meta-label">召回记忆</span>
                ${escapeHtml(runContext.recall_context)}
              </div>`
            : ""
        }
        ${
          runContext.system_prompt
            ? `<div class="reasoning-meta-item">
                <span class="reasoning-meta-label">System Prompt</span>
                ${escapeHtml(runContext.system_prompt)}
              </div>`
            : ""
        }
      </div>
    </div>
    <div class="reasoning-block">
      <h3>逐步推理</h3>
      ${steps.length ? steps.map(renderReasoningStep).join("") : '<div class="reasoning-empty">本次回复没有额外推理步骤。</div>'}
    </div>
  `;
}

function renderReasoningStep(step) {
  const tagClass = step.skill_results?.length
    ? "tool"
    : step.tool_calls?.length
    ? "tool"
    : step.finish_reason === "stop"
      ? "done"
      : "";
  const tagText = step.skill_results?.length
    ? "skill"
    : step.tool_calls?.length
    ? "tool_calls"
    : step.finish_reason || "response";

  return `
    <div class="reasoning-step">
      <div class="reasoning-step-head">
        <div class="reasoning-step-title">Step ${step.iteration}</div>
        <span class="reasoning-tag ${tagClass}">${escapeHtml(tagText)}</span>
      </div>

      <div class="reasoning-meta-label">LLM 输入上下文</div>
      ${
        step.input_messages?.length
          ? step.input_messages.map(renderReasoningInputMessage).join("")
          : '<div class="reasoning-empty">无输入消息</div>'
      }

      ${
        step.content
          ? `<div class="reasoning-meta-label">LLM 输出</div>
             <div class="markdown-body reasoning-markdown">${BlueSnailMarkdown.renderMarkdown(step.content)}</div>`
          : ""
      }

      ${
        step.tool_calls?.length
          ? `<div class="reasoning-meta-label">工具调用</div>
             <pre class="reasoning-pre">${escapeHtml(JSON.stringify(step.tool_calls, null, 2))}</pre>`
          : ""
      }

      ${
        step.skill_results?.length
          ? `<div class="reasoning-meta-label">Skill 调用</div>
             <pre class="reasoning-pre">${escapeHtml(JSON.stringify(step.skill_results, null, 2))}</pre>`
          : ""
      }

      ${
        step.tool_results?.length
          ? `<div class="reasoning-meta-label">工具结果</div>
             <pre class="reasoning-pre">${escapeHtml(JSON.stringify(step.tool_results, null, 2))}</pre>`
          : ""
      }
    </div>
  `;
}

function renderReasoningInputMessage(message) {
  return `
    <div class="reasoning-message">
      <div class="reasoning-message-role">${escapeHtml(message.role)}${
        message.name ? ` · ${escapeHtml(message.name)}` : ""
      }</div>
      <div>${escapeHtml(truncateText(message.content, 1200))}</div>
    </div>
  `;
}

function openReasoningTrace(traceId) {
  const trace = reasoningTraces.find((item) => item.id === traceId);
  if (!trace) {
    return;
  }
  activeReasoningId = trace.id;
  renderReasoningHistory();
  renderReasoningContent(trace);
  setReasoningPanelVisible(true);
}

function appendMessage(message, traceId = null) {
  if (messagesEl.querySelector(".empty-state")) {
    messagesEl.innerHTML = "";
  }

  const node = messageTemplate.content.cloneNode(true);
  const article = node.querySelector(".message");
  const roleEl = node.querySelector(".role");
  const contentEl = node.querySelector(".content");
  const detailsEl = node.querySelector(".details");
  const toolDetailEl = node.querySelector(".tool-detail");
  const viewReasoningBtn = node.querySelector(".view-reasoning");

  const role = message.role || "assistant";
  article.classList.add(role);
  roleEl.textContent = roleLabel(role, message.name);
  renderMessageContent(contentEl, message);

  if (traceId && role === "assistant") {
    viewReasoningBtn.classList.remove("hidden");
    viewReasoningBtn.addEventListener("click", () => openReasoningTrace(traceId));
  }

  if (message.metadata?.tool_calls?.length) {
    detailsEl.classList.remove("hidden");
    toolDetailEl.textContent = JSON.stringify(message.metadata.tool_calls, null, 2);
  }

  if (message.metadata?.is_error) {
    contentEl.classList.add("content-error");
  }

  messagesEl.appendChild(node);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function renderMessageContent(contentEl, message) {
  const role = message.role || "assistant";
  const content = message.content || "";
  contentEl.classList.add("markdown-body");

  if (role === "tool") {
    contentEl.innerHTML = BlueSnailMarkdown.renderToolContent(content);
    return;
  }

  if (role === "user") {
    contentEl.innerHTML = BlueSnailMarkdown.renderMarkdown(content);
    return;
  }

  contentEl.innerHTML = BlueSnailMarkdown.renderMarkdown(content);
}

function roleLabel(role, name) {
  if (role === "tool" && name) {
    return `tool · ${name}`;
  }
  return role;
}

function setLoading(isLoading) {
  loading = isLoading;
  sendBtn.disabled = isLoading;
  statusText.textContent = isLoading ? "思考中..." : "就绪";
}

function showToast(text, isError = false) {
  const toast = document.createElement("div");
  toast.className = `toast${isError ? " error" : ""}`;
  toast.textContent = text;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 2800);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function truncateText(value, maxLength) {
  const text = String(value || "").trim();
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength)}...`;
}
