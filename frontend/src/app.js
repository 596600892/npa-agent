import { apiGet, apiPatch, apiPost, fileToBase64 } from "./api.js";

const state = {
  health: null,
  project: null,
  file: null,
  mappingPreview: null,
  fieldMappingConfirmed: false,
  legalDocument: null,
  latestLegalRisk: null,
  executionPlan: null,
  executionBatches: [],
  executionTasks: [],
  historyFile: null,
  historyMappingPreview: null,
  historyRecords: [],
  historyAnalytics: null,
  currentCalibration: null,
  courtProfiles: [],
  selectedMode: "redacted_cloud",
  modelProviders: [],
  voiceProviders: [],
  documentParser: null,
  yindengSubscriptions: [],
  yindengAlerts: [],
  knowledgeNotes: [],
  selectedKnowledgeNote: null,
  privateSkillDrafts: [],
  selectedPrivateSkillDraft: null,
  auditLogs: [],
  auditSummary: null,
  latestReportText: "",
  recognition: null,
};

const $ = (id) => document.getElementById(id);

function toast(message, type = "info") {
  const target = $("uploadStatus");
  target.textContent = message;
  target.dataset.type = type;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function markdownToHtml(markdown) {
  const lines = markdown.split("\n");
  const html = [];
  let tableRows = [];

  function flushTable() {
    if (!tableRows.length) return;
    const rows = tableRows
      .filter((row) => !/^\|\s*-+/.test(row))
      .map((row) => row.split("|").slice(1, -1).map((cell) => cell.trim()));
    if (rows.length) {
      const [head, ...body] = rows;
      html.push("<table>");
      html.push(`<thead><tr>${head.map((cell) => `<th>${escapeHtml(cell)}</th>`).join("")}</tr></thead>`);
      html.push(`<tbody>${body.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")}</tbody>`);
      html.push("</table>");
    }
    tableRows = [];
  }

  for (const line of lines) {
    if (line.startsWith("|")) {
      tableRows.push(line);
      continue;
    }
    flushTable();
    if (line.startsWith("# ")) html.push(`<h1>${escapeHtml(line.slice(2))}</h1>`);
    else if (line.startsWith("## ")) html.push(`<h2>${escapeHtml(line.slice(3))}</h2>`);
    else if (line.startsWith("### ")) html.push(`<h3>${escapeHtml(line.slice(4))}</h3>`);
    else if (line.startsWith("> ")) html.push(`<blockquote>${escapeHtml(line.slice(2))}</blockquote>`);
    else if (line.startsWith("- ")) html.push(`<li>${escapeHtml(line.slice(2))}</li>`);
    else if (/^\d+\. /.test(line)) html.push(`<li>${escapeHtml(line.replace(/^\d+\. /, ""))}</li>`);
    else if (!line.trim()) html.push("");
    else html.push(`<p>${escapeHtml(line)}</p>`);
  }
  flushTable();
  return html.join("\n");
}

function fillSelect(select, items, selectedId) {
  select.innerHTML = "";
  for (const item of items) {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.label;
    option.selected = item.id === selectedId;
    select.appendChild(option);
  }
}

function providerById(items, id) {
  return items.find((item) => item.id === id) || items[0] || {};
}

function money(value) {
  if (value === null || value === undefined) return "未识别";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "未识别";
  if (amount >= 100000000) return `${(amount / 100000000).toFixed(2)} 亿`;
  if (amount >= 10000) return `${(amount / 10000).toFixed(2)} 万`;
  return `${amount.toFixed(0)} 元`;
}

function percent(value) {
  if (value === null || value === undefined) return "样本不足";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "样本不足";
  return `${(amount * 100).toFixed(1)}%`;
}

function compactNumber(value) {
  if (value === null || value === undefined) return "样本不足";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "样本不足";
  return amount.toFixed(1);
}

function riskLabel(value) {
  return { low: "低", medium: "中", high: "高", unknown: "未知", not_analyzed: "未分析" }[value] || value || "未分析";
}

function executionStatusLabel(value) {
  return {
    pending: "待处理",
    contacted: "已接通",
    no_answer: "未接",
    unreachable: "失联",
    willing: "有意愿",
    promise_payment: "承诺还款",
    dispute: "异议",
    switch_to_litigation: "转诉讼评估",
    outsourced: "建议分包",
    closed: "已关闭",
  }[value] || value || "待处理";
}

function knowledgeStatusLabel(value) {
  return { confirmed: "已确认", pending_confirmation: "待确认" }[value] || value || "未知";
}

function privateSkillStatusLabel(value) {
  return { draft: "草稿", needs_revision: "需修改", approved: "已审核", archived: "已归档" }[value] || value || "草稿";
}

function yesNo(value) {
  return value ? "是" : "否";
}

const GUIDE_STEPS = [
  { id: "project", title: "项目", hint: "新建或选择一个资产包项目" },
  { id: "asset", title: "资产包", hint: "上传 Excel，至少要有本金" },
  { id: "mapping", title: "字段确认", hint: "确认系统识别的字段映射" },
  { id: "materials", title: "补充材料", hint: "合同、历史数据和银登信息越多越准" },
  { id: "report", title: "分析报告", hint: "生成初筛报告和报价建议" },
  { id: "execution", title: "执行计划", hint: "生成分批次处置清单" },
  { id: "memory", title: "经验沉淀", hint: "同步知识库，生成私有 Skill 草稿" },
];

function safeText(id, value) {
  const element = $(id);
  if (element) element.textContent = value;
}

function safeHtml(id, value) {
  const element = $(id);
  if (element) element.innerHTML = value;
}

function openExpertDrawer() {
  const drawer = document.querySelector(".expert-drawer");
  if (drawer) drawer.open = true;
  drawer?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function focusControl(id) {
  const element = $(id);
  if (!element) return;
  if (element.closest(".expert-drawer")) openExpertDrawer();
  element.scrollIntoView({ behavior: "smooth", block: "center" });
  if (!element.disabled) element.focus();
}

function clickControl(id, disabledMessage) {
  const element = $(id);
  if (!element) return;
  if (element.closest(".expert-drawer")) openExpertDrawer();
  element.scrollIntoView({ behavior: "smooth", block: "center" });
  if (element.disabled) {
    showGuidanceMessage(disabledMessage || "这个动作现在还不可用，请先完成前面的步骤。", "warn");
    return;
  }
  element.click();
}

function showGuidanceMessage(message, type = "info") {
  safeHtml("guidanceBlockers", `<div class="guide-note" data-type="${escapeHtml(type)}">${escapeHtml(message)}</div>`);
}

function deriveGuidanceState() {
  const hasProject = Boolean(state.project);
  const hasReport = Boolean(hasProject && state.latestReportText);
  const hasAssetFile = Boolean(state.file || hasReport);
  const hasMapping = Boolean(state.mappingPreview || hasReport);
  const hasConfirmedMapping = Boolean(state.fieldMappingConfirmed || hasReport);
  const hasMaterials = Boolean(hasProject && (state.latestLegalRisk || state.historyRecords.length || state.courtProfiles.length));
  const hasExecution = Boolean(hasProject && state.executionPlan);
  const hasMemory = Boolean(hasProject && state.knowledgeNotes.some((note) => note.id === `project_${state.project.id}` || note.scope_id === state.project.id));
  const completed = new Set();
  if (hasProject) completed.add("project");
  if (hasAssetFile) completed.add("asset");
  if (hasConfirmedMapping) completed.add("mapping");
  if (hasMaterials) completed.add("materials");
  if (hasReport) completed.add("report");
  if (hasExecution) completed.add("execution");
  if (hasMemory) completed.add("memory");

  if (!hasProject) {
    return {
      current_step: "project",
      completed_steps: completed,
      title: "先新建一个分析项目",
      badge: "等待开始",
      message: "从一个项目开始即可。系统会在后面自动提示上传资产包、确认字段、补充材料和生成报告。",
      recommended_actions: [{ label: "新建分析项目", run: createProject }],
      blockers: [],
      optional_improvements: ["已经有项目时，也可以直接在左侧历史项目里选择。"],
    };
  }
  if (!hasAssetFile) {
    return {
      current_step: "asset",
      completed_steps: completed,
      title: "上传资产包 Excel",
      badge: "需要资产包",
      message: "请选择资产包 Excel。最少需要本金字段；身份证、手机号、地址越完整，画像和处置判断越准。",
      recommended_actions: [
        { label: "选择 Excel 文件", run: () => focusControl("fileInput") },
        { label: "上传并识别字段", run: () => clickControl("uploadBtn") },
      ],
      blockers: ["还没有上传资产包 Excel。"],
      optional_improvements: ["可以先下载标准模板，也可以直接上传自己的非标准表格。"],
    };
  }
  if (!hasMapping || !hasConfirmedMapping) {
    return {
      current_step: "mapping",
      completed_steps: completed,
      title: hasMapping ? "确认字段映射" : "识别字段映射",
      badge: hasMapping ? "等待确认" : "等待识别",
      message: hasMapping ? "请确认系统识别的字段。低置信度字段可以手动调整，缺可选字段不阻塞分析。" : "文件已选定后，先上传并让系统识别字段。",
      recommended_actions: [{ label: hasMapping ? "确认字段映射" : "上传并识别字段", run: () => clickControl(hasMapping ? "confirmMappingBtn" : "uploadBtn", "请先上传资产包 Excel。") }],
      blockers: hasMapping ? [] : ["还没有字段识别结果。"],
      optional_improvements: ["本金是必需字段；身份证、手机号、地址缺失时，系统会降低相应画像和触达可信度。"],
    };
  }
  if (!hasReport) {
    return {
      current_step: "report",
      completed_steps: completed,
      title: "生成初筛报告",
      badge: "可分析",
      message: hasMaterials ? "基础数据和补充材料已经就绪，可以生成带来源说明的初筛报告。" : "当前数据已经能先分析；合同、历史处置数据和银登公告可后续补充，让结论更准。",
      recommended_actions: [
        { label: "生成初筛报告", run: () => clickControl("runAnalysisBtn", "请先确认字段映射。") },
        { label: "补充合同/历史数据", run: openExpertDrawer },
      ],
      blockers: [],
      optional_improvements: hasMaterials ? ["补充材料已参与当前判断。"] : ["补合同可分析法律风险；上传历史数据可校准法院画像和报价。"],
    };
  }
  if (!hasExecution) {
    return {
      current_step: "execution",
      completed_steps: completed,
      title: "生成处置执行计划",
      badge: "报告已完成",
      message: "报告已经生成。下一步可以把 A/B/C/D 分层落成执行清单，也可以把项目结论沉淀到本地知识库。",
      recommended_actions: [
        { label: "生成执行计划", run: () => clickControl("generateExecutionBtn") },
        { label: "沉淀当前项目", run: () => clickControl("syncKnowledgeBtn") },
        { label: "补充合同或历史数据", run: openExpertDrawer },
      ],
      blockers: [],
      optional_improvements: ["执行计划默认脱敏展示，并支持导出 Excel。"],
    };
  }
  return {
    current_step: "memory",
    completed_steps: completed,
    title: "沉淀经验并复盘",
    badge: "闭环完成",
    message: "资产包分析和执行计划已经形成。可以同步知识库、确认经验，并从已确认记忆生成私有 Skill 草稿。",
    recommended_actions: [
      { label: "沉淀当前项目", run: () => clickControl("syncKnowledgeBtn") },
      { label: "生成私有 Skill 草稿", run: () => clickControl("generatePrivateSkillBtn") },
      { label: "查看执行工作台", run: openExpertDrawer },
    ],
    blockers: [],
    optional_improvements: ["私有 Skill 草稿只进入审核区，本阶段不会自动启用或参与分析。"],
  };
}

function renderGuidance() {
  const guidance = deriveGuidanceState();
  safeText("guidanceTitle", guidance.title);
  safeText("guidanceBadge", guidance.badge);
  safeText("guidanceMessage", guidance.message);
  safeText("guideProgress", `${guidance.completed_steps.size}/${GUIDE_STEPS.length}`);
  const stepIndex = GUIDE_STEPS.findIndex((step) => step.id === guidance.current_step);
  safeHtml(
    "guidanceSteps",
    GUIDE_STEPS.map((step, index) => {
      const status = guidance.completed_steps.has(step.id) ? "done" : index === stepIndex ? "current" : "pending";
      const statusLabel = status === "done" ? "完成" : status === "current" ? "当前" : "待处理";
      return `
        <div class="guide-step" data-status="${status}">
          <span>${index + 1}</span>
          <div>
            <strong>${escapeHtml(step.title)}</strong>
            <small>${escapeHtml(statusLabel)} · ${escapeHtml(step.hint)}</small>
          </div>
        </div>
      `;
    }).join("")
  );
  const actions = $("guidanceActions");
  if (actions) {
    actions.innerHTML = "";
    for (const action of guidance.recommended_actions.slice(0, 3)) {
      const button = document.createElement("button");
      button.className = "primary-button";
      button.textContent = action.label;
      button.onclick = action.run;
      actions.appendChild(button);
    }
  }
  safeHtml("guidanceBlockers", guidance.blockers.map((item) => `<div class="guide-note" data-type="warn">${escapeHtml(item)}</div>`).join(""));
  safeHtml("guidanceOptional", guidance.optional_improvements.map((item) => `<div class="guide-note">${escapeHtml(item)}</div>`).join(""));
  document.querySelectorAll("[data-guide-step]").forEach((element) => {
    element.classList.toggle("is-current", element.dataset.guideStep === guidance.current_step);
  });
}

async function loadProjects() {
  const data = await apiGet("/api/projects");
  const list = $("projectList");
  list.innerHTML = "";
  for (const project of data.projects || []) {
    const button = document.createElement("button");
    button.className = "project-item";
    button.textContent = project.name;
    button.onclick = async () => {
      state.project = project;
      $("currentProjectTitle").textContent = project.name;
      await loadLatestLegalRisk();
      await loadExecutionWorkspace();
      await loadLatestReport();
      await loadKnowledgeNotes();
      renderGuidance();
    };
    list.appendChild(button);
  }
  renderGuidance();
}

async function createProject() {
  const data = await apiPost("/api/projects", { name: `个贷资产包分析 ${new Date().toLocaleString()}`, asset_type: "consumer_loan" });
  if (!data.ok) return alert(data.message);
  state.project = data.project;
  state.file = null;
  state.mappingPreview = null;
  state.fieldMappingConfirmed = false;
  state.currentCalibration = null;
  state.latestReportText = "";
  $("currentProjectTitle").textContent = state.project.name;
  $("uploadStatus").textContent = "项目已创建";
  $("mappingStatus").textContent = "尚未识别";
  $("mappingList").innerHTML = "";
  $("confirmMappingBtn").disabled = true;
  $("analysisStatus").textContent = "等待字段确认";
  $("runAnalysisBtn").disabled = true;
  $("reportStatus").textContent = "尚未生成";
  $("reportView").innerHTML = "<p>报告会显示在这里。敏感字段默认脱敏。</p>";
  renderProjectCalibration(null);
  state.latestLegalRisk = null;
  renderLegalRisk(null);
  $("legalStatus").textContent = "可选上传";
  clearExecutionWorkspace();
  await loadKnowledgeNotes();
  await loadProjects();
  renderGuidance();
}

async function uploadFile() {
  if (!state.project) await createProject();
  const file = $("fileInput").files[0];
  if (!file) return alert("请先选择 .xlsx 文件");
  toast("正在读取文件...");
  const content = await fileToBase64(file);
  const uploaded = await apiPost(`/api/projects/${state.project.id}/files`, {
    filename: file.name,
    file_type: "asset_package_excel",
    content_base64: content,
  });
  if (!uploaded.ok) return alert(uploaded.message);
  state.file = uploaded.file;
  state.fieldMappingConfirmed = false;
  state.latestReportText = "";
  state.currentCalibration = null;
  toast("已上传，正在识别字段...");
  const preview = await apiPost(`/api/projects/${state.project.id}/field-mapping/preview`, { file_id: state.file.id });
  if (!preview.ok) return alert(preview.message);
  state.mappingPreview = preview;
  renderMapping(preview);
  renderGuidance();
}

function renderMapping(preview) {
  $("mappingStatus").textContent = `已识别 ${preview.sheet_name}`;
  const wrap = $("mappingList");
  wrap.innerHTML = "";
  for (const [field, item] of Object.entries(preview.mapping)) {
    const row = document.createElement("div");
    row.className = "mapping-row";
    const options = [`<option value="">不映射</option>`].concat(
      preview.headers.map((header) => `<option value="${escapeHtml(header)}" ${header === item.source_column ? "selected" : ""}>${escapeHtml(header)}</option>`)
    );
    row.innerHTML = `
      <div>
        <strong>${escapeHtml(item.label || field)}</strong>
        <small>置信度 ${(item.confidence * 100).toFixed(0)}% ${item.needs_confirmation ? "需确认" : "自动"}</small>
      </div>
      <select data-field="${escapeHtml(field)}">${options.join("")}</select>
    `;
    wrap.appendChild(row);
  }
  $("confirmMappingBtn").disabled = false;
  renderGuidance();
}

async function confirmMapping() {
  const mapping = {};
  for (const select of document.querySelectorAll("#mappingList select")) {
    mapping[select.dataset.field] = select.value || null;
  }
  const data = await apiPost(`/api/projects/${state.project.id}/field-mapping/confirm`, {
    file_id: state.file.id,
    mapping,
    confidence: state.mappingPreview.mapping,
  });
  if (!data.ok) return alert(data.message);
  $("analysisStatus").textContent = `已标准化 ${data.normalized_count} 户`;
  $("runAnalysisBtn").disabled = false;
  state.fieldMappingConfirmed = true;
  renderGuidance();
}

async function uploadLegalDocument() {
  if (!state.project) await createProject();
  const file = $("legalDocInput").files[0];
  if (!file) return alert("请先选择 PDF、图片、DOCX、TXT 或 HTML 文书");
  $("legalStatus").textContent = "正在解析文书...";
  const content = await fileToBase64(file);
  const uploaded = await apiPost(`/api/projects/${state.project.id}/legal-documents`, {
    filename: file.name,
    content_base64: content,
  });
  if (!uploaded.ok) {
    $("legalStatus").textContent = uploaded.message || "上传失败";
    return;
  }
  state.legalDocument = uploaded.document;
  $("legalStatus").textContent = `${extractionMethodLabel(uploaded.document.extraction_method)} · 文本质量 ${uploaded.document.text_quality}`;
  const analyzed = await apiPost(`/api/projects/${state.project.id}/legal-documents/${uploaded.document.id}/analyze`, {});
  if (!analyzed.ok) {
    $("legalStatus").textContent = analyzed.message || "分析失败";
    return;
  }
  state.latestLegalRisk = analyzed.legal_risk.risk;
  renderLegalRisk(state.latestLegalRisk);
  $("legalStatus").textContent = `风险 ${riskLabel(state.latestLegalRisk.overall_risk)}`;
  renderGuidance();
}

function renderLegalRisk(risk) {
  const wrap = $("legalRiskCards");
  if (!risk) {
    const ocr = state.documentParser?.ocr;
    const ocrText = ocr ? `本地 OCR：${escapeHtml(ocr.status)}` : "正在检测本地 OCR";
    wrap.innerHTML = `<p class="muted-copy">支持 PDF、图片、DOCX、TXT、HTML。PDF 可以是扫描件；${ocrText}。</p>`;
    return;
  }
  const sections = Object.values(risk.risks || {});
  const nextActions = (risk.next_actions || []).slice(0, 3).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const judicial = risk.judicial_analysis;
  const impacts = risk.strategy_impacts;
  const judicialHtml = judicial
    ? `
      <div class="risk-summary secondary">
        <strong>${escapeHtml(documentTypeLabel(risk.document_type))}线索</strong>
        <span>裁判 ${judicial.adjudication_points?.length || 0} · 执行 ${judicial.execution_statuses?.length || 0} · 调解 ${judicial.mediation_terms?.length || 0} · 金额 ${judicial.amounts?.length || 0}</span>
      </div>
    `
    : "";
  const impactHtml = impacts
    ? `
      <div class="risk-summary secondary">
        <strong>策略影响</strong>
        <span>报价 ${escapeHtml(impacts.pricing_direction || "neutral")} · 执行 ${escapeHtml(impacts.execution_route || "未触发专项分流")}</span>
      </div>
    `
    : "";
  wrap.innerHTML = `
    <div class="risk-summary">
      <strong>整体风险：${escapeHtml(riskLabel(risk.overall_risk))}</strong>
      <span>${escapeHtml(documentTypeLabel(risk.document_type))} · 可信度 ${escapeHtml(risk.confidence)} · 文本质量 ${escapeHtml(risk.text_quality)} · ${escapeHtml(risk.filename || "合同/文书")}</span>
      <span>${escapeHtml(extractionMethodLabel(risk.extraction_method))} · OCR ${escapeHtml(risk.ocr_status || "not_needed")} · 页码 ${(risk.pages_used || []).map(escapeHtml).join("、") || "未记录"}</span>
    </div>
    ${judicialHtml}
    ${impactHtml}
    <div class="risk-card-grid">
      ${sections
        .map(
          (item) => `
            <div class="risk-card" data-risk="${escapeHtml(item.risk)}">
              <strong>${escapeHtml(item.label)}</strong>
              <span>${escapeHtml(riskLabel(item.risk))}</span>
              <small>${escapeHtml(item.conclusion)}</small>
            </div>
          `
        )
        .join("")}
    </div>
    <ul class="risk-next">${nextActions}</ul>
  `;
}

function extractionMethodLabel(value) {
  return {
    text: "文本",
    docx_text: "DOCX 文本",
    html_text: "HTML 文本",
    pdf_text: "PDF 文本层",
    pdf_ocr: "PDF OCR",
    image_ocr: "图片 OCR",
    ocr_unavailable: "OCR 不可用",
    unknown: "未知解析方式",
  }[value || "unknown"] || value || "未知解析方式";
}

function documentTypeLabel(value) {
  return {
    contract: "合同/条款",
    judgment: "判决书",
    enforcement: "执行文书",
    mediation: "调解文书",
    unknown: "未识别文书",
  }[value || "unknown"] || value || "未识别文书";
}

async function uploadHistoryFile() {
  const file = $("historyFileInput").files[0];
  if (!file) return alert("请先选择公司历史处置 .xlsx 文件");
  $("historyStatus").textContent = "正在读取历史文件...";
  const content = await fileToBase64(file);
  const uploaded = await apiPost("/api/company-history/files", {
    filename: file.name,
    file_type: "company_history_excel",
    content_base64: content,
  });
  if (!uploaded.ok) return alert(uploaded.message);
  state.historyFile = uploaded.file;
  $("historyStatus").textContent = "已上传，正在识别字段...";
  const preview = await apiPost("/api/company-history/field-mapping/preview", { file_id: state.historyFile.id });
  if (!preview.ok) return alert(preview.message);
  state.historyMappingPreview = preview;
  renderHistoryMapping(preview);
}

function renderHistoryMapping(preview) {
  $("historyStatus").textContent = `已识别 ${preview.sheet_name}`;
  const wrap = $("historyMappingList");
  wrap.innerHTML = "";
  for (const [field, item] of Object.entries(preview.mapping)) {
    const row = document.createElement("div");
    row.className = "mapping-row";
    const options = [`<option value="">不映射</option>`].concat(
      preview.headers.map((header) => `<option value="${escapeHtml(header)}" ${header === item.source_column ? "selected" : ""}>${escapeHtml(header)}</option>`)
    );
    row.innerHTML = `
      <div>
        <strong>${escapeHtml(item.label || field)}</strong>
        <small>置信度 ${(item.confidence * 100).toFixed(0)}% ${item.needs_confirmation ? "需确认" : "自动"}</small>
      </div>
      <select data-field="${escapeHtml(field)}">${options.join("")}</select>
    `;
    wrap.appendChild(row);
  }
  $("confirmHistoryMappingBtn").disabled = false;
  renderGuidance();
}

async function confirmHistoryMapping() {
  const mapping = {};
  for (const select of document.querySelectorAll("#historyMappingList select")) {
    mapping[select.dataset.field] = select.value || null;
  }
  const data = await apiPost("/api/company-history/field-mapping/confirm", {
    file_id: state.historyFile.id,
    mapping,
    confidence: state.historyMappingPreview.mapping,
  });
  if (!data.ok) return alert(data.message);
  $("historyStatus").textContent = `已导入 ${data.normalized_count} 条，生成 ${data.court_profile_count} 个法院画像`;
  $("confirmHistoryMappingBtn").disabled = true;
  await loadHistoryRecords();
  await loadCourtProfiles();
  renderGuidance();
}

async function runAnalysis() {
  $("analysisStatus").textContent = "正在分析...";
  const data = await apiPost(`/api/projects/${state.project.id}/analysis/run`, {
    analysis_type: "consumer_loan_initial_screening",
    safety_mode: "local_rules_only",
  });
  if (!data.ok) return alert(data.message);
  $("analysisStatus").textContent = "分析完成";
  await loadLatestReport();
  renderGuidance();
}

async function loadLatestReport() {
  if (!state.project) return;
  const data = await apiGet(`/api/projects/${state.project.id}/reports/latest`);
  if (!data.ok) {
    $("reportStatus").textContent = "尚未生成";
    $("reportView").innerHTML = "<p>这个项目还没有报告。</p>";
    state.latestReportText = "";
    renderGuidance();
    return;
  }
  $("reportStatus").textContent = "已生成";
  state.latestReportText = data.report.markdown;
  state.currentCalibration = data.report.data?.calibration || null;
  $("reportView").innerHTML = markdownToHtml(data.report.markdown);
  $("aiInput").value = data.report.markdown.slice(0, 2500);
  const next = $("nextActions");
  next.innerHTML = "";
  for (const action of ["补充合同样本", "上传历史处置数据", "生成电话调解话术"]) {
    const chip = document.createElement("span");
    chip.className = "action-chip";
    chip.textContent = action;
    next.appendChild(chip);
  }
  renderProjectCalibration(state.currentCalibration);
  renderGuidance();
}

async function loadLatestLegalRisk() {
  if (!state.project) return;
  const data = await apiGet(`/api/projects/${state.project.id}/legal-risk/latest`);
  if (!data.ok) {
    state.latestLegalRisk = null;
    renderLegalRisk(null);
    $("legalStatus").textContent = "可选上传";
    return;
  }
  state.latestLegalRisk = data.legal_risk.risk;
  renderLegalRisk(state.latestLegalRisk);
  $("legalStatus").textContent = `风险 ${riskLabel(state.latestLegalRisk.overall_risk)}`;
  renderGuidance();
}

function clearExecutionWorkspace() {
  state.executionPlan = null;
  state.executionBatches = [];
  state.executionTasks = [];
  $("executionStatus").textContent = "尚未生成";
  $("executionBatchFilter").innerHTML = `<option value="">全部批次</option>`;
  $("executionSummary").innerHTML = `<p class="muted-copy">确认字段后可生成执行计划。我会自动分批次、给话术和下一步动作。</p>`;
  $("executionTasks").innerHTML = "";
  $("exportExecutionLink").classList.add("disabled-link");
  $("exportExecutionLink").href = "#";
  renderGuidance();
}

async function generateExecutionPlan() {
  if (!state.project) return alert("请先新建或选择项目");
  $("executionStatus").textContent = "生成中...";
  const data = await apiPost(`/api/projects/${state.project.id}/execution/plan`, {});
  if (!data.ok) {
    $("executionStatus").textContent = data.message || "生成失败";
    return;
  }
  state.executionPlan = data.plan;
  state.executionBatches = data.batches || [];
  state.executionTasks = data.tasks || [];
  renderExecutionWorkspace(data.plan, data.batches || [], data.tasks || []);
  renderGuidance();
}

async function loadExecutionWorkspace() {
  if (!state.project) return;
  const [batches, tasks] = await Promise.all([apiGet(`/api/projects/${state.project.id}/execution/batches`), apiGet(`/api/projects/${state.project.id}/execution/tasks`)]);
  if (!batches.ok || !tasks.ok || !tasks.plan) {
    clearExecutionWorkspace();
    return;
  }
  state.executionPlan = tasks.plan;
  state.executionBatches = batches.batches || [];
  state.executionTasks = tasks.tasks || [];
  renderExecutionWorkspace(tasks.plan, state.executionBatches, state.executionTasks);
  renderGuidance();
}

async function refreshExecutionTasks() {
  if (!state.project || !state.executionPlan) return;
  const params = new URLSearchParams();
  if ($("executionBatchFilter").value) params.set("batch_id", $("executionBatchFilter").value);
  if ($("executionStatusFilter").value) params.set("status", $("executionStatusFilter").value);
  if ($("executionTierFilter").value) params.set("tier", $("executionTierFilter").value);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const data = await apiGet(`/api/projects/${state.project.id}/execution/tasks${suffix}`);
  if (!data.ok) return;
  state.executionTasks = data.tasks || [];
  renderExecutionTasks(state.executionTasks);
}

function renderExecutionWorkspace(plan, batches, tasks) {
  $("executionStatus").textContent = plan ? `${plan.summary?.task_count || tasks.length} 个任务` : "尚未生成";
  $("exportExecutionLink").href = `/api/projects/${state.project.id}/execution/export.xlsx?mode=redacted`;
  $("exportExecutionLink").classList.remove("disabled-link");
  const batchSelect = $("executionBatchFilter");
  const selected = batchSelect.value;
  batchSelect.innerHTML = `<option value="">全部批次</option>${batches.map((batch) => `<option value="${escapeHtml(batch.id)}">${escapeHtml(batch.name)}</option>`).join("")}`;
  if (selected) batchSelect.value = selected;
  const summary = plan?.summary || {};
  $("executionSummary").innerHTML = `
    <div class="execution-metrics">
      <span><strong>${summary.task_count || tasks.length}</strong>任务</span>
      <span><strong>${summary.first_round_count || 0}</strong>首轮调解</span>
      <span><strong>${summary.high_priority_count || 0}</strong>高优先级</span>
      <span><strong>${summary.missing_signal_count || 0}</strong>补线索</span>
      <span><strong>${summary.litigation_candidate_count || 0}</strong>诉讼候选</span>
    </div>
  `;
  renderExecutionTasks(tasks);
}

function renderExecutionTasks(tasks) {
  const wrap = $("executionTasks");
  wrap.innerHTML = "";
  if (!tasks.length) {
    wrap.innerHTML = `<p class="muted-copy">当前筛选下没有执行任务。</p>`;
    return;
  }
  for (const task of tasks.slice(0, 80)) {
    const card = document.createElement("div");
    card.className = "execution-task";
    card.dataset.taskId = task.id;
    card.innerHTML = `
      <div class="execution-task-main">
        <div>
          <strong>${escapeHtml(task.batch_name)} · ${escapeHtml(task.masked_debtor)}</strong>
          <span>${escapeHtml(task.tier)} 类 · 优先级 ${escapeHtml(task.priority_score)} · 本金 ${escapeHtml(money(task.principal))}</span>
          <span>${escapeHtml(task.region || "未知")} · ${escapeHtml(task.court || "法院未填")} · ${task.phone_present ? "有手机号" : "缺手机号"}</span>
        </div>
        <span class="status-pill">${escapeHtml(executionStatusLabel(task.status))}</span>
      </div>
      <p>${escapeHtml(task.suggested_action)}：${escapeHtml(task.next_action)}</p>
      <blockquote>${escapeHtml(task.script)}</blockquote>
      <div class="execution-update">
        <select data-role="result">
          <option value="contacted">已接通</option>
          <option value="no_answer">未接</option>
          <option value="unreachable">失联</option>
          <option value="willing">有意愿</option>
          <option value="promise_payment">承诺还款</option>
          <option value="dispute">异议</option>
          <option value="switch_to_litigation">转诉讼评估</option>
          <option value="outsourced">建议分包</option>
          <option value="closed">已关闭</option>
        </select>
        <input data-role="note" type="text" placeholder="跟进备注" />
        <button class="text-button" data-role="save">记录</button>
      </div>
    `;
    card.querySelector('[data-role="save"]').onclick = () => saveExecutionEvent(task.id, card);
    wrap.appendChild(card);
  }
}

async function saveExecutionEvent(taskId, card) {
  const result = card.querySelector('[data-role="result"]').value;
  const note = card.querySelector('[data-role="note"]').value.trim();
  const data = await apiPost(`/api/projects/${state.project.id}/execution/tasks/${taskId}/events`, {
    event_type: "contact_result",
    result,
    note,
    next_action: note || undefined,
  });
  if (!data.ok) return alert(data.message || "记录失败");
  await refreshExecutionTasks();
}

async function createSecurityConfirmation(actionType, confirmationText, extra = {}) {
  const data = await apiPost("/api/security/confirmations", {
    project_id: state.project?.id,
    action_type: actionType,
    confirmation_text: confirmationText,
    ...extra,
  });
  if (!data.ok) {
    throw new Error(data.message || "安全确认失败");
  }
  return data.confirmation;
}

async function exportSensitiveExecution() {
  if (!state.project || !state.executionPlan) return alert("请先生成执行计划");
  const confirmationText = $("sensitiveExportConfirmText").value.trim();
  if (confirmationText.length < 6) {
    $("executionStatus").textContent = "请先填写原文敏感导出确认说明";
    return;
  }
  try {
    $("executionStatus").textContent = "正在创建导出确认...";
    const confirmation = await createSecurityConfirmation("original_sensitive_export", confirmationText, {
      export_mode: "original_sensitive",
    });
    const url = `/api/projects/${state.project.id}/execution/export.xlsx?mode=original_sensitive&confirmation_id=${encodeURIComponent(confirmation.id)}`;
    window.open(url, "_blank", "noopener");
    $("executionStatus").textContent = "已发起原文敏感导出";
    await loadAudit();
  } catch (error) {
    $("executionStatus").textContent = error.message;
  }
}

async function loadKnowledgeNotes() {
  const data = await apiGet("/api/knowledge/notes");
  if (!data.ok) return;
  state.knowledgeNotes = data.notes || [];
  renderKnowledgeNotes(state.knowledgeNotes);
  renderGuidance();
}

function renderKnowledgeNotes(notes) {
  const wrap = $("knowledgeNotes");
  wrap.innerHTML = "";
  $("knowledgeStatus").textContent = notes.length ? `${notes.length} 条记忆` : "本地 Markdown";
  if (!notes.length) {
    wrap.innerHTML = `<p class="muted-copy">还没有知识库笔记。先沉淀当前项目，或保存一条公司偏好。</p>`;
    return;
  }
  for (const note of notes.slice(0, 80)) {
    const card = document.createElement("button");
    card.className = "knowledge-note";
    card.innerHTML = `
      <strong>${escapeHtml(note.title)}</strong>
      <span>${escapeHtml(note.note_type)} · ${escapeHtml(knowledgeStatusLabel(note.status))}</span>
      <small>${escapeHtml(note.summary)}</small>
    `;
    card.onclick = () => openKnowledgeNote(note.id);
    wrap.appendChild(card);
  }
}

async function openKnowledgeNote(noteId) {
  const data = await apiGet(`/api/knowledge/notes/${encodeURIComponent(noteId)}`);
  if (!data.ok) return alert(data.message || "读取笔记失败");
  const note = data.note;
  state.selectedKnowledgeNote = note;
  $("knowledgeStatus").textContent = `${knowledgeStatusLabel(note.status)} · ${note.title}`;
  $("knowledgePreview").innerHTML = markdownToHtml(note.content_text || note.summary || "");
  $("knowledgeConfirmNote").value = "";
  $("confirmKnowledgeBtn").disabled = note.status === "confirmed";
  $("confirmKnowledgeBtn").textContent = note.status === "confirmed" ? "已确认" : "确认这条记忆";
}

async function syncKnowledge() {
  if (!state.project) return alert("请先新建或选择项目");
  $("knowledgeStatus").textContent = "同步中...";
  const data = await apiPost(`/api/projects/${state.project.id}/knowledge/sync`, {});
  if (!data.ok) {
    $("knowledgeStatus").textContent = data.message || "同步失败";
    return;
  }
  $("knowledgeStatus").textContent = `已沉淀 ${data.notes?.length || 0} 条`;
  await loadKnowledgeNotes();
  if (data.project_note?.id) await openKnowledgeNote(data.project_note.id);
  renderGuidance();
}

async function searchKnowledge() {
  const query = $("knowledgeSearchInput").value.trim();
  if (!query) {
    await loadKnowledgeNotes();
    return;
  }
  $("knowledgeStatus").textContent = "搜索中...";
  const data = await apiPost("/api/knowledge/search", { query });
  if (!data.ok) {
    $("knowledgeStatus").textContent = data.message || "搜索失败";
    return;
  }
  state.knowledgeNotes = data.notes || [];
  renderKnowledgeNotes(state.knowledgeNotes);
  $("knowledgeStatus").textContent = `${query} · ${state.knowledgeNotes.length} 条`;
}

async function saveCompanyPreference() {
  const payload = {
    title: $("preferenceTitle").value.trim(),
    preference_type: $("preferenceType").value.trim(),
    content: $("preferenceContent").value.trim(),
    confirmed: $("preferenceConfirmed").checked,
    source: state.project ? `项目 ${state.project.name}` : "用户输入",
  };
  if (!payload.title || !payload.content) return alert("请填写偏好标题和内容");
  $("knowledgeStatus").textContent = "保存偏好...";
  const data = await apiPost("/api/knowledge/company-preferences", payload);
  if (!data.ok) {
    $("knowledgeStatus").textContent = data.message || "保存失败";
    return;
  }
  $("knowledgeStatus").textContent = knowledgeStatusLabel(data.note.status);
  $("preferenceContent").value = "";
  await loadKnowledgeNotes();
  await openKnowledgeNote(data.note.id);
}

async function confirmKnowledgeNote() {
  if (!state.selectedKnowledgeNote) return alert("请先选择一条知识库笔记");
  $("knowledgeStatus").textContent = "确认记忆...";
  const data = await apiPost(`/api/knowledge/notes/${encodeURIComponent(state.selectedKnowledgeNote.id)}/confirm`, {
    confirmation_note: $("knowledgeConfirmNote").value.trim(),
    project_id: state.project?.id,
  });
  if (!data.ok) {
    $("knowledgeStatus").textContent = data.message || "确认失败";
    return;
  }
  await loadKnowledgeNotes();
  await openKnowledgeNote(data.note.id);
}

async function saveCourtExperience() {
  const courtName = $("courtExperienceName").value.trim();
  const experience = $("courtExperienceContent").value.trim();
  if (!courtName || !experience) return alert("请填写法院名称和复盘内容");
  $("knowledgeStatus").textContent = "保存法院经验...";
  const data = await apiPost(`/api/knowledge/court-notes/${encodeURIComponent(courtName)}/experience`, {
    title: `${courtName} 处置复盘`,
    experience,
    confirmed: $("courtExperienceConfirmed").checked,
    source: state.project ? `项目 ${state.project.name}` : "用户输入",
  });
  if (!data.ok) {
    $("knowledgeStatus").textContent = data.message || "保存失败";
    return;
  }
  $("courtExperienceContent").value = "";
  await loadKnowledgeNotes();
  await openKnowledgeNote(data.note.id);
  renderGuidance();
}

async function loadPrivateSkillDrafts() {
  const data = await apiGet("/api/skills/private-drafts");
  if (!data.ok) return;
  state.privateSkillDrafts = data.drafts || [];
  renderPrivateSkillDrafts(state.privateSkillDrafts);
}

function renderPrivateSkillDrafts(drafts) {
  const wrap = $("privateSkillDrafts");
  wrap.innerHTML = "";
  $("privateSkillStatus").textContent = drafts.length ? `${drafts.length} 个草稿` : "未启用调用";
  if (!drafts.length) {
    wrap.innerHTML = `<p class="muted-copy">还没有私有 skill 草稿。请先确认记忆，再生成草稿。</p>`;
    return;
  }
  for (const draft of drafts.slice(0, 80)) {
    const card = document.createElement("button");
    card.className = "private-skill-draft";
    card.innerHTML = `
      <strong>${escapeHtml(draft.name)}</strong>
      <span>${escapeHtml(draft.draft_type)} · ${escapeHtml(privateSkillStatusLabel(draft.status))} · 风险 ${escapeHtml(draft.risk_level)}</span>
      <small>来源 ${draft.source_note_ids?.length || 0} 条 · 不自动启用</small>
    `;
    card.onclick = () => openPrivateSkillDraft(draft.id);
    wrap.appendChild(card);
  }
}

async function openPrivateSkillDraft(draftId) {
  const data = await apiGet(`/api/skills/private-drafts/${encodeURIComponent(draftId)}`);
  if (!data.ok) return alert(data.message || "读取草稿失败");
  const draft = data.draft;
  state.selectedPrivateSkillDraft = draft;
  $("privateSkillStatus").textContent = `${privateSkillStatusLabel(draft.status)} · 不自动启用`;
  $("privateSkillPreview").innerHTML = markdownToHtml(draft.markdown || "");
  const disabled = draft.status === "archived";
  $("approvePrivateSkillBtn").disabled = disabled;
  $("revisePrivateSkillBtn").disabled = disabled;
  $("archivePrivateSkillBtn").disabled = disabled;
}

async function generatePrivateSkillDraft() {
  $("privateSkillStatus").textContent = "生成中...";
  const data = await apiPost("/api/skills/private-drafts/generate", { draft_type: $("privateSkillType").value });
  if (!data.ok) {
    $("privateSkillStatus").textContent = data.message || "生成失败";
    return;
  }
  await loadPrivateSkillDrafts();
  await openPrivateSkillDraft(data.draft.id);
}

async function reviewPrivateSkillDraft(status) {
  if (!state.selectedPrivateSkillDraft) return alert("请先选择一个私有 skill 草稿");
  $("privateSkillStatus").textContent = "审核中...";
  const data = await apiPost(`/api/skills/private-drafts/${encodeURIComponent(state.selectedPrivateSkillDraft.id)}/review`, {
    status,
    reviewer: $("privateSkillReviewer").value.trim() || "local_user",
    review_note: $("privateSkillReviewNote").value.trim(),
  });
  if (!data.ok) {
    $("privateSkillStatus").textContent = data.message || "审核失败";
    return;
  }
  await loadPrivateSkillDrafts();
  await openPrivateSkillDraft(data.draft.id);
}

async function saveModel() {
  const key = $("modelKey").value.trim();
  const data = await apiPost("/api/settings/model", {
    mode: state.selectedMode,
    provider: $("modelProvider").value,
    base_url: $("modelBaseUrl").value.trim(),
    model: $("modelName").value.trim() || "auto",
    ...(key ? { api_key: key } : {}),
    allow_original_sensitive_data: state.selectedMode === "original_cloud",
  });
  if (!data.ok) return alert(data.message);
  $("safetyStatus").textContent = data.model.mode;
  $("modelStatus").textContent = data.model.api_key_present ? "模型已配置" : "模型未配置";
  $("aiStatus").textContent = "模型配置已保存";
}

async function saveVoice() {
  const key = $("voiceKey").value.trim();
  const data = await apiPost("/api/settings/voice", {
    mode: $("enhancedVoice").checked ? "enhanced" : "builtin_fallback",
    enhanced_enabled: $("enhancedVoice").checked,
    asr_provider: "builtin_browser",
    tts_provider: $("voiceProvider").value,
    tts_base_url: $("voiceBaseUrl").value.trim(),
    tts_model: "tts-1",
    tts_voice: $("voiceName").value.trim() || "nova",
    ...(key ? { tts_api_key: key } : {}),
    sensitive_data_readout: "masked_only",
  });
  if (!data.ok) return alert(data.message);
  $("voiceStatus").textContent = data.voice.enhanced_enabled ? "增强语音" : "自带语音";
  $("voicePanelStatus").textContent = data.voice.enhanced_enabled ? "增强语音" : "自带语音";
}

async function loadProviders() {
  const [model, voice] = await Promise.all([apiGet("/api/settings/model/providers"), apiGet("/api/settings/voice/providers")]);
  if (model.ok) state.modelProviders = model.providers || [];
  if (voice.ok) state.voiceProviders = voice.providers || [];
  fillSelect($("modelProvider"), state.modelProviders, "deepseek");
  fillSelect($("voiceProvider"), state.voiceProviders, "builtin_browser");
}

async function loadDocumentParserStatus() {
  const data = await apiGet("/api/settings/document-parser");
  if (!data.ok) return;
  state.documentParser = data;
  if (state.latestLegalRisk) renderLegalRisk(state.latestLegalRisk);
  else renderLegalRisk(null);
}

function applyProviderDefaults() {
  const modelProvider = providerById(state.modelProviders, $("modelProvider").value);
  if (!$("modelBaseUrl").value && modelProvider.base_url) $("modelBaseUrl").value = modelProvider.base_url;
  if (!$("modelName").value && modelProvider.default_model) $("modelName").value = modelProvider.default_model;
  const voiceProvider = providerById(state.voiceProviders, $("voiceProvider").value);
  if (!$("voiceBaseUrl").value && voiceProvider.default_base_url) $("voiceBaseUrl").value = voiceProvider.default_base_url;
  if (!$("voiceName").value && voiceProvider.default_voice) $("voiceName").value = voiceProvider.default_voice;
}

async function loadHealth() {
  const data = await apiGet("/api/health");
  if (!data.ok) {
    safeText("healthStatus", "服务未确认");
    safeText("serviceAddress", `当前页面：${window.location.origin}。如果不是 NPA Agent，请换端口启动。`);
    return;
  }
  state.health = data;
  safeText("healthStatus", data.app_name === "NPA Agent" ? "NPA 服务正常" : "服务异常");
  safeText("serviceAddress", `当前服务：${data.address || window.location.origin} · 数据目录 ${data.data_dir_present ? "就绪" : "未就绪"}`);
}

async function loadYindengNotices() {
  const [notices, subscriptions, alerts] = await Promise.all([
    apiGet("/api/intelligence/yindeng/notices"),
    apiGet("/api/intelligence/yindeng/subscriptions"),
    apiGet("/api/intelligence/yindeng/alerts"),
  ]);
  if (subscriptions.ok) state.yindengSubscriptions = subscriptions.subscriptions || [];
  if (alerts.ok) {
    state.yindengAlerts = alerts.alerts || [];
    renderYindengAlerts(state.yindengAlerts);
  }
  if (notices.ok) renderYindengList(notices.notices || []);
}

async function loadHistoryRecords() {
  const [data, analyticsData] = await Promise.all([apiGet("/api/company-history/records"), apiGet("/api/company-history/analytics")]);
  if (!data.ok) return;
  if (analyticsData.ok) {
    state.historyAnalytics = analyticsData.analytics;
    renderHistoryAnalytics(state.historyAnalytics);
  }
  const wrap = $("historyRecords");
  const records = data.records || [];
  state.historyRecords = records;
  wrap.innerHTML = "";
  if (!records.length) {
    wrap.innerHTML = `<p class="muted-copy">还没有公司历史处置数据。</p>`;
    renderGuidance();
    return;
  }
  for (const record of records.slice(0, 6)) {
    const card = document.createElement("div");
    card.className = "notice-card";
    card.innerHTML = `
      <strong>${escapeHtml(record.project_name || "历史项目")}</strong>
      <span>${escapeHtml(record.asset_type || "资产类型未填")} · ${escapeHtml(record.region || "地区未填")} · ${escapeHtml(record.court_name || "法院未填")}</span>
      <span>本金 ${escapeHtml(money(record.principal_total))} · 回款 ${escapeHtml(money(record.recovered_amount))} · 回收率 ${escapeHtml(percent(record.derived?.recovery_rate))}</span>
    `;
    wrap.appendChild(card);
  }
  renderGuidance();
}

function renderHistoryAnalytics(analytics) {
  const wrap = $("historyAnalytics");
  if (!wrap) return;
  if (!analytics || !analytics.total_records) {
    wrap.innerHTML = `<p class="muted-copy">上传历史处置数据后，我会按地区、法院、金额段和处置方式做聚合。</p>`;
    return;
  }
  wrap.innerHTML = `
    <div class="history-metrics">
      <span><strong>${analytics.total_records}</strong>历史样本</span>
      <span><strong>${analytics.usable_recovery_count}</strong>可算回收率</span>
      <span><strong>${escapeHtml(percent(analytics.average_recovery_rate))}</strong>平均回收率</span>
      <span><strong>${escapeHtml(compactNumber(analytics.average_recovery_months))}</strong>平均周期（月）</span>
    </div>
    ${historyBreakdownTable("地区", analytics.by_region)}
    ${historyBreakdownTable("法院", analytics.by_court)}
    ${historyBreakdownTable("金额段", analytics.by_amount_bucket)}
    ${historyBreakdownTable("处置方式", analytics.by_disposal_method)}
  `;
}

function historyBreakdownTable(title, rows = []) {
  const body = rows
    .slice(0, 5)
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.key)}</td>
          <td>${escapeHtml(item.sample_count)}</td>
          <td>${escapeHtml(percent(item.average_recovery_rate))}</td>
          <td>${escapeHtml(compactNumber(item.average_recovery_months))}</td>
        </tr>
      `
    )
    .join("");
  return `
    <div class="history-breakdown">
      <strong>${escapeHtml(title)}</strong>
      <table>
        <thead><tr><th>维度值</th><th>样本</th><th>回收率</th><th>周期</th></tr></thead>
        <tbody>${body || `<tr><td>无数据</td><td>0</td><td>样本不足</td><td>样本不足</td></tr>`}</tbody>
      </table>
    </div>
  `;
}

function renderProjectCalibration(calibration) {
  const wrap = $("projectCalibration");
  if (!wrap) return;
  if (!calibration) {
    wrap.innerHTML = `<p class="muted-copy">生成项目报告后，这里会显示本项目命中的历史样本和报价修正依据。</p>`;
    return;
  }
  const records = (calibration.matched_records || [])
    .slice(0, 5)
    .map((item) => `<li>${escapeHtml(item.project_name || "历史项目")}：${escapeHtml(item.match_reason || "存在匹配")}，回收率 ${escapeHtml(percent(item.recovery_rate))}，匹配分 ${escapeHtml(item.match_score || 0)}</li>`)
    .join("");
  const reasons = (calibration.reasons || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  wrap.innerHTML = `
    <div class="calibration-card">
      <strong>本项目历史校准</strong>
      <span>样本 ${calibration.matched_count || 0} · 可算回收率 ${calibration.usable_recovery_count || 0} · 可信度 ${escapeHtml(calibration.sample_confidence || calibration.confidence || "none")} · 修正 ${(Number(calibration.adjustment || 0) * 100).toFixed(1)}%</span>
      <small>当前金额段：${escapeHtml(calibration.project_context?.amount_bucket || "unknown")} · 户均本金 ${escapeHtml(money(calibration.project_context?.average_principal))}</small>
      <ul>${records || "<li>暂无命中历史样本，规则报价为主。</li>"}</ul>
      <ul>${reasons}</ul>
    </div>
  `;
}

async function loadCourtProfiles() {
  const data = await apiGet("/api/courts/profiles");
  if (!data.ok) return;
  const wrap = $("courtProfiles");
  const profiles = data.profiles || [];
  state.courtProfiles = profiles;
  $("courtStatus").textContent = profiles.length ? `${profiles.length} 个法院` : "尚未生成";
  wrap.innerHTML = "";
  if (!profiles.length) {
    wrap.innerHTML = `<p class="muted-copy">上传历史处置数据后，我会自动汇总法院画像。</p>`;
    renderGuidance();
    return;
  }
  for (const profile of profiles.slice(0, 10)) {
    const card = document.createElement("div");
    card.className = "court-card";
    const failures = (profile.common_failure_reasons || []).join("、") || "暂无";
    card.innerHTML = `
      <div>
        <strong>${escapeHtml(profile.court_name)}</strong>
        <span>${escapeHtml(profile.label)} · ${escapeHtml(profile.region || "地区未填")}</span>
      </div>
      <div class="court-metrics">
        <span>${profile.sample_count} 样本</span>
        <span>${escapeHtml(percent(profile.average_recovery_rate))}</span>
        <span>${profile.average_recovery_months ? `${Number(profile.average_recovery_months).toFixed(1)} 月` : "周期不足"}</span>
      </div>
      <small>主金额段：${escapeHtml(profile.primary_amount_bucket || "unknown")} · 主处置方式：${escapeHtml(profile.primary_disposal_method || "未填")} · 可信度 ${escapeHtml(profile.sample_confidence || "low")}</small>
      <small>常见失败原因：${escapeHtml(failures)}</small>
    `;
    wrap.appendChild(card);
  }
  renderGuidance();
}

function renderYindengList(notices) {
  const list = $("yindengList");
  list.innerHTML = "";
  if (!notices.length) {
    list.innerHTML = `<p class="muted-copy">还没有银登机会记录。</p>`;
    return;
  }
  for (const notice of notices) {
    const card = document.createElement("div");
    card.className = "notice-card";
    const attachmentSummary = (notice.attachments || [])
      .slice(0, 3)
      .map((item) => `${item.label || "附件"}:${item.parse_status || item.file_type || "未解析"}`)
      .join(" · ");
    const extraction = notice.parsed?.extraction?.extraction_method || notice.parsed?.source_mix || "文本";
    card.innerHTML = `
      <strong>${escapeHtml(notice.title)}</strong>
      <span>置信度 ${escapeHtml(notice.confidence)} · ${escapeHtml(notice.asset_type || "unknown")} · 解析 ${escapeHtml(extraction)} · 附件 ${(notice.attachments || []).length}</span>
      <span>本金 ${escapeHtml(money(notice.principal))} · 户数 ${escapeHtml(notice.debtor_count ?? "未识别")}</span>
      <span>地区 ${(notice.regions || []).map(escapeHtml).join("、") || "未识别"}</span>
      ${attachmentSummary ? `<small>${escapeHtml(attachmentSummary)}</small>` : ""}
      <button class="text-button" data-notice-id="${escapeHtml(notice.id)}">生成项目</button>
    `;
    card.querySelector("button").onclick = () => createProjectFromNotice(notice.id);
    list.appendChild(card);
  }
}

function renderYindengAlerts(alerts) {
  const wrap = $("yindengAlerts");
  if (!wrap) return;
  if (!alerts.length) {
    wrap.innerHTML = `<p class="muted-copy">暂无关键词命中提醒。</p>`;
    return;
  }
  wrap.innerHTML = `<h3>本地提醒</h3>`;
  for (const alert of alerts.slice(0, 5)) {
    const card = document.createElement("div");
    card.className = "notice-card compact";
    card.innerHTML = `
      <strong>${escapeHtml(alert.keyword)} 命中</strong>
      <span>${escapeHtml(alert.title || "银登公告")}</span>
      <span>本金 ${escapeHtml(money(alert.principal))} · 户数 ${escapeHtml(alert.debtor_count ?? "未识别")}</span>
    `;
    wrap.appendChild(card);
  }
}

async function saveYindengSubscription() {
  const keyword = $("yindengKeyword").value.trim();
  if (!keyword) return alert("请先填写订阅关键词");
  const data = await apiPost("/api/intelligence/yindeng/subscriptions", { keyword, enabled: true });
  if (!data.ok) {
    $("yindengStatus").textContent = data.message || "订阅失败";
    return;
  }
  $("yindengKeyword").value = "";
  $("yindengStatus").textContent = `已订阅：${keyword}`;
  await loadYindengNotices();
}

async function fetchYindeng() {
  const url = $("yindengUrl").value.trim();
  if (!url) return alert("请先填写银登公开公告 URL");
  $("yindengStatus").textContent = "抓取中...";
  const data = await apiPost("/api/intelligence/yindeng/fetch", { url, source_type: "public_url" });
  if (!data.ok) {
    $("yindengStatus").textContent = data.message || "抓取失败";
    return;
  }
  $("yindengStatus").textContent = `已解析：${data.notice.confidence}`;
  if (data.attachment_extractions?.length) {
    const parsedCount = data.attachment_extractions.filter((item) => item.parse_status === "parsed").length;
    $("yindengStatus").textContent = `已解析：${data.notice.confidence} · 附件 ${parsedCount}/${data.attachment_extractions.length}`;
  }
  $("aiInput").value = data.notice.raw_text.slice(0, 2500);
  await loadYindengNotices();
}

async function parseYindengText() {
  const text = $("yindengText").value.trim();
  if (!text) return alert("请先粘贴公告正文");
  $("yindengStatus").textContent = "解析正文...";
  const data = await apiPost("/api/intelligence/yindeng/parse", { text, source_type: "manual_text", source_url: $("yindengUrl").value.trim() });
  if (!data.ok) {
    $("yindengStatus").textContent = data.message || "解析失败";
    return;
  }
  $("yindengStatus").textContent = `已解析：${data.notice.confidence}`;
  $("aiInput").value = text.slice(0, 2500);
  await loadYindengNotices();
}

async function parseYindengFile() {
  const file = $("yindengFileInput").files[0];
  if (!file) return alert("请先选择银登公告 PDF、图片、TXT 或 HTML 文件");
  $("yindengStatus").textContent = "解析公告文件...";
  const content = await fileToBase64(file);
  const data = await apiPost("/api/intelligence/yindeng/parse", {
    filename: file.name,
    content_base64: content,
    source_type: "manual_file",
    source_url: $("yindengUrl").value.trim(),
  });
  if (!data.ok) {
    $("yindengStatus").textContent = data.message || "文件解析失败";
    return;
  }
  $("yindengStatus").textContent = `已解析文件：${data.notice.confidence}`;
  $("aiInput").value = data.notice.raw_text.slice(0, 2500);
  await loadYindengNotices();
}

async function createProjectFromNotice(noticeId) {
  const data = await apiPost(`/api/intelligence/yindeng/notices/${noticeId}/create-project`, {});
  if (!data.ok) return alert(data.message);
  state.project = data.project;
  state.file = null;
  state.mappingPreview = null;
  state.fieldMappingConfirmed = false;
  state.latestReportText = "";
  $("currentProjectTitle").textContent = state.project.name;
  $("uploadStatus").textContent = "已从银登公告创建项目，请继续上传资产包 Excel";
  state.latestLegalRisk = null;
  renderLegalRisk(null);
  $("legalStatus").textContent = "可选上传";
  clearExecutionWorkspace();
  await loadProjects();
  renderGuidance();
}

async function generateAi() {
  const content = $("aiInput").value.trim() || $("commandInput").value.trim();
  if (!content) return alert("请先输入报告、公告或任务内容");
  $("aiStatus").textContent = "AI 生成中...";
  const payload = {
    purpose: $("aiPurpose").value,
    content,
    safety_mode: state.selectedMode,
    project_id: state.project?.id,
  };
  if (state.selectedMode === "original_cloud") {
    const confirmationText = $("originalCloudConfirmText").value.trim();
    if (confirmationText.length < 6) {
      $("aiStatus").textContent = "原文云端分析需要先填写确认说明";
      return;
    }
    try {
      const confirmation = await createSecurityConfirmation("original_cloud_ai", confirmationText, {
        purpose: payload.purpose,
        safety_mode: "original_cloud",
      });
      payload.confirm_original_cloud = true;
      payload.confirmation_id = confirmation.id;
    } catch (error) {
      $("aiStatus").textContent = error.message;
      await loadAudit();
      return;
    }
  }
  const data = await apiPost("/api/ai/generate", payload);
  if (!data.ok) {
    $("aiStatus").textContent = data.message || "AI 调用失败";
    await loadAudit();
    return;
  }
  $("aiStatus").textContent = `${data.result.provider} / ${data.result.model}`;
  $("aiOutput").innerHTML = markdownToHtml(data.result.text);
  await loadAudit();
}

async function loadAudit() {
  const [summary, logs] = await Promise.all([apiGet("/api/audit/summary"), apiGet("/api/audit/logs?limit=80")]);
  if (summary.ok) {
    state.auditSummary = summary.summary;
    renderAuditSummary(summary.summary);
  }
  if (logs.ok) {
    state.auditLogs = logs.logs || [];
    renderAuditLogs(state.auditLogs);
  }
}

function renderAuditSummary(summary) {
  $("auditStatus").textContent = summary.latest_at ? `最近 ${new Date(summary.latest_at).toLocaleString()}` : "暂无审计";
  $("auditSummary").innerHTML = `
    <div class="audit-metrics">
      <span><strong>${summary.total || 0}</strong>审计记录</span>
      <span><strong>${summary.high_risk_count || 0}</strong>高风险动作</span>
      <span><strong>${summary.original_cloud_count || 0}</strong>原文云端</span>
      <span><strong>${summary.original_export_count || 0}</strong>原文导出</span>
      <span><strong>${summary.network_call_count || 0}</strong>联网动作</span>
      <span><strong>${summary.memory_write_count || 0}</strong>记忆写入</span>
    </div>
  `;
}

function renderAuditLogs(logs) {
  const wrap = $("auditLogs");
  if (!logs.length) {
    wrap.innerHTML = `<p class="muted-copy">还没有审计记录。上传、解析、模型调用、导出和记忆写入后会出现在这里。</p>`;
    return;
  }
  wrap.innerHTML = "";
  for (const log of logs) {
    const event = log.event || {};
    const card = document.createElement("div");
    card.className = "audit-card";
    card.innerHTML = `
      <div>
        <strong>${escapeHtml(log.event_type)}</strong>
        <span>${escapeHtml(new Date(log.created_at).toLocaleString())} · ${escapeHtml(log.project_id || "全局")}</span>
      </div>
      <div class="audit-flags">
        <span>敏感读取：${escapeHtml(yesNo(event.sensitive_data_access))}</span>
        <span>联网：${escapeHtml(yesNo(event.network_access))}</span>
        <span>写记忆：${escapeHtml(yesNo(event.memory_write))}</span>
        <span>导出：${escapeHtml(event.export_mode || "否")}</span>
        <span>安全模式：${escapeHtml(event.safety_mode || "本地/默认")}</span>
      </div>
      <small>${escapeHtml(auditEventSummary(event))}</small>
    `;
    wrap.appendChild(card);
  }
}

function auditEventSummary(event) {
  const parts = [];
  if (event.provider) parts.push(`provider=${event.provider}`);
  if (event.model) parts.push(`model=${event.model}`);
  if (event.purpose) parts.push(`用途=${event.purpose}`);
  if (event.extraction_method) parts.push(`解析=${event.extraction_method}`);
  if (event.ocr_status) parts.push(`OCR=${event.ocr_status}`);
  if (event.confirmation_id) parts.push(`确认=${event.confirmation_id}`);
  if (event.prompt_chars) parts.push(`prompt字符=${event.prompt_chars}`);
  if (event.response_chars) parts.push(`输出字符=${event.response_chars}`);
  return parts.join(" · ") || "仅记录动作元数据，不保存完整敏感正文。";
}

function speakBuiltin(text) {
  if (!("speechSynthesis" in window)) {
    $("voiceRuntimeStatus").textContent = "当前浏览器不支持自带朗读。";
    return false;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text.slice(0, 1000));
  utterance.lang = "zh-CN";
  utterance.rate = 1;
  window.speechSynthesis.speak(utterance);
  return true;
}

async function speakText(text) {
  if (!text.trim()) return alert("当前没有可朗读的内容");
  if (!$("enhancedVoice").checked) {
    speakBuiltin(text);
    return;
  }
  $("voiceRuntimeStatus").textContent = "增强语音合成中...";
  const data = await apiPost("/api/voice/tts", { text });
  if (!data.ok) {
    $("voiceRuntimeStatus").textContent = `${data.message} 已切换自带语音。`;
    speakBuiltin(text);
    return;
  }
  const audio = new Audio(`data:${data.content_type};base64,${data.audio_base64}`);
  audio.play();
  $("voiceRuntimeStatus").textContent = `正在播报：${data.provider}`;
}

function reportSummaryText() {
  const source = state.latestReportText || $("reportView").innerText || $("aiOutput").innerText || $("commandInput").value;
  return source.split("\n").filter(Boolean).slice(0, 12).join("。");
}

function startVoiceInput() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    $("voiceRuntimeStatus").textContent = "当前浏览器不支持语音识别，请直接输入文字。";
    return;
  }
  if (state.recognition) state.recognition.abort();
  const recognition = new SpeechRecognition();
  state.recognition = recognition;
  recognition.lang = "zh-CN";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  recognition.onstart = () => {
    $("voiceRuntimeStatus").textContent = "正在听...";
  };
  recognition.onresult = (event) => {
    const text = event.results?.[0]?.[0]?.transcript || "";
    $("commandInput").value = text;
    $("aiInput").value = text;
    $("voiceRuntimeStatus").textContent = "已识别语音";
  };
  recognition.onerror = () => {
    $("voiceRuntimeStatus").textContent = "语音识别不可用，请改用键盘输入。";
  };
  recognition.onend = () => {
    if ($("voiceRuntimeStatus").textContent === "正在听...") $("voiceRuntimeStatus").textContent = "语音待命";
  };
  recognition.start();
}

function bindEvents() {
  $("newProjectBtn").onclick = createProject;
  $("uploadBtn").onclick = uploadFile;
  $("confirmMappingBtn").onclick = confirmMapping;
  $("uploadHistoryBtn").onclick = uploadHistoryFile;
  $("confirmHistoryMappingBtn").onclick = confirmHistoryMapping;
  $("uploadLegalBtn").onclick = uploadLegalDocument;
  $("runAnalysisBtn").onclick = runAnalysis;
  $("generateExecutionBtn").onclick = generateExecutionPlan;
  $("exportSensitiveExecutionBtn").onclick = exportSensitiveExecution;
  $("executionBatchFilter").onchange = refreshExecutionTasks;
  $("executionStatusFilter").onchange = refreshExecutionTasks;
  $("executionTierFilter").onchange = refreshExecutionTasks;
  $("syncKnowledgeBtn").onclick = syncKnowledge;
  $("searchKnowledgeBtn").onclick = searchKnowledge;
  $("knowledgeSearchInput").onkeydown = (event) => {
    if (event.key === "Enter") searchKnowledge();
  };
  $("savePreferenceBtn").onclick = saveCompanyPreference;
  $("confirmKnowledgeBtn").onclick = confirmKnowledgeNote;
  $("saveCourtExperienceBtn").onclick = saveCourtExperience;
  $("generatePrivateSkillBtn").onclick = generatePrivateSkillDraft;
  $("approvePrivateSkillBtn").onclick = () => reviewPrivateSkillDraft("approved");
  $("revisePrivateSkillBtn").onclick = () => reviewPrivateSkillDraft("needs_revision");
  $("archivePrivateSkillBtn").onclick = () => reviewPrivateSkillDraft("archived");
  $("saveModelBtn").onclick = saveModel;
  $("saveVoiceBtn").onclick = saveVoice;
  $("fetchYindengBtn").onclick = fetchYindeng;
  $("parseYindengTextBtn").onclick = parseYindengText;
  $("parseYindengFileBtn").onclick = parseYindengFile;
  $("saveYindengSubscriptionBtn").onclick = saveYindengSubscription;
  $("generateAiBtn").onclick = generateAi;
  $("refreshAuditBtn").onclick = loadAudit;
  $("voiceListenBtn").onclick = startVoiceInput;
  $("voiceQuickInputBtn").onclick = startVoiceInput;
  $("readSummaryBtn").onclick = () => speakText(reportSummaryText());
  $("voiceReadReportBtn").onclick = () => speakText(reportSummaryText());
  $("stopVoiceBtn").onclick = () => window.speechSynthesis?.cancel();
  document.querySelectorAll(".task-button").forEach((button) => {
    button.onclick = () => {
      document.querySelectorAll(".task-button").forEach((item) => item.classList.toggle("active", item === button));
      const task = button.dataset.task;
      if (task === "analysis") document.querySelector(".guided-workspace")?.scrollIntoView({ behavior: "smooth", block: "start" });
      if (task === "strategy") {
        openExpertDrawer();
        $("executionStatus")?.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      if (task === "script") {
        openExpertDrawer();
        $("aiPurpose").value = "phone_script";
        $("aiInput")?.focus();
      }
      if (task === "history") document.querySelector(".project-list")?.scrollIntoView({ behavior: "smooth", block: "start" });
    };
  });
  $("modelProvider").onchange = () => {
    $("modelBaseUrl").value = "";
    $("modelName").value = "";
    applyProviderDefaults();
  };
  $("voiceProvider").onchange = () => {
    $("voiceBaseUrl").value = "";
    $("voiceName").value = "";
    applyProviderDefaults();
  };
  document.querySelectorAll(".segmented button").forEach((button) => {
    button.onclick = () => {
      state.selectedMode = button.dataset.mode;
      document.querySelectorAll(".segmented button").forEach((item) => item.classList.toggle("selected", item === button));
    };
  });
}

async function init() {
  bindEvents();
  renderGuidance();
  await loadHealth();
  await loadProviders();
  await loadDocumentParserStatus();
  applyProviderDefaults();
  await loadProjects();
  const model = await apiGet("/api/settings/model");
  const voice = await apiGet("/api/settings/voice");
  if (model.ok) {
    $("safetyStatus").textContent = model.model.mode;
    $("modelStatus").textContent = model.model.api_key_present ? "模型已配置" : "模型未配置";
    $("modelProvider").value = model.model.provider || "deepseek";
    $("modelBaseUrl").value = model.model.base_url || providerById(state.modelProviders, $("modelProvider").value).base_url || "";
    $("modelName").value = model.model.model || "auto";
  }
  if (voice.ok) {
    $("voiceStatus").textContent = voice.voice.enhanced_enabled ? "增强语音" : "自带语音";
    $("voicePanelStatus").textContent = voice.voice.enhanced_enabled ? "增强语音" : "自带语音";
    $("enhancedVoice").checked = Boolean(voice.voice.enhanced_enabled);
    $("voiceProvider").value = voice.voice.tts_provider || "builtin_browser";
    $("voiceBaseUrl").value = voice.voice.tts_base_url || providerById(state.voiceProviders, $("voiceProvider").value).default_base_url || "";
    $("voiceName").value = voice.voice.tts_voice || "nova";
  }
  await loadYindengNotices();
  await loadHistoryRecords();
  await loadCourtProfiles();
  await loadKnowledgeNotes();
  await loadPrivateSkillDrafts();
  await loadAudit();
  renderGuidance();
}

init();
