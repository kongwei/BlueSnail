const workflowList = document.getElementById("workflowList");
const workflowForm = document.getElementById("workflowForm");
const workflowId = document.getElementById("workflowId");
const workflowName = document.getElementById("workflowName");
const workflowDescription = document.getElementById("workflowDescription");
const workflowEntry = document.getElementById("workflowEntry");
const workflowMaxIterations = document.getElementById("workflowMaxIterations");
const workflowPreview = document.getElementById("workflowPreview");
const workflowSteps = document.getElementById("workflowSteps");
const workflowJson = document.getElementById("workflowJson");
const addWorkflowStepBtn = document.getElementById("addWorkflowStepBtn");
const addWorkflowBtn = document.getElementById("addWorkflowBtn");
const resetWorkflowBtn = document.getElementById("resetWorkflowBtn");
const saveWorkflowBtn = document.getElementById("saveWorkflowBtn");
const activateWorkflowBtn = document.getElementById("activateWorkflowBtn");
const deleteWorkflowBtn = document.getElementById("deleteWorkflowBtn");
const activeWorkflowHint = document.getElementById("activeWorkflowHint");

let workflowBundle = null;
let workflowCatalog = { step_types: [] };
let editingId = null;
let syncingWorkflowJson = false;

init();

async function init() {
  await loadWorkflow();
  workflowForm.addEventListener("submit", (event) => event.preventDefault());
  addWorkflowStepBtn.addEventListener("click", addWorkflowStep);
  addWorkflowBtn.addEventListener("click", addWorkflow);
  resetWorkflowBtn.addEventListener("click", resetWorkflow);
  saveWorkflowBtn.addEventListener("click", saveWorkflow);
  activateWorkflowBtn.addEventListener("click", activateEditingWorkflow);
  deleteWorkflowBtn.addEventListener("click", deleteEditingWorkflow);
  workflowJson.addEventListener("change", applyWorkflowJson);
  workflowId.addEventListener("input", syncEditingWorkflowFromForm);
  workflowName.addEventListener("input", syncEditingWorkflowFromForm);
  workflowDescription.addEventListener("input", syncEditingWorkflowFromForm);
  workflowEntry.addEventListener("input", syncEditingWorkflowFromForm);
  workflowMaxIterations.addEventListener("input", syncEditingWorkflowFromForm);
}

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

async function loadWorkflow() {
  try {
    const [bundleRes, catalogRes] = await Promise.all([
      fetch("/api/workflow"),
      fetch("/api/workflow/catalog"),
    ]);
    const bundle = await bundleRes.json();
    const catalog = await catalogRes.json();
    if (!bundleRes.ok) {
      throw new Error(formatApiError(bundle.detail, "加载流程失败"));
    }
    workflowCatalog = catalog;
    applyWorkflowBundle(bundle);
  } catch (error) {
    showToast(`加载流程编排失败：${error.message}`, true);
  }
}

function applyWorkflowBundle(bundle, preferredId = null) {
  workflowBundle = bundle;
  editingId = preferredId || editingId || bundle.active_id;
  if (!getEditingWorkflow()) {
    editingId = bundle.active_id || bundle.workflows?.[0]?.id;
  }
  renderWorkflowLibrary();
  renderEditingWorkflow();
}

function getEditingWorkflow() {
  return workflowBundle?.workflows?.find((item) => item.id === editingId) || null;
}

function getActiveWorkflow() {
  return (
    workflowBundle?.workflows?.find((item) => item.id === workflowBundle.active_id) ||
    null
  );
}

function renderWorkflowLibrary() {
  workflowList.innerHTML = "";
  const active = getActiveWorkflow();
  activeWorkflowHint.textContent = active
    ? `当前对话流程：${active.name}（${active.id}）`
    : "当前对话流程：未设置";

  for (const item of workflowBundle?.workflows || []) {
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = `workflow-library-item${item.id === editingId ? " active" : ""}`;
    button.innerHTML = `
      <strong>${escapeHtml(item.name || item.id)}</strong>
      <span>ID: ${escapeHtml(item.id)}</span>
      ${item.id === workflowBundle.active_id ? '<em>对话中使用</em>' : ""}
    `;
    button.addEventListener("click", () => {
      syncEditingWorkflowFromForm();
      editingId = item.id;
      renderWorkflowLibrary();
      renderEditingWorkflow();
    });
    li.appendChild(button);
    workflowList.appendChild(li);
  }
}

function renderEditingWorkflow() {
  const workflow = getEditingWorkflow();
  if (!workflow) {
    return;
  }
  workflowId.value = workflow.id || "";
  workflowName.value = workflow.name || "";
  workflowDescription.value = workflow.description || "";
  workflowEntry.value = workflow.entry || "";
  workflowMaxIterations.value = workflow.max_iterations || 50;
  renderWorkflowSteps(workflow);
  renderWorkflowPreview(workflow);
  writeWorkflowJson();
}

function renderWorkflowSteps(workflow) {
  workflowSteps.innerHTML = "";
  const types = workflowCatalog.step_types || [];
  (workflow.steps || []).forEach((step, index) => {
    const card = document.createElement("div");
    card.className = "workflow-step";
    const typeOptions = types
      .map(
        (item) =>
          `<option value="${escapeHtml(item.type)}"${
            item.type === step.type ? " selected" : ""
          }>${escapeHtml(item.label || item.type)}</option>`
      )
      .join("");
    card.innerHTML = `
      <div class="workflow-step-head">
        <span class="workflow-step-title">步骤 ${index + 1}</span>
        <div class="workflow-step-actions">
          <button class="btn secondary" type="button" data-action="up">上移</button>
          <button class="btn secondary" type="button" data-action="down">下移</button>
          <button class="btn secondary" type="button" data-action="remove">删除</button>
        </div>
      </div>
      <label class="field">
        <span>ID</span>
        <input data-field="id" type="text" value="${escapeHtml(step.id || "")}" />
      </label>
      <label class="field">
        <span>类型</span>
        <select data-field="type">${typeOptions}</select>
      </label>
      <label class="field">
        <span>默认下一步</span>
        <input data-field="next" type="text" value="${escapeHtml(step.next || "")}" />
      </label>
      <label class="field">
        <span>启用</span>
        <select data-field="enabled">
          <option value="true"${step.enabled !== false ? " selected" : ""}>是</option>
          <option value="false"${step.enabled === false ? " selected" : ""}>否</option>
        </select>
      </label>
      ${renderStepExtraFields(step)}
    `;
    card.querySelectorAll("[data-field]").forEach((input) => {
      input.addEventListener("change", () => updateStepFromCard(index, card));
      input.addEventListener("input", () => updateStepFromCard(index, card));
    });
    card.querySelector('[data-action="up"]').addEventListener("click", () => moveWorkflowStep(index, -1));
    card.querySelector('[data-action="down"]').addEventListener("click", () => moveWorkflowStep(index, 1));
    card.querySelector('[data-action="remove"]').addEventListener("click", () => removeWorkflowStep(index));
    workflowSteps.appendChild(card);
  });
}

function renderStepExtraFields(step) {
  if (step.type === "recall_memory") {
    return `
      <label class="field">
        <span>top_k</span>
        <input data-param="top_k" type="number" min="1" value="${escapeHtml(
          String(step.params?.top_k ?? 3)
        )}" />
      </label>`;
  }
  if (step.type === "inject_text") {
    return `
      <label class="field">
        <span>注入文本</span>
        <textarea data-param="text" rows="2">${escapeHtml(step.params?.text || "")}</textarea>
      </label>`;
  }
  if (step.type === "llm") {
    const on = step.on || {};
    return `
      <label class="field">
        <span>允许工具</span>
        <select data-param="use_tools">
          <option value="true"${step.params?.use_tools !== false ? " selected" : ""}>是</option>
          <option value="false"${step.params?.use_tools === false ? " selected" : ""}>否</option>
        </select>
      </label>
      <label class="field"><span>tool_calls →</span><input data-on="tool_calls" type="text" value="${escapeHtml(on.tool_calls || "")}" /></label>
      <label class="field"><span>content →</span><input data-on="content" type="text" value="${escapeHtml(on.content || "")}" /></label>
      <label class="field"><span>empty →</span><input data-on="empty" type="text" value="${escapeHtml(on.empty || "")}" /></label>
      <label class="field"><span>error →</span><input data-on="error" type="text" value="${escapeHtml(on.error || "")}" /></label>
      <label class="field"><span>max_iterations →</span><input data-on="max_iterations" type="text" value="${escapeHtml(on.max_iterations || "")}" /></label>
    `;
  }
  return "";
}

function updateStepFromCard(index, card) {
  const workflow = getEditingWorkflow();
  if (!workflow) {
    return;
  }
  const step = {
    ...(workflow.steps[index] || {}),
    params: { ...(workflow.steps[index]?.params || {}) },
    on: { ...(workflow.steps[index]?.on || {}) },
  };
  const typeChanged = card.querySelector('[data-field="type"]').value !== workflow.steps[index].type;
  card.querySelectorAll("[data-field]").forEach((input) => {
    const field = input.dataset.field;
    if (field === "enabled") {
      step.enabled = input.value === "true";
    } else {
      step[field] = input.value.trim();
    }
  });
  card.querySelectorAll("[data-param]").forEach((input) => {
    const key = input.dataset.param;
    if (key === "top_k") {
      step.params.top_k = Number(input.value) || 3;
    } else if (key === "use_tools") {
      step.params.use_tools = input.value === "true";
    } else {
      step.params[key] = input.value;
    }
  });
  card.querySelectorAll("[data-on]").forEach((input) => {
    const key = input.dataset.on;
    if (input.value.trim()) {
      step.on[key] = input.value.trim();
    } else {
      delete step.on[key];
    }
  });
  if (!step.next) {
    delete step.next;
  }
  if (!Object.keys(step.params).length) {
    delete step.params;
  }
  if (!Object.keys(step.on).length) {
    delete step.on;
  }
  workflow.steps[index] = step;
  if (typeChanged) {
    renderEditingWorkflow();
    return;
  }
  renderWorkflowPreview(workflow);
  writeWorkflowJson();
}

function moveWorkflowStep(index, delta) {
  const workflow = getEditingWorkflow();
  const next = index + delta;
  if (!workflow || next < 0 || next >= workflow.steps.length) {
    return;
  }
  const [step] = workflow.steps.splice(index, 1);
  workflow.steps.splice(next, 0, step);
  renderEditingWorkflow();
}

function removeWorkflowStep(index) {
  const workflow = getEditingWorkflow();
  if (!workflow || workflow.steps.length <= 1) {
    showToast("至少保留一个步骤", true);
    return;
  }
  workflow.steps.splice(index, 1);
  renderEditingWorkflow();
}

function addWorkflowStep() {
  const workflow = getEditingWorkflow();
  if (!workflow) {
    return;
  }
  const id = `step_${workflow.steps.length + 1}`;
  workflow.steps.push({
    id,
    type: "inject_text",
    next: "finish",
    enabled: true,
    params: { text: "" },
  });
  renderEditingWorkflow();
}

function addWorkflow() {
  if (!workflowBundle) {
    return;
  }
  const id = `flow_${Date.now().toString(36)}`;
  workflowBundle.workflows.push({
    id,
    name: `自定义流程 ${workflowBundle.workflows.length + 1}`,
    description: "用户自定义 Agent 流程",
    entry: "ingest",
    max_iterations: 20,
    steps: [
      { id: "ingest", type: "ingest_user", next: "think" },
      {
        id: "think",
        type: "llm",
        params: { use_tools: true },
        on: {
          tool_calls: "act",
          content: "finish",
          empty: "finish",
          error: "finish",
          max_iterations: "finish",
        },
      },
      { id: "act", type: "execute_calls", next: "think" },
      { id: "finish", type: "finish" },
    ],
  });
  editingId = id;
  renderWorkflowLibrary();
  renderEditingWorkflow();
}

function syncEditingWorkflowFromForm() {
  const workflow = getEditingWorkflow();
  if (!workflow) {
    return;
  }
  const nextId = workflowId.value.trim() || workflow.id;
  if (workflowBundle.active_id === workflow.id) {
    workflowBundle.active_id = nextId;
  }
  workflow.id = nextId;
  workflow.name = workflowName.value.trim() || workflow.id;
  workflow.description = workflowDescription.value.trim();
  workflow.entry = workflowEntry.value.trim();
  workflow.max_iterations = Number(workflowMaxIterations.value) || 50;
  editingId = workflow.id;
  renderWorkflowPreview(workflow);
  renderWorkflowLibrary();
  writeWorkflowJson();
}

function renderWorkflowPreview(workflow) {
  const parts = (workflow.steps || []).map((step) => {
    const routes = [];
    if (step.next) {
      routes.push(`→ ${step.next}`);
    }
    for (const [key, value] of Object.entries(step.on || {})) {
      routes.push(`${key}→${value}`);
    }
    return `${step.id}[${step.type}] ${routes.join(" ")}`.trim();
  });
  workflowPreview.textContent = parts.join("  ·  ");
}

function writeWorkflowJson() {
  const workflow = getEditingWorkflow();
  if (!workflow) {
    return;
  }
  syncingWorkflowJson = true;
  workflowJson.value = JSON.stringify(workflow, null, 2);
  syncingWorkflowJson = false;
}

function applyWorkflowJson() {
  if (syncingWorkflowJson) {
    return;
  }
  try {
    const parsed = JSON.parse(workflowJson.value);
    if (!parsed?.id || !parsed?.steps) {
      throw new Error("JSON 需包含 id 和 steps");
    }
    const index = workflowBundle.workflows.findIndex((item) => item.id === editingId);
    if (index < 0) {
      throw new Error("当前编辑的流程不存在");
    }
    if (workflowBundle.active_id === editingId) {
      workflowBundle.active_id = parsed.id;
    }
    workflowBundle.workflows[index] = parsed;
    editingId = parsed.id;
    renderWorkflowLibrary();
    renderEditingWorkflow();
  } catch (error) {
    showToast(`流程 JSON 无效：${error.message}`, true);
  }
}

async function saveWorkflow() {
  syncEditingWorkflowFromForm();
  try {
    const response = await fetch("/api/workflow", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        active_id: workflowBundle.active_id,
        workflows: workflowBundle.workflows,
      }),
    });
    const data = await parseJsonResponse(response);
    if (!response.ok) {
      throw new Error(formatApiError(data.detail, "保存流程失败"));
    }
    applyWorkflowBundle(data, editingId);
    showToast("流程库已保存");
    return true;
  } catch (error) {
    showToast(error.message, true);
    return false;
  }
}

async function activateEditingWorkflow() {
  syncEditingWorkflowFromForm();
  const workflow = getEditingWorkflow();
  if (!workflow) {
    return;
  }
  const saved = await saveWorkflow();
  if (!saved) {
    return;
  }
  try {
    const response = await fetch("/api/workflow/active", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ref: workflow.id }),
    });
    const data = await parseJsonResponse(response);
    if (!response.ok) {
      throw new Error(formatApiError(data.detail, "切换流程失败"));
    }
    workflowBundle.active_id = data.id;
    renderWorkflowLibrary();
    showToast(`对话将使用流程：${data.name}（${data.id}）`);
  } catch (error) {
    showToast(error.message, true);
  }
}

async function deleteEditingWorkflow() {
  if (!workflowBundle || workflowBundle.workflows.length <= 1) {
    showToast("至少保留一个流程", true);
    return;
  }
  const workflow = getEditingWorkflow();
  if (!workflow) {
    return;
  }
  workflowBundle.workflows = workflowBundle.workflows.filter((item) => item.id !== workflow.id);
  if (workflowBundle.active_id === workflow.id) {
    workflowBundle.active_id = workflowBundle.workflows[0].id;
  }
  editingId = workflowBundle.workflows[0].id;
  renderWorkflowLibrary();
  renderEditingWorkflow();
}

async function resetWorkflow() {
  try {
    const response = await fetch("/api/workflow/reset", { method: "POST" });
    const data = await parseJsonResponse(response);
    if (!response.ok) {
      throw new Error(formatApiError(data.detail, "恢复默认流程失败"));
    }
    applyWorkflowBundle(data, data.active_id);
    showToast("已恢复默认流程");
  } catch (error) {
    showToast(error.message, true);
  }
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
