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
const appEl = document.querySelector(".app");
const toggleSidebarBtn = document.getElementById("toggleSidebarBtn");
const sidebarBackdrop = document.getElementById("sidebarBackdrop");

const sessionId = `web-${Date.now()}`;
let loading = false;
let reasoningTraces = [];
let activeReasoningId = null;

async function parseJsonResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch (_error) {
    return { detail: text || response.statusText || "请求失败" };
  }
}

function formatApiError(detail, fallback = "请求失败") {
  if (!detail) {
    return fallback;
  }
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }
        if (item && typeof item === "object") {
          return item.msg || item.message || JSON.stringify(item);
        }
        return String(item);
      })
      .join("; ");
  }
  if (typeof detail === "object" && detail.message) {
    return String(detail.message);
  }
  return String(detail);
}

init();

async function init() {
  renderEmptyState();
  await Promise.all([loadTools(), loadSkills(), loadHistory(), loadLlmConfig()]);
  llmPanelToggle.addEventListener("click", toggleLlmPanel);
  llmConfigForm.addEventListener("submit", saveLlmConfig);
  testLlmBtn.addEventListener("click", testLlmConfig);
  toggleReasoningBtn.addEventListener("click", () => setReasoningPanelVisible(true));
  closeReasoningBtn.addEventListener("click", () => setReasoningPanelVisible(false));
  toggleSidebarBtn.addEventListener("click", () => setSidebarOpen(true));
  sidebarBackdrop.addEventListener("click", () => setSidebarOpen(false));
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
  setSidebarOpen(false);
  setLoading(true);

  try {
    await consumeChatStream(text);
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
  const isError = data.stopped_reason === "llm_error";
  appendMessage(
    {
      role: "assistant",
      content: data.answer,
      metadata: isError ? { is_error: true } : {},
    },
    traceId
  );

  const chatStepState = new Map();
  for (const step of data.steps || []) {
    appendStepMessagesToChat(step, traceId, chatStepState);
  }
}

async function consumeChatStream(text) {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: text,
      session_id: sessionId,
    }),
  });

  if (!response.ok) {
    const data = await parseJsonResponse(response);
    throw new Error(formatApiError(data.detail, "请求失败"));
  }

  const traceId = beginReasoningStream(text);
  setReasoningPanelVisible(true);
  const chatStepState = new Map();

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalData = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    buffer = processSSEBuffer(buffer, (eventType, data) => {
      if (eventType === "start") {
        updateReasoningRunContext(traceId, data.run_context || {});
      } else if (eventType === "step") {
        handleStreamStep(data, traceId, chatStepState);
      } else if (eventType === "done") {
        finalData = data;
        finalizeReasoningStream(traceId, data);
      } else if (eventType === "error") {
        throw new Error(formatApiError(data.detail, "Agent 运行失败"));
      }
    });
  }

  if (!finalData) {
    throw new Error("Agent 运行未完成");
  }

  if (finalData.stopped_reason === "llm_error") {
    statusText.textContent = "LLM 出错";
  }
  metaInfo.textContent = `迭代 ${finalData.iterations} 次 · 停止原因 ${finalData.stopped_reason}`;
}

function processSSEBuffer(buffer, onEvent) {
  const parts = buffer.split("\n\n");
  const remaining = parts.pop() || "";
  for (const part of parts) {
    if (!part.trim()) {
      continue;
    }
    let eventType = "message";
    let dataLine = "";
    for (const line of part.split("\n")) {
      if (line.startsWith("event:")) {
        eventType = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLine = line.slice(5).trim();
      }
    }
    if (!dataLine) {
      continue;
    }
    onEvent(eventType, JSON.parse(dataLine));
  }
  return remaining;
}

function beginReasoningStream(userInput) {
  const trace = {
    id: `trace-${Date.now()}-${reasoningTraces.length + 1}`,
    userInput,
    createdAt: new Date().toLocaleTimeString(),
    reasoning: {
      run_context: {},
      steps: [],
      stopped_reason: "-",
      iterations: 0,
    },
  };
  reasoningTraces.push(trace);
  activeReasoningId = trace.id;
  renderReasoningHistory();
  renderReasoningStreamShell(trace);
  return trace.id;
}

function handleStreamStep(step, traceId, chatStepState) {
  appendReasoningStepLive(step, traceId);
  appendStepMessagesToChat(step, traceId, chatStepState);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function appendStepMessagesToChat(step, traceId, chatStepState) {
  const state = chatStepState.get(step.iteration) || {
    assistant: false,
    results: false,
  };

  const hasAssistantPayload = step.content || step.tool_calls?.length;
  if (hasAssistantPayload && !state.assistant) {
    if (step.finish_reason === "stop" || step.finish_reason === "error") {
      appendMessage(
        {
          role: "assistant",
          content: step.content,
          metadata: {
            is_error: step.finish_reason === "error",
            ...(step.tool_calls?.length
              ? { tool_calls: step.tool_calls }
              : {}),
          },
        },
        traceId
      );
    } else if (step.tool_calls?.length) {
      appendMessage(
        {
          role: "assistant",
          content: step.content || "",
          metadata: { tool_calls: step.tool_calls },
        },
        traceId
      );
    }
    state.assistant = true;
  }

  const hasResults =
    step.skill_results?.length || step.tool_results?.length;
  if (hasResults && !state.results) {
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
    state.results = true;
  }

  chatStepState.set(step.iteration, state);
}

function finalizeReasoningStream(traceId, data) {
  const trace = reasoningTraces.find((item) => item.id === traceId);
  if (trace) {
    trace.reasoning = data.reasoning || trace.reasoning;
  }
  updateReasoningOverview(traceId, data);
}

function updateReasoningRunContext(traceId, runContext) {
  const trace = reasoningTraces.find((item) => item.id === traceId);
  if (!trace) {
    return;
  }
  trace.reasoning.run_context = runContext;
  const recallEl = document.getElementById("reasoningRecallContext");
  const systemEl = document.getElementById("reasoningSystemPrompt");
  if (recallEl) {
    recallEl.textContent = runContext.recall_context || "";
    recallEl.closest(".reasoning-meta-item").classList.toggle(
      "hidden",
      !runContext.recall_context
    );
  }
  if (systemEl) {
    systemEl.textContent = runContext.system_prompt || "";
    systemEl.closest(".reasoning-meta-item").classList.toggle(
      "hidden",
      !runContext.system_prompt
    );
  }
}

function updateReasoningOverview(traceId, data) {
  const trace = reasoningTraces.find((item) => item.id === traceId);
  if (trace && data.reasoning) {
    trace.reasoning.stopped_reason = data.stopped_reason;
    trace.reasoning.iterations = data.iterations;
  }
  const stoppedEl = document.getElementById("reasoningStoppedReason");
  const iterationsEl = document.getElementById("reasoningIterations");
  if (stoppedEl) {
    stoppedEl.textContent = data.stopped_reason || "-";
  }
  if (iterationsEl) {
    iterationsEl.textContent = String(data.iterations ?? 0);
  }
}

function renderReasoningStreamShell(trace) {
  const reasoning = trace.reasoning || {};
  const runContext = reasoning.run_context || {};

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
          <span id="reasoningStoppedReason">${escapeHtml(reasoning.stopped_reason || "-")}</span>
        </div>
        <div class="reasoning-meta-item">
          <span class="reasoning-meta-label">迭代次数</span>
          <span id="reasoningIterations">${escapeHtml(String(reasoning.iterations || 0))}</span>
        </div>
        <div class="reasoning-meta-item${runContext.recall_context ? "" : " hidden"}">
          <span class="reasoning-meta-label">召回记忆</span>
          <span id="reasoningRecallContext">${escapeHtml(runContext.recall_context || "")}</span>
        </div>
        <div class="reasoning-meta-item${runContext.system_prompt ? "" : " hidden"}">
          <span class="reasoning-meta-label">System Prompt</span>
          <span id="reasoningSystemPrompt">${escapeHtml(runContext.system_prompt || "")}</span>
        </div>
      </div>
    </div>
    <div class="reasoning-block">
      <h3>逐步推理</h3>
      <div id="reasoningStepsLive" class="reasoning-steps-live"></div>
    </div>
  `;
}

function appendReasoningStepLive(step, traceId) {
  const trace = reasoningTraces.find((item) => item.id === traceId);
  let existingIndex = -1;
  if (trace) {
    existingIndex = trace.reasoning.steps.findIndex(
      (item) => item.iteration === step.iteration
    );
    if (existingIndex >= 0) {
      trace.reasoning.steps[existingIndex] = step;
    } else {
      trace.reasoning.steps.push(step);
    }
    trace.reasoning.iterations = trace.reasoning.steps.length;
  }

  if (traceId !== activeReasoningId) {
    return;
  }

  const container = document.getElementById("reasoningStepsLive");
  if (!container) {
    return;
  }

  upsertReasoningStepDom(container, step);
  const iterationsEl = document.getElementById("reasoningIterations");
  if (iterationsEl && trace) {
    iterationsEl.textContent = String(trace.reasoning.steps.length);
  }
  container.lastElementChild?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  reasoningContent.scrollTop = reasoningContent.scrollHeight;
}

function upsertReasoningStepDom(container, step) {
  const existing = container.querySelector(
    `[data-iteration="${step.iteration}"]`
  );
  const html = renderReasoningStep(step);
  if (existing) {
    existing.outerHTML = html;
  } else {
    container.insertAdjacentHTML("beforeend", html);
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

function setSidebarOpen(open) {
  appEl.classList.toggle("sidebar-open", open);
  toggleSidebarBtn.setAttribute("aria-expanded", open ? "true" : "false");
  toggleSidebarBtn.setAttribute("aria-label", open ? "关闭侧边栏" : "打开侧边栏");
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

  renderReasoningStreamShell(trace);
  const container = document.getElementById("reasoningStepsLive");
  for (const step of trace.reasoning?.steps || []) {
    container.insertAdjacentHTML("beforeend", renderReasoningStep(step));
  }
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

  const bodyParts = [];

  if (step.content) {
    bodyParts.push(
      `<div class="reasoning-meta-label">LLM 输出</div>
       <div class="markdown-body reasoning-markdown">${BlueSnailMarkdown.renderMarkdown(step.content)}</div>`
    );
  }

  if (step.tool_calls?.length) {
    bodyParts.push(
      `<div class="reasoning-meta-label">工具调用</div>
       <pre class="reasoning-pre">${escapeHtml(JSON.stringify(step.tool_calls, null, 2))}</pre>`
    );
  }

  if (step.skill_results?.length) {
    bodyParts.push(
      `<div class="reasoning-meta-label">Skill 结果</div>
       <pre class="reasoning-pre">${escapeHtml(JSON.stringify(step.skill_results, null, 2))}</pre>`
    );
  }

  if (step.tool_results?.length) {
    bodyParts.push(
      `<div class="reasoning-meta-label">工具结果</div>
       <pre class="reasoning-pre">${escapeHtml(JSON.stringify(step.tool_results, null, 2))}</pre>`
    );
  }

  if (!bodyParts.length) {
    bodyParts.push('<div class="reasoning-empty">本 Step 无新增输出</div>');
  }

  return `
    <div class="reasoning-step" data-iteration="${step.iteration}">
      <div class="reasoning-step-head">
        <div class="reasoning-step-title">Step ${step.iteration}</div>
        <span class="reasoning-tag ${tagClass}">${escapeHtml(tagText)}</span>
      </div>
      ${bodyParts.join("")}
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
