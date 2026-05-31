function defaultApiBase() {
  const host = window.location.hostname;
  if (window.location.protocol.startsWith("http") && host) {
    return `${window.location.protocol}//${host}:5290`;
  }
  return "http://127.0.0.1:5290";
}

const API_BASE = window.QIANCHUAN_API_BASE || defaultApiBase();
const SESSION_KEY = "qianchuan_control_session";
const SNAPSHOT_KEY = "qianchuan_control_startup_snapshot";
const DEFAULT_ADVERTISER_ID = 11;
const NEAR_BUDGET_ACTION = "NEAR_BUDGET_ROI_ADD_BUDGET";
const HOURLY_ROI_GOAL_ACTION = "HOURLY_SPEND_INCREASE_ROI_GOAL";
const PLAN_SMART_BID_TYPES = ["SMART_BID_CUSTOM", "SMART_BID_CONSERVATIVE"];
const CONTROL_PLAN_SMART_BID_TYPES = ["SMART_BID_CUSTOM"];
const OPERATION_BOARD_REFRESH_MS = 15000;
const PLAN_SMART_BID_LABELS = {
  SMART_BID_CUSTOM: "控成本",
  SMART_BID_CONSERVATIVE: "放量",
};

const fallbackImage =
  "https://p3-aio.ecombdimg.com/obj/ecom-shop-material/jpeg_m_ec2dff6d15c3c3f160742c71d879636c_sx_564482_www1500-1500";
const ruleFormLogic = window.QianchuanRuleFormLogic;
let operationBoardRefreshTimer = 0;
let operationBoardLoadPromise = null;

const state = {
  sessionToken: window.localStorage.getItem(SESSION_KEY) || "",
  user: null,
  shops: [],
  selectedShopId: 0,
  planPrefixOptions: [
    { prefix: "SC", ownerName: "Operator A", label: "SC Operator A" },
    { prefix: "CY", ownerName: "Operator B", label: "CY Operator B" },
    { prefix: "ST", ownerName: "Operator C", label: "ST Operator C" },
  ],
  plans: [],
  totalPlans: 0,
  dashboard: null,
  report: null,
  operationBoard: null,
  rules: [],
  groups: [],
  users: [],
  logs: [],
  activeStatus: "all",
  activePlanType: "all",
  activeProductStatus: "all",
  planSortKey: "spend",
  planSortDir: "desc",
  productSortKey: "spend",
  productSortDir: "desc",
  planPage: 1,
  planPageSize: 50,
  planLoadRequestId: 0,
  apiStatusText: "",
  activeRuleId: "",
  activeGroupId: "",
  trashGroupFilter: "all",
  ruleWorkspaceMode: "library",
  activeView: "dashboard",
};

const els = {
  loginView: document.querySelector("#loginView"),
  appShell: document.querySelector("#appShell"),
  loginForm: document.querySelector("#loginForm"),
  loginUsername: document.querySelector("#loginUsername"),
  loginPassword: document.querySelector("#loginPassword"),
  loginHint: document.querySelector("#loginHint"),
  userRoleText: document.querySelector("#userRoleText"),
  currentUserName: document.querySelector("#currentUserName"),
  currentShopName: document.querySelector("#currentShopName"),
  currentShopMeta: document.querySelector("#currentShopMeta"),
  shopAvatar: document.querySelector("#shopAvatar"),
  shopSelect: document.querySelector("#shopSelect"),
  apiStatus: document.querySelector("#apiStatus"),
  planPoolCount: document.querySelector("#planPoolCount"),
  topbarSub: document.querySelector("#topbarSub"),
  runRulesBtn: document.querySelector("#runRulesBtn"),
  metricSpend: document.querySelector("#metricSpend"),
  metricRoi: document.querySelector("#metricRoi"),
  metricGmv: document.querySelector("#metricGmv"),
  metricShops: document.querySelector("#metricShops"),
  pendingActionCount: document.querySelector("#pendingActionCount"),
  shopRoiRows: document.querySelector("#shopRoiRows"),
  accountRoiRows: document.querySelector("#accountRoiRows"),
  reportStartDate: document.querySelector("#reportStartDate"),
  reportEndDate: document.querySelector("#reportEndDate"),
  loadReportBtn: document.querySelector("#loadReportBtn"),
  reportSpend: document.querySelector("#reportSpend"),
  reportRoi: document.querySelector("#reportRoi"),
  reportGmv: document.querySelector("#reportGmv"),
  reportPlanCount: document.querySelector("#reportPlanCount"),
  reportRangeText: document.querySelector("#reportRangeText"),
  reportShopRows: document.querySelector("#reportShopRows"),
  reportPlanRows: document.querySelector("#reportPlanRows"),
  reportPlanSearch: document.querySelector("#reportPlanSearch"),
  shopRows: document.querySelector("#shopRows"),
  shopForm: document.querySelector("#shopForm"),
  shopFormOriginalId: document.querySelector("#shopFormOriginalId"),
  shopFormName: document.querySelector("#shopFormName"),
  shopFormShopId: document.querySelector("#shopFormShopId"),
  shopFormAdvertiserId: document.querySelector("#shopFormAdvertiserId"),
  shopFormStatus: document.querySelector("#shopFormStatus"),
  planPanelSub: document.querySelector("#planPanelSub"),
  planRows: document.querySelector("#planRows"),
  planSearch: document.querySelector("#planSearch"),
  planPageInfo: document.querySelector("#planPageInfo"),
  planPagination: document.querySelector("#planPagination"),
  productPanelSub: document.querySelector("#productPanelSub"),
  productRows: document.querySelector("#productRows"),
  productSearch: document.querySelector("#productSearch"),
  operationPauseTotal: document.querySelector("#operationPauseTotal"),
  operationPendingTotal: document.querySelector("#operationPendingTotal"),
  operationRestoredTotal: document.querySelector("#operationRestoredTotal"),
  operationBudgetResetStatus: document.querySelector("#operationBudgetResetStatus"),
  operationBudgetResetSub: document.querySelector("#operationBudgetResetSub"),
  operationPanelSub: document.querySelector("#operationPanelSub"),
  refreshOperationsBtn: document.querySelector("#refreshOperationsBtn"),
  operationRows: document.querySelector("#operationRows"),
  groupList: document.querySelector("#groupList"),
  groupForm: document.querySelector("#groupForm"),
  groupId: document.querySelector("#groupId"),
  groupName: document.querySelector("#groupName"),
  groupDescription: document.querySelector("#groupDescription"),
  ruleView: document.querySelector("#view-rules"),
  ruleList: document.querySelector("#ruleList"),
  rulePanelTitle: document.querySelector("#rulePanelTitle"),
  rulePanelSub: document.querySelector("#rulePanelSub"),
  ruleActiveCount: document.querySelector("#ruleActiveCount"),
  ruleDeletedCount: document.querySelector("#ruleDeletedCount"),
  ruleTotalCount: document.querySelector("#ruleTotalCount"),
  goTrashBtn: document.querySelector("#goTrashBtn"),
  trashTotalCount: document.querySelector("#trashTotalCount"),
  trashRiskCount: document.querySelector("#trashRiskCount"),
  trashScaleCount: document.querySelector("#trashScaleCount"),
  trashWatchCount: document.querySelector("#trashWatchCount"),
  trashRows: document.querySelector("#trashRows"),
  ruleForm: document.querySelector("#ruleForm"),
  ruleName: document.querySelector("#ruleName"),
  ruleGroup: document.querySelector("#ruleGroup"),
  ruleShopScope: document.querySelector("#ruleShopScope"),
  rulePlanTypeScope: document.querySelector("#rulePlanTypeScope"),
  ruleAction: document.querySelector("#ruleAction"),
  ruleEnabled: document.querySelector("#ruleEnabled"),
  ruleAfterMinutes: document.querySelector("#ruleAfterMinutes"),
  ruleMinSpend: document.querySelector("#ruleMinSpend"),
  ruleHourlySpendAbove: document.querySelector("#ruleHourlySpendAbove"),
  ruleSpendStep: document.querySelector("#ruleSpendStep"),
  ruleDelayMinutes: document.querySelector("#ruleDelayMinutes"),
  ruleRoiBelow: document.querySelector("#ruleRoiBelow"),
  ruleRoiAbove: document.querySelector("#ruleRoiAbove"),
  ruleBudgetRemainingPercent: document.querySelector("#ruleBudgetRemainingPercent"),
  ruleRoiGoalIncrement: document.querySelector("#ruleRoiGoalIncrement"),
  ruleMaxRoiGoal: document.querySelector("#ruleMaxRoiGoal"),
  ruleHoldMinutes: document.querySelector("#ruleHoldMinutes"),
  ruleCooldown: document.querySelector("#ruleCooldown"),
  ruleBudgetMode: document.querySelector("#ruleBudgetMode"),
  ruleBudgetValue: document.querySelector("#ruleBudgetValue"),
  ruleDailyCap: document.querySelector("#ruleDailyCap"),
  ruleNotify: document.querySelector("#ruleNotify"),
  deleteRuleBtn: document.querySelector("#deleteRuleBtn"),
  userRows: document.querySelector("#userRows"),
  userForm: document.querySelector("#userForm"),
  userFormId: document.querySelector("#userFormId"),
  userFormUsername: document.querySelector("#userFormUsername"),
  userFormDisplayName: document.querySelector("#userFormDisplayName"),
  userFormPassword: document.querySelector("#userFormPassword"),
  userFormRole: document.querySelector("#userFormRole"),
  userFormStatus: document.querySelector("#userFormStatus"),
  userShopChecks: document.querySelector("#userShopChecks"),
  logList: document.querySelector("#logList"),
  toast: document.querySelector("#toast"),
};

function isAdmin() {
  return state.user?.role === "admin";
}

function selectedShop() {
  return state.shops.find((shop) => Number(shop.shopId) === Number(state.selectedShopId)) || state.shops[0] || null;
}

function normalizePlanPrefix(value) {
  const prefix = String(value || "").trim().toUpperCase().slice(0, 2);
  return /^[A-Z]{2}$/.test(prefix) ? prefix : "";
}

function normalizePlanSmartBidType(value) {
  const raw = String(value || "").trim();
  const upper = raw.toUpperCase();
  if (PLAN_SMART_BID_TYPES.includes(upper)) return upper;
  if (["CUSTOM", "COST", "COST_CONTROL", "控成本"].includes(upper) || raw === "控成本") return "SMART_BID_CUSTOM";
  if (["CONSERVATIVE", "VOLUME", "VOLUME_SCALE", "放量"].includes(upper) || raw === "放量") return "SMART_BID_CONSERVATIVE";
  return "";
}

function normalizePlanSmartBidTypes(values, fallback = CONTROL_PLAN_SMART_BID_TYPES) {
  const source = Array.isArray(values) ? values : values ? String(values).split(/[，,]/) : [];
  const normalized = [];
  for (const value of source) {
    const text = String(value || "").trim();
    const items = text.toLowerCase() === "all" ? PLAN_SMART_BID_TYPES : [normalizePlanSmartBidType(text)].filter(Boolean);
    for (const item of items) {
      if (!normalized.includes(item)) normalized.push(item);
    }
  }
  return normalized.length ? normalized : [...fallback];
}

function planTypeLabel(value) {
  return PLAN_SMART_BID_LABELS[normalizePlanSmartBidType(value)] || "未知";
}

function rulePlanSmartBidTypes(rule) {
  return normalizePlanSmartBidTypes(rule?.planSmartBidTypes, CONTROL_PLAN_SMART_BID_TYPES);
}

function ruleAppliesToPlanType(rule, plan) {
  return rulePlanSmartBidTypes(rule).includes(normalizePlanSmartBidType(plan.smartBidType) || "SMART_BID_CUSTOM");
}

function planPrefixLabel(prefix) {
  const normalized = normalizePlanPrefix(prefix);
  const option = state.planPrefixOptions.find((item) => item.prefix === normalized);
  return option?.label || (normalized ? `${normalized} 未绑定` : "未分配");
}

function planPrefixForName(name) {
  const raw = String(name || "").trim().toUpperCase();
  const letters = [];
  for (const ch of raw) {
    if (ch >= "A" && ch <= "Z") {
      letters.push(ch);
      if (letters.length === 2) return normalizePlanPrefix(letters.join(""));
    } else if (letters.length) {
      break;
    } else if (![" ", "_", "-", "【", "】", "[", "]", "(", ")", "（", "）"].includes(ch)) {
      break;
    }
  }
  return "";
}

function userPrefixLabels(user) {
  return (user?.planPrefixes || []).map(planPrefixLabel).join("、");
}

function applyMeta(data = {}) {
  if (Array.isArray(data.shops)) state.shops = data.shops;
  if (Array.isArray(data.planPrefixOptions)) state.planPrefixOptions = data.planPrefixOptions;
}

function ensureActiveRuleSelection() {
  if (state.activeGroupId && !state.groups.some((group) => group.id === state.activeGroupId)) {
    state.activeGroupId = "";
  }
  state.activeGroupId = state.activeGroupId || state.groups[0]?.id || "";
  const activeRuleRows = activeRules();
  const scopedRules = state.activeGroupId ? rulesInGroup(state.activeGroupId) : activeRuleRows;
  if (state.activeRuleId && !activeRuleRows.some((rule) => rule.id === state.activeRuleId)) {
    state.activeRuleId = "";
  }
  if (state.activeRuleId && scopedRules.some((rule) => rule.id === state.activeRuleId)) {
    return;
  }
  state.activeRuleId = scopedRules[0]?.id || activeRuleRows[0]?.id || "";
}

function setRuleWorkspaceMode(mode) {
  state.ruleWorkspaceMode = mode === "editor" ? "editor" : "library";
  renderRuleWorkspaceMode();
}

function renderRuleWorkspaceMode() {
  if (!els.ruleView) return;
  const isEditor = state.ruleWorkspaceMode === "editor";
  els.ruleView.dataset.mode = isEditor ? "editor" : "library";
  document.querySelectorAll(".rule-mode-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.ruleMode === state.ruleWorkspaceMode);
  });
  if (els.rulePanelTitle) els.rulePanelTitle.textContent = isEditor ? "编辑规则" : "当前分类规则";
  if (els.rulePanelSub) {
    els.rulePanelSub.textContent = isEditor ? "只展示当前规则的配置项，保存后直接参与真实执行。" : "顶部显示全量规则数，列表只显示当前选中分类。";
  }
}

function knownPlanPrefixOptions() {
  const rows = new Map();
  for (const option of state.planPrefixOptions || []) {
    const prefix = normalizePlanPrefix(option.prefix);
    if (prefix) rows.set(prefix, { prefix, ownerName: option.ownerName || "未绑定", label: option.label || `${prefix} ${option.ownerName || "未绑定"}` });
  }
  for (const user of state.users || []) {
    for (const prefix of user.planPrefixes || []) {
      const normalized = normalizePlanPrefix(prefix);
      if (!normalized) continue;
      const ownerName = user.role === "admin" ? rows.get(normalized)?.ownerName || "未绑定" : user.displayName || user.username;
      rows.set(normalized, { prefix: normalized, ownerName, label: `${normalized} ${ownerName}` });
    }
  }
  for (const plan of [...(state.dashboard?.plans || []), ...(state.plans || []), ...(state.report?.plans || [])]) {
    const prefix = normalizePlanPrefix(plan.ownerPrefix) || planPrefixForName(plan.name);
    if (!prefix || rows.has(prefix)) continue;
    rows.set(prefix, { prefix, ownerName: "未绑定", label: `${prefix} 未绑定` });
  }
  return Array.from(rows.values()).sort((a, b) => a.prefix.localeCompare(b.prefix));
}

function headersFor(options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  if (state.sessionToken) {
    headers.Authorization = `Bearer ${state.sessionToken}`;
  }
  return headers;
}

async function apiFetch(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: headersFor(options),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || data.message || `HTTP ${response.status}`);
  }
  return data;
}

function hasCacheMeta(data) {
  return Boolean(data?._cache?.source);
}

function cacheStatusText(items) {
  const cached = items.filter(hasCacheMeta);
  if (!cached.length) return "已连接";
  return cached.some((item) => item._cache?.refreshing) ? "本地缓存刷新中" : "本地缓存";
}

function dashboardHasData(dashboard) {
  const global = dashboard?.global || {};
  return Boolean(
    Number(global.spend || 0) > 0 ||
      Number(global.gmv || 0) > 0 ||
      Number(global.planCount || global.totalPlans || 0) > 0 ||
      (Array.isArray(dashboard?.plans) && dashboard.plans.length),
  );
}

function snapshotStatusText(label, data) {
  const savedAt = data?.savedAt ? new Date(data.savedAt) : null;
  const timeText = savedAt && !Number.isNaN(savedAt.getTime()) ? savedAt.toLocaleString("zh-CN", { hour12: false }) : "";
  const suffix = data?._cache?.refreshing ? "，后台刷新中" : "";
  return `${label}${timeText ? ` ${timeText}` : ""}${suffix}`;
}

function yuan(value) {
  const num = Number(value || 0);
  return num.toLocaleString("zh-CN", {
    minimumFractionDigits: num % 1 === 0 ? 0 : 1,
    maximumFractionDigits: 1,
  });
}

function nowText() {
  return new Date().toLocaleTimeString("zh-CN", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function dateTimeText(value) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("zh-CN", { hour12: false });
}

function shortDateTimeText(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function dateInputValue(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function minutesText(minutes) {
  const value = Number(minutes || 0);
  if (value < 60) return `${value} 分钟`;
  const hours = Math.floor(value / 60);
  const remain = value % 60;
  return remain ? `${hours} 小时 ${remain} 分` : `${hours} 小时`;
}

function pageTotal(pageInfo, fallback = 0) {
  if (!pageInfo || typeof pageInfo !== "object") return fallback;
  return Number(pageInfo.total_num || pageInfo.total_number || pageInfo.total_count || pageInfo.total || fallback || 0);
}

function normalizeReport(report) {
  const shopNames = new Map((report?.shops || []).map((shop) => [Number(shop.shopId), shop.shopName]));
  const applyOwner = (plan) => {
    if (!plan || typeof plan !== "object") return;
    const prefix = normalizePlanPrefix(plan.ownerPrefix) || planPrefixForName(plan.name);
    plan.ownerPrefix = prefix;
    plan.ownerName = plan.ownerName || planPrefixLabel(prefix).replace(/^[A-Z]{2}\s*/, "");
    plan.smartBidType = normalizePlanSmartBidType(plan.smartBidType) || "SMART_BID_CUSTOM";
    plan.smartBidLabel = planTypeLabel(plan.smartBidType);
  };
  for (const shop of report?.shops || []) {
    for (const plan of shop.plans || []) {
      plan.shopId = shop.shopId;
      plan.shopName = shop.shopName;
      applyOwner(plan);
    }
  }
  for (const plan of report?.plans || []) {
    if (!plan.shopName && plan.shopId) plan.shopName = shopNames.get(Number(plan.shopId)) || "";
    applyOwner(plan);
  }
  return report;
}

async function fetchAllPlanPages(firstResult, pageSize = 500) {
  const firstPlans = Array.isArray(firstResult?.plans) ? firstResult.plans : [];
  const total = pageTotal(firstResult?.page_info, firstPlans.length);
  const totalPages = Math.min(20, Math.ceil(total / pageSize));
  if (totalPages <= 1) {
    return { total, plans: firstPlans };
  }
  const requests = [];
  for (let page = 2; page <= totalPages; page += 1) {
    requests.push(apiFetch(`/api/qianchuan/plans?page=${page}&page_size=${pageSize}`));
  }
  const pages = await Promise.all(requests);
  return {
    total,
    plans: firstPlans.concat(pages.flatMap((item) => (Array.isArray(item?.plans) ? item.plans : []))),
  };
}

function roleText(role) {
  if (role === "admin") return "管理员";
  if (role === "operator") return "投手";
  return "只读";
}

function isOperatorAccount(user) {
  return user && user.role !== "admin";
}

function statusText(status) {
  return status === "active" ? "启用" : "停用";
}

function normalizeApiPlan(plan) {
  const createdAt = plan.createTime ? new Date(String(plan.createTime).replace(" ", "T")) : null;
  const elapsedMinutes =
    createdAt && !Number.isNaN(createdAt.getTime())
      ? Math.max(0, Math.round((Date.now() - createdAt.getTime()) / 60000))
      : Number(plan.elapsedMinutes || 0);
  return {
    id: Number(plan.id),
    name: plan.name || `计划 ${plan.id}`,
    product: plan.product || "未返回商品名",
    anchor: plan.anchor || "未返回主播",
    image: plan.image || fallbackImage,
    optStatus: plan.optStatus || "UNKNOWN",
    status: plan.status || "",
    elapsedMinutes,
    spend: Number(plan.spend || 0),
    gmv: Number(plan.gmv || 0),
    payGmv: Number(plan.payGmv || 0),
    payRoi: Number(plan.payRoi || 0),
    settleGmv: Number(plan.settleGmv || plan.gmv || 0),
    settleRoi: Number(plan.settleRoi || plan.roi || 0),
    realSettleGmv: Number(plan.realSettleGmv || 0),
    refundGmv: Number(plan.refundGmv || 0),
    refundOrders: Number(plan.refundOrders || 0),
    roiMetric: plan.roiMetric || {},
    orders: Number(plan.orders || 0),
    roi: Number(plan.roi || 0),
    budget: Number(plan.budget || 0),
    roiGoal: Number(plan.roiGoal || 0),
    shopId: Number(plan.shopId || 0),
    shopName: plan.shopName || "",
    advertiserId: Number(plan.advertiserId || plan.advertiser_id || DEFAULT_ADVERTISER_ID),
    smartBidType: normalizePlanSmartBidType(plan.smartBidType || plan.smart_bid_type) || "SMART_BID_CUSTOM",
    smartBidLabel: plan.smartBidLabel || planTypeLabel(plan.smartBidType || plan.smart_bid_type),
    ownerPrefix: normalizePlanPrefix(plan.ownerPrefix) || planPrefixForName(plan.name),
    ownerName: plan.ownerName || planPrefixLabel(plan.ownerPrefix || planPrefixForName(plan.name)).replace(/^[A-Z]{2}\s*/, ""),
    lastChange: plan.modifyTime || plan.createTime || "",
  };
}

function normalizeLogEntry(log) {
  if (!log || typeof log !== "object") return { time: nowText(), title: "记录", text: "", type: "neutral" };
  if (log.time || log.title || log.text) {
    return {
      time: log.time || nowText(),
      title: log.title || "记录",
      text: log.text || "",
      type: log.type || "neutral",
    };
  }
  return {
    time: String(log.created_at || "").slice(11, 19) || nowText(),
    title: `后端动作 · ${log.action || "记录"}`,
    text: log.response?.message || log.response?.code || "已记录",
    type: log.response?.code === 0 ? "ok" : "neutral",
  };
}

function normalizeOperationBoard(board) {
  if (!board || typeof board !== "object") {
    return { ok: false, date: dateInputValue(), autoPause: { total: 0, pending: 0, restored: 0, records: [] }, budgetReset: { runs: [], latest: null } };
  }
  const autoPause = board.autoPause && typeof board.autoPause === "object" ? board.autoPause : {};
  const budgetReset = board.budgetReset && typeof board.budgetReset === "object" ? board.budgetReset : {};
  const records = Array.isArray(autoPause.records) ? autoPause.records : [];
  const runs = Array.isArray(budgetReset.runs) ? budgetReset.runs : [];
  return {
    ...board,
    date: board.date || dateInputValue(),
    autoPause: {
      total: Number(autoPause.total || records.length),
      pending: Number(autoPause.pending || records.filter((item) => item.status !== "restored").length),
      restored: Number(autoPause.restored || records.filter((item) => item.status === "restored").length),
      records,
    },
    budgetReset: {
      ...budgetReset,
      runs,
      latest: budgetReset.latest || runs[0] || null,
    },
  };
}

function applyStartupSnapshot(data, label = "本地快照") {
  if (!data || typeof data !== "object") return false;
  if (data.user) state.user = data.user;
  applyMeta(data);
  if (data.dashboard && typeof data.dashboard === "object") state.dashboard = data.dashboard;
  if (Array.isArray(data.rules) && (data.rules.length || !state.rules.length)) state.rules = data.rules;
  if (Array.isArray(data.groups) && (data.groups.length || !state.groups.length)) state.groups = data.groups;
  if (Array.isArray(data.users)) state.users = data.users;
  if (Array.isArray(data.logs)) state.logs = data.logs.slice(0, 100).map(normalizeLogEntry);
  if (data.operationBoard && typeof data.operationBoard === "object") state.operationBoard = normalizeOperationBoard(data.operationBoard);
  if (data.report && typeof data.report === "object") state.report = normalizeReport(data.report);
  if (data.activeView) state.activeView = data.activeView;
  const plans = Array.isArray(data.plans) ? data.plans : Array.isArray(data.dashboard?.plans) ? data.dashboard.plans : [];
  if (plans.length) {
    state.plans = plans.map(normalizeApiPlan);
    state.planPage = 1;
  }
  state.totalPlans = pageTotal(data.page_info, Number(data.totalPlans || state.plans.length));
  ensureActiveRuleSelection();
  if (!state.selectedShopId && state.shops.length) state.selectedShopId = state.shops[0].shopId;
  state.apiStatusText = snapshotStatusText(label, data);
  if (state.user) showApp();
  renderAll();
  return true;
}

function saveBrowserStartupSnapshot() {
  if (!state.sessionToken || !state.user) return;
  const payload = {
    ok: true,
    source: "browser-startup-snapshot",
    savedAt: new Date().toISOString(),
    sessionToken: state.sessionToken,
    user: state.user,
    shops: state.shops,
    planPrefixOptions: state.planPrefixOptions,
    dashboard: state.dashboard,
    plans: state.plans.slice(0, 2000),
    totalPlans: state.totalPlans || state.plans.length,
    rules: state.rules,
    groups: state.groups,
    users: state.users,
    operationBoard: state.operationBoard,
    logs: state.logs.slice(0, 100),
    report: state.report,
    activeView: state.activeView,
  };
  try {
    window.localStorage.setItem(SNAPSHOT_KEY, JSON.stringify(payload));
  } catch (error) {
    // 浏览器空间不足时只影响首屏快照，不影响真实接口刷新。
  }
}

function restoreBrowserStartupSnapshot() {
  if (!state.sessionToken) return false;
  try {
    const raw = window.localStorage.getItem(SNAPSHOT_KEY);
    if (!raw) return false;
    const payload = JSON.parse(raw);
    if (payload?.sessionToken !== state.sessionToken) return false;
    if (!payload.user || (!payload.dashboard && !Array.isArray(payload.plans))) return false;
    return applyStartupSnapshot(payload, "浏览器快照");
  } catch (error) {
    window.localStorage.removeItem(SNAPSHOT_KEY);
    return false;
  }
}

async function loadLocalStartupSnapshot() {
  if (!state.sessionToken) return false;
  try {
    const snapshot = await apiFetch("/api/local/startup-snapshot");
    const applied = applyStartupSnapshot(snapshot, "本地快照");
    if (applied) saveBrowserStartupSnapshot();
    return applied;
  } catch (error) {
    return false;
  }
}

async function refreshConfigData() {
  if (!state.sessionToken || !state.user) return false;
  const [rulesResult, groupsResult, usersResult] = await Promise.allSettled([
    apiFetch("/api/qianchuan/rules"),
    apiFetch("/api/rule-groups"),
    isAdmin() ? apiFetch("/api/admin/users") : Promise.resolve(null),
  ]);
  let changed = false;
  if (rulesResult.status === "fulfilled" && Array.isArray(rulesResult.value.rules)) {
    state.rules = rulesResult.value.rules;
    changed = true;
  }
  if (groupsResult.status === "fulfilled" && Array.isArray(groupsResult.value.groups)) {
    state.groups = groupsResult.value.groups;
    changed = true;
  }
  if (usersResult.status === "fulfilled" && Array.isArray(usersResult.value?.users)) {
    state.users = usersResult.value.users;
    changed = true;
  }
  if (!changed) return false;
  ensureActiveRuleSelection();
  renderGroups();
  renderRules();
  renderTrash();
  renderUsers();
  saveBrowserStartupSnapshot();
  state.apiStatusText = "配置已刷新";
  renderShell();
  return true;
}

function addLog(title, text, type = "neutral") {
  state.logs.unshift({ time: nowText(), title, text, type });
  state.logs = state.logs.slice(0, 100);
  renderLogs();
}

function toast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => els.toast.classList.remove("show"), 2200);
}

function stopOperationBoardAutoRefresh() {
  if (!operationBoardRefreshTimer) return;
  window.clearInterval(operationBoardRefreshTimer);
  operationBoardRefreshTimer = 0;
}

function startOperationBoardAutoRefresh() {
  if (operationBoardRefreshTimer || state.activeView !== "operations" || !state.user) return;
  loadOperationBoard({ silent: true }).catch(() => {});
  operationBoardRefreshTimer = window.setInterval(() => {
    if (state.activeView !== "operations" || !state.user) {
      stopOperationBoardAutoRefresh();
      return;
    }
    loadOperationBoard({ silent: true }).catch(() => {});
  }, OPERATION_BOARD_REFRESH_MS);
}

function syncOperationBoardAutoRefresh() {
  if (state.activeView === "operations" && state.user) {
    startOperationBoardAutoRefresh();
  } else {
    stopOperationBoardAutoRefresh();
  }
}

function showApp() {
  els.loginView.classList.add("hidden");
  els.appShell.classList.remove("hidden");
  document.body.classList.toggle("is-admin", isAdmin());
  document.body.classList.toggle("is-operator", state.user?.role === "operator");
  syncOperationBoardAutoRefresh();
}

function showLogin(message = "") {
  stopOperationBoardAutoRefresh();
  els.appShell.classList.add("hidden");
  els.loginView.classList.remove("hidden");
  document.body.classList.remove("is-admin", "is-operator");
  if (message) els.loginHint.textContent = message;
}

async function bootstrapSession() {
  if (state.sessionToken) {
    try {
      const me = await apiFetch("/api/me");
      state.user = me.user;
      applyMeta(me);
      return true;
    } catch (error) {
      window.localStorage.removeItem(SESSION_KEY);
      window.localStorage.removeItem(SNAPSHOT_KEY);
      state.sessionToken = "";
    }
  }
  return false;
}

async function login(username, password) {
  const data = await apiFetch("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  state.sessionToken = data.token;
  window.localStorage.setItem(SESSION_KEY, data.token);
  state.user = data.user;
  applyMeta(data);
}

async function logout() {
  try {
    await apiFetch("/api/auth/logout", { method: "POST", body: "{}" });
  } catch (error) {
    // Local logout should still clear the browser session.
  }
  state.sessionToken = "";
  state.user = null;
  window.localStorage.removeItem(SESSION_KEY);
  window.localStorage.removeItem(SNAPSHOT_KEY);
  showLogin("已退出，可以重新登录。");
}

function viewById(view) {
  return document.querySelector(`#view-${view}`);
}

function switchView(view) {
  if (["users", "trash"].includes(view) && !isAdmin()) view = "dashboard";
  state.activeView = view;
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  document.querySelectorAll(".view").forEach((section) => section.classList.remove("active"));
  viewById(view)?.classList.add("active");
  saveBrowserStartupSnapshot();
  syncOperationBoardAutoRefresh();
}

function renderShell() {
  const prefixes = state.user?.role === "admin" ? state.planPrefixOptions.map((item) => item.prefix) : state.user?.planPrefixes || [];
  const prefixText = prefixes.length ? prefixes.map(planPrefixLabel).join("、") : "未绑定计划";
  els.userRoleText.textContent = roleText(state.user?.role);
  els.currentUserName.textContent = state.user?.displayName || state.user?.username || "-";
  els.currentShopName.textContent = state.user?.role === "admin" ? "全部投手计划" : prefixText;
  els.currentShopMeta.textContent = state.user?.role === "admin" ? "SC / CY / ST" : "按计划名前缀授权";
  els.shopAvatar.textContent = (state.user?.displayName || "千").slice(0, 1);
  els.topbarSub.textContent = `${prefixText} · ${state.apiStatusText || "真实 API"}`;
  els.apiStatus.textContent = state.user ? state.apiStatusText || "已连接" : "未登录";
  els.planPoolCount.textContent = String(state.totalPlans || state.plans.length);
  els.runRulesBtn.disabled = !["admin", "operator"].includes(state.user?.role);
  renderShopSelect();
  if (window.lucide) window.lucide.createIcons();
}

function renderShopSelect() {
  els.shopSelect.classList.add("hidden");
  els.shopSelect.innerHTML = state.shops
    .map((shop) => `<option value="${shop.shopId}">${shop.shopName}</option>`)
    .join("");
  if (state.selectedShopId) els.shopSelect.value = String(state.selectedShopId);
}

function renderMetrics() {
  const summary = state.dashboard?.global;
  const spend = summary ? Number(summary.spend || 0) : state.plans.reduce((sum, plan) => sum + plan.spend, 0);
  const gmv = summary ? Number(summary.gmv || 0) : state.plans.reduce((sum, plan) => sum + plan.gmv, 0);
  const roi = summary ? Number(summary.roi || 0) : spend > 0 ? gmv / spend : 0;
  els.metricSpend.textContent = `￥${yuan(spend)}`;
  els.metricGmv.textContent = `￥${yuan(gmv)}`;
  els.metricRoi.textContent = roi.toFixed(2);
  els.metricShops.textContent = String(summary?.planCount ?? state.plans.length);
  els.pendingActionCount.textContent = String(state.plans.reduce((sum, plan) => sum + evaluatePlan(plan).length, 0));
}

function renderDashboardTables() {
  const plans = state.dashboard?.plans || state.plans || [];
  els.shopRoiRows.innerHTML =
    plans.slice(0, 30)
      .map(
        (plan) => `
          <tr>
            <td><strong>${plan.ownerName || planPrefixLabel(plan.ownerPrefix)}</strong><div class="plan-sub">${plan.name || plan.id}</div></td>
            <td><span class="roi ${Number(plan.roi || 0) >= 2 ? "good" : Number(plan.roi || 0) === 0 ? "bad" : ""}">${Number(plan.roi || 0).toFixed(2)}</span><div class="plan-sub">支付 ${Number(plan.payRoi || 0).toFixed(2)}</div></td>
            <td class="money">￥${yuan(plan.spend)}</td>
            <td class="money">￥${yuan(plan.gmv)}</td>
            <td>${plan.orders || 0}</td>
            <td>${plan.ownerPrefix || "-"}<div class="plan-sub">${plan.ownerName || planPrefixLabel(plan.ownerPrefix)}</div></td>
          </tr>
        `,
      )
      .join("") || `<tr><td colspan="6">当前权限范围没有计划数据。</td></tr>`;

  const users = (state.dashboard?.users || []).filter(isOperatorAccount);
  els.accountRoiRows.innerHTML =
    users
      .map(
        (user) => `
          <tr>
            <td><strong>${user.displayName || user.username}</strong><div class="plan-sub">${user.username}</div></td>
            <td>${roleText(user.role)}</td>
            <td>${(user.planPrefixes || []).join("、") || "-"}</td>
            <td><span class="roi ${Number(user.roi || 0) >= 2 ? "good" : Number(user.roi || 0) === 0 ? "bad" : ""}">${Number(user.roi || 0).toFixed(2)}</span><div class="plan-sub">支付 ${Number(user.payRoi || 0).toFixed(2)}</div></td>
            <td class="money">￥${yuan(user.spend)}</td>
            <td class="money">￥${yuan(user.gmv)}</td>
            <td>${user.planCount || 0}</td>
          </tr>
        `,
      )
      .join("") || `<tr><td colspan="7">还没有子账号绑定计划。</td></tr>`;
}

function renderReport() {
  const report = state.report;
  const summary = report?.global || {};
  const ranges = report?.range || {};
  const shopNames = new Map((report?.shops || []).map((shop) => [Number(shop.shopId), shop.shopName]));
  els.reportSpend.textContent = `￥${yuan(summary.spend)}`;
  els.reportGmv.textContent = `￥${yuan(summary.gmv)}`;
  els.reportRoi.textContent = Number(summary.roi || 0).toFixed(2);
  els.reportPlanCount.textContent = String(summary.planCount || report?.plans?.length || 0);
  const cacheText = report?._cache?.source
    ? ` · 本地缓存${report._cache.source === "local-daily-report" ? "汇总" : ""}${report._cache.refreshing ? " · 后台刷新中" : ""}`
    : "";
  els.reportRangeText.textContent =
    ranges.startTime && ranges.endTime ? `${ranges.startTime.slice(0, 10)} 至 ${ranges.endTime.slice(0, 10)}${cacheText}` : "等待查询";

  const users =
    report?.users?.length
      ? report.users
      : Object.values(
          (report?.plans || []).reduce((map, plan) => {
            const key = plan.ownerPrefix || "-";
            const current = map[key] || {
              displayName: plan.ownerName || planPrefixLabel(key),
              username: key,
              roi: 0,
              spend: 0,
              gmv: 0,
              payGmv: 0,
              payRoi: 0,
              settleGmv: 0,
              settleRoi: 0,
              refundGmv: 0,
              refundOrders: 0,
              orders: 0,
              planCount: 0,
            };
            current.spend += Number(plan.spend || 0);
            current.gmv += Number(plan.gmv || 0);
            current.payGmv += Number(plan.payGmv || 0);
            current.settleGmv += Number(plan.settleGmv || plan.gmv || 0);
            current.refundGmv += Number(plan.refundGmv || 0);
            current.refundOrders += Number(plan.refundOrders || 0);
            current.orders += Number(plan.orders || 0);
            current.planCount += 1;
            current.roi = current.spend > 0 ? current.gmv / current.spend : 0;
            current.payRoi = current.spend > 0 ? current.payGmv / current.spend : 0;
            current.settleRoi = current.spend > 0 ? current.settleGmv / current.spend : 0;
            map[key] = current;
            return map;
          }, {}),
        );
  els.reportShopRows.innerHTML =
    users
      .map(
        (user) => `
          <tr>
            <td><strong>${user.displayName || user.username}</strong><div class="plan-sub">${(user.planPrefixes || [user.username]).join("、")}</div></td>
            <td><span class="roi ${Number(user.roi || 0) >= 2 ? "good" : Number(user.roi || 0) === 0 ? "bad" : ""}">${Number(user.roi || 0).toFixed(2)}</span><div class="plan-sub">支付 ${Number(user.payRoi || 0).toFixed(2)}</div></td>
            <td class="money">￥${yuan(user.spend)}</td>
            <td class="money">￥${yuan(user.gmv)}</td>
            <td>${user.orders || 0}</td>
            <td>${user.planCount || 0}</td>
          </tr>
        `,
      )
      .join("") || `<tr><td colspan="6">请选择时间后查询报表。</td></tr>`;

  const keyword = els.reportPlanSearch.value.trim().toLowerCase();
  const plans = (report?.plans || []).filter((plan) => {
    const text = `${plan.ownerName || ""} ${plan.ownerPrefix || ""} ${plan.shopName || ""} ${plan.name || ""} ${plan.product || ""} ${plan.anchor || ""}`.toLowerCase();
    return !keyword || text.includes(keyword);
  });
  els.reportPlanRows.innerHTML =
    plans
      .map(
        (plan) => `
          <tr>
            <td>${plan.ownerName || planPrefixLabel(plan.ownerPrefix)}<div class="plan-sub">${plan.ownerPrefix || "-"}</div></td>
            <td><strong>${plan.name || plan.id}</strong><div class="plan-sub">${plan.product || ""}</div></td>
            <td>${statusPill(plan)}</td>
            <td class="money">￥${yuan(plan.spend)}</td>
            <td><span class="roi ${Number(plan.roi || 0) >= 2 ? "good" : Number(plan.roi || 0) === 0 ? "bad" : ""}">${Number(plan.roi || 0).toFixed(2)}</span><div class="plan-sub">支付 ${Number(plan.payRoi || 0).toFixed(2)}</div></td>
            <td class="money">￥${yuan(plan.gmv)}<div class="plan-sub">支付 ￥${yuan(plan.payGmv || 0)}</div></td>
            <td>${plan.orders || 0}</td>
            <td class="money">￥${yuan(plan.budget)}</td>
          </tr>
        `,
      )
      .join("") || `<tr><td colspan="8">没有计划明细。</td></tr>`;
}

function renderShopRows() {
  const plans = [...(state.dashboard?.plans || []), ...(state.plans || [])];
  const seenPlans = new Set();
  const counts = plans.reduce((map, plan) => {
    const prefix = normalizePlanPrefix(plan.ownerPrefix) || planPrefixForName(plan.name);
    if (!prefix) return map;
    const key = `${prefix}:${plan.shopId || ""}:${plan.id || plan.name || ""}`;
    if (seenPlans.has(key)) return map;
    seenPlans.add(key);
    map.set(prefix, (map.get(prefix) || 0) + 1);
    return map;
  }, new Map());
  const rows = knownPlanPrefixOptions()
    .map((item) => {
      const assignee = prefixAssignee(item.prefix);
      return { ...item, assignee, count: counts.get(item.prefix) || 0 };
    })
    .sort((a, b) => {
      if (Boolean(a.assignee) !== Boolean(b.assignee)) return a.assignee ? 1 : -1;
      if (b.count !== a.count) return b.count - a.count;
      return a.prefix.localeCompare(b.prefix);
    });
  els.shopRows.innerHTML =
    rows
      .map(
        (item) => `
          <tr>
            <td><strong>${item.prefix}</strong></td>
            <td>${item.count}<div class="plan-sub">计划名前两个字母</div></td>
            <td>${item.assignee ? item.assignee.displayName || item.assignee.username : "未绑定"}</td>
            <td><span class="status-pill ${item.assignee ? "on" : "pause"}">${item.assignee ? "已绑定" : "待绑定"}</span></td>
            <td class="admin-only">
              <select class="mini-select" data-prefix-select="${item.prefix}">
                <option value="">选择投手</option>
                ${bindingUserOptions(item.assignee?.id)}
              </select>
            </td>
            <td class="admin-only">
              <button class="mini-btn" data-action="bind-prefix" data-prefix="${item.prefix}">${item.assignee ? "改绑定" : "绑定"}</button>
            </td>
          </tr>
        `,
      )
      .join("") || `<tr><td colspan="6">暂无计划归属。</td></tr>`;
}

function prefixAssignee(prefix) {
  const normalized = normalizePlanPrefix(prefix);
  return (state.users || []).find(
    (user) =>
      user.role !== "admin" &&
      user.status === "active" &&
      (user.planPrefixes || []).map(normalizePlanPrefix).includes(normalized),
  );
}

function bindingUserOptions(selectedUserId = 0) {
  return (state.users || [])
    .filter((user) => user.role !== "admin" && user.status === "active")
    .map(
      (user) =>
        `<option value="${user.id}" ${Number(user.id) === Number(selectedUserId) ? "selected" : ""}>${user.displayName || user.username}</option>`,
    )
    .join("");
}

function renderGroups() {
  els.groupList.innerHTML =
    state.groups
      .map((group) => {
        const groupRules = rulesInGroup(group.id);
        const deletedCount = trashedRules().filter((rule) => (rule.groupId || "watch-notify") === group.id).length;
        const enabledCount = groupRules.filter((rule) => rule.enabled).length;
        return `
          <button class="rule-card ${group.id === state.activeGroupId ? "active" : ""}" data-group-id="${group.id}">
            <span>
              <span class="rule-card-title">${group.name}</span>
              <small>${group.description || "没有说明"}</small>
            </span>
            <span class="rule-card-metas">
              <span class="mode-pill ${enabledCount ? "enabled" : "disabled"}">启用 ${enabledCount}/${groupRules.length}</span>
              <small>规则 ${groupRules.length} 条${deletedCount ? ` · 回收站 ${deletedCount}` : ""}</small>
            </span>
          </button>
        `;
      })
      .join("") || `<div class="empty-state">暂无规则分组。</div>`;
  renderRuleGroupOptions();
  loadGroupForm();
}

function renderRuleGroupOptions() {
  els.ruleGroup.innerHTML = state.groups.map((group) => `<option value="${group.id}">${group.name}</option>`).join("");
  renderRuleScopeOptions();
}

function renderRuleScopeOptions() {
  const options = [`<option value="all">全部计划</option>`].concat(
    knownPlanPrefixOptions().map((item) => `<option value="${item.prefix}">${item.label}</option>`),
  );
  els.ruleShopScope.innerHTML = options.join("");
}

function ruleIsDeleted(rule) {
  return Boolean(rule?.deletedAt);
}

function activeRules() {
  return state.rules.filter((rule) => !ruleIsDeleted(rule));
}

function trashedRules() {
  return state.rules.filter(ruleIsDeleted);
}

function rulesInGroup(groupId) {
  return activeRules().filter((rule) => (rule.groupId || "watch-notify") === groupId);
}

function activeRule() {
  return activeRules().find((rule) => rule.id === state.activeRuleId) || activeRules()[0] || null;
}

function activeGroup() {
  return state.groups.find((group) => group.id === state.activeGroupId) || state.groups[0] || null;
}

function isBudgetIncreaseAction(action) {
  return action === "ADD_BUDGET" || action === NEAR_BUDGET_ACTION;
}

function isRoiGoalAction(action) {
  return action === HOURLY_ROI_GOAL_ACTION;
}

function planBudgetRemainingPercent(plan) {
  const budget = Number(plan?.budget || 0);
  if (budget <= 0) return 100;
  const spend = Math.max(0, Number(plan?.spend || 0));
  return (Math.max(0, budget - spend) / budget) * 100;
}

function planHourlySpend(plan) {
  const elapsed = Number(plan?.elapsedMinutes || 0);
  if (elapsed <= 0) return 0;
  return Number(plan?.spend || 0) / (elapsed / 60);
}

function ruleDetail(rule) {
  const typeText = rulePlanSmartBidTypes(rule).map(planTypeLabel).join(" / ");
  const suffix = ` · ${typeText}`;
  if (rule.action === "SPEND_STEP_ROI_STOP") {
    return `每消耗 ${yuan(rule.spendStep || rule.minSpend)} 元，${Number(rule.delayMinutes ?? 10)} 分钟后净成交ROI < ${rule.roiBelow}，暂停${suffix}`;
  }
  if (rule.action === NEAR_BUDGET_ACTION) {
    return `剩余日预算 ≤ ${Number(rule.budgetRemainingPercent || 0)}%，净成交ROI > ${rule.roiAbove}，加 ${yuan(rule.budgetValue)} 元${suffix}`;
  }
  if (rule.action === HOURLY_ROI_GOAL_ACTION) {
    return `每小时消耗 > ${yuan(rule.hourlySpendAbove)} 元，目标ROI +${Number(rule.roiGoalIncrement || 0)}，最高 ${Number(rule.maxRoiGoal || 2.4)}${suffix}`;
  }
  if (rule.action === "ADD_BUDGET") {
    return `净成交ROI > ${rule.roiAbove}，${rule.budgetMode === "percent" ? `加 ${rule.budgetValue}%` : `加 ${rule.budgetValue} 元`}${suffix}`;
  }
  if (rule.action === "DISABLE") {
    return `净成交ROI < ${rule.roiBelow}，消耗 ≥ ${rule.minSpend}${suffix}`;
  }
  return `净成交ROI < ${rule.roiBelow}，通知负责人${suffix}`;
}

function ruleActionText(action) {
  const labels = {
    DISABLE: "暂停计划",
    ADD_BUDGET: "增加预算",
    NOTIFY: "通知投手",
    SPEND_STEP_ROI_STOP: "每消耗 X 后看 ROI",
    [NEAR_BUDGET_ACTION]: "预算快用完继续加",
    [HOURLY_ROI_GOAL_ACTION]: "小时消耗高提目标",
  };
  return labels[action] || action || "-";
}

function ruleGroupKey(rule) {
  const groupId = rule?.groupId || "watch-notify";
  if (["risk-stop", "scale-budget", "watch-notify"].includes(groupId)) return groupId;
  return "watch-notify";
}

function evaluatePlan(plan) {
  const hits = [];
  for (const rule of activeRules()) {
    if (!rule.enabled) continue;
    if (!ruleAppliesToPlanType(rule, plan)) continue;
    const prefixes = Array.isArray(rule.planPrefixes) ? rule.planPrefixes.map(normalizePlanPrefix).filter(Boolean) : [];
    if (prefixes.length && !prefixes.includes(normalizePlanPrefix(plan.ownerPrefix))) continue;
    if (rule.action === "SPEND_STEP_ROI_STOP") continue;
    if (rule.action === NEAR_BUDGET_ACTION) {
      const remainingPercent = planBudgetRemainingPercent(plan);
      const threshold = Number(rule.budgetRemainingPercent || 0);
      if (threshold > 0 && remainingPercent <= threshold && Number(rule.roiAbove || 0) > 0 && plan.roi > Number(rule.roiAbove)) {
        hits.push({
          rule,
          reason: `剩余日预算 ${remainingPercent.toFixed(1)}%，净成交ROI ${plan.roi.toFixed(2)}`,
        });
      }
      continue;
    }
    if (rule.action === HOURLY_ROI_GOAL_ACTION) {
      const hourlySpend = planHourlySpend(plan);
      const maxGoal = Number(rule.maxRoiGoal || 2.4);
      if (
        Number(rule.hourlySpendAbove || 0) > 0 &&
        hourlySpend > Number(rule.hourlySpendAbove) &&
        Number(plan.roiGoal || 0) > 0 &&
        Number(plan.roiGoal || 0) < maxGoal
      ) {
        hits.push({
          rule,
          reason: `每小时消耗 ${yuan(hourlySpend)} 元，目标ROI ${Number(plan.roiGoal || 0).toFixed(2)}`,
        });
      }
      continue;
    }
    if (plan.elapsedMinutes < Number(rule.afterMinutes || 0)) continue;
    if (plan.spend < Number(rule.minSpend || 0)) continue;
    if (Number(rule.roiBelow || 0) > 0 && plan.roi < Number(rule.roiBelow)) {
      hits.push({ rule, reason: `净成交ROI ${plan.roi.toFixed(2)} 低于 ${rule.roiBelow}` });
    }
    if (Number(rule.roiAbove || 0) > 0 && plan.roi > Number(rule.roiAbove)) {
      hits.push({ rule, reason: `净成交ROI ${plan.roi.toFixed(2)} 高于 ${rule.roiAbove}` });
    }
  }
  return hits;
}

function statusPill(plan) {
  if (plan.optStatus === "ENABLE") return `<span class="status-pill on">投放中</span>`;
  if (plan.optStatus === "PAUSED") return `<span class="status-pill pause">已暂停</span>`;
  if (plan.optStatus === "DISABLE") return `<span class="status-pill pause">已暂停</span>`;
  return `<span class="status-pill stop">非投放</span>`;
}

function productNameForPlan(plan) {
  return String(plan?.product || "未返回商品名").trim() || "未返回商品名";
}

function productGroups() {
  const groups = new Map();
  for (const plan of state.plans) {
    const product = productNameForPlan(plan);
    const group = groups.get(product) || {
      product,
      image: plan.image || fallbackImage,
      ownerPrefixes: new Set(),
      ownerNames: new Set(),
      planCount: 0,
      runningCount: 0,
      pausedCount: 0,
      otherCount: 0,
      spend: 0,
      gmv: 0,
      budget: 0,
      orders: 0,
      plans: [],
    };
    group.ownerPrefixes.add(plan.ownerPrefix || "");
    group.ownerNames.add(plan.ownerName || planPrefixLabel(plan.ownerPrefix));
    group.planCount += 1;
    group.runningCount += plan.optStatus === "ENABLE" ? 1 : 0;
    group.pausedCount += ["PAUSED", "DISABLE"].includes(plan.optStatus) ? 1 : 0;
    group.otherCount += !["ENABLE", "PAUSED", "DISABLE"].includes(plan.optStatus) ? 1 : 0;
    group.spend += Number(plan.spend || 0);
    group.gmv += Number(plan.gmv || 0);
    group.budget += Number(plan.budget || 0);
    group.orders += Number(plan.orders || 0);
    group.plans.push(plan);
    groups.set(product, group);
  }
  return Array.from(groups.values()).map((group) => ({
    ...group,
    roi: group.spend > 0 ? group.gmv / group.spend : 0,
    ownerPrefixes: Array.from(group.ownerPrefixes).filter(Boolean),
    ownerNames: Array.from(group.ownerNames).filter(Boolean),
    allPaused: group.planCount > 0 && group.runningCount === 0 && group.pausedCount === group.planCount,
  }));
}

function filteredProducts() {
  const keyword = els.productSearch?.value.trim().toLowerCase() || "";
  const rows = productGroups().filter((group) => {
    const statusOk =
      state.activeProductStatus === "all" ||
      (state.activeProductStatus === "running" && group.runningCount > 0) ||
      (state.activeProductStatus === "paused" && group.allPaused);
    const text = `${group.product} ${group.ownerNames.join(" ")} ${group.ownerPrefixes.join(" ")} ${group.plans
      .map((plan) => `${plan.name} ${plan.anchor}`)
      .join(" ")}`.toLowerCase();
    return statusOk && (!keyword || text.includes(keyword));
  });
  const dir = state.productSortDir === "asc" ? 1 : -1;
  return rows.sort((a, b) => {
    const av = Number(a[state.productSortKey] || 0);
    const bv = Number(b[state.productSortKey] || 0);
    if (av === bv) return a.product.localeCompare(b.product, "zh-CN");
    return av > bv ? dir : -dir;
  });
}

function renderProductSortHeaders() {
  document.querySelectorAll("[data-product-sort-icon]").forEach((span) => {
    const key = span.dataset.productSortIcon;
    span.textContent = state.productSortKey === key ? (state.productSortDir === "asc" ? "↑" : "↓") : "";
  });
  document.querySelectorAll(".product-sort-th").forEach((button) => {
    button.classList.toggle("active", button.dataset.productSortKey === state.productSortKey);
  });
}

function renderProducts() {
  if (!els.productRows) return;
  renderProductSortHeaders();
  const rows = filteredProducts();
  els.productRows.innerHTML =
    rows
      .map((group) => {
        const roiClass = group.roi >= 2.2 ? "good" : group.roi < 1.2 && group.spend >= 120 ? "bad" : "";
        const status = group.allPaused
          ? `<span class="status-pill pause">已全停</span>`
          : group.runningCount > 0
            ? `<span class="status-pill on">投放中</span>`
            : `<span class="status-pill stop">非投放</span>`;
        const names = group.ownerNames.join("、") || "未分配";
        const plans = group.plans
          .slice()
          .sort((a, b) => Number(b.spend || 0) - Number(a.spend || 0))
          .slice(0, 2)
          .map((plan) => plan.name)
          .join(" / ");
        return `
          <tr>
            <td class="plan-cell">
              <div class="plan-title-line">
                <img class="product-thumb" src="${group.image}" alt="${group.product}">
                <div>
                  <div class="plan-name" title="${group.product}">${group.product}</div>
                  <div class="plan-sub" title="${plans}">${plans || "暂无计划名"}</div>
                </div>
              </div>
            </td>
            <td>${names}<div class="plan-sub">${group.ownerPrefixes.join(" / ") || "-"}</div></td>
            <td>${group.planCount}</td>
            <td>${group.runningCount}</td>
            <td class="money">￥${yuan(group.spend)}</td>
            <td><span class="roi ${roiClass}">${group.roi.toFixed(2)}</span><div class="plan-sub">订单 ${group.orders}</div></td>
            <td class="money">￥${yuan(group.budget)}</td>
            <td>${status}</td>
            <td><button class="mini-btn" data-action="view-product-plans" data-product-name="${encodeURIComponent(group.product)}">看计划</button></td>
          </tr>
        `;
      })
      .join("") || `<tr><td colspan="9">当前筛选下没有商品。</td></tr>`;
  const allCount = productGroups().length;
  const fullPausedCount = productGroups().filter((group) => group.allPaused).length;
  els.productPanelSub.textContent = `商品 ${allCount} 个 · 当前筛选 ${rows.length} 个 · 已全停 ${fullPausedCount} 个`;
}

function filteredPlans() {
  const query = els.planSearch.value.trim().toLowerCase();
  const plans = state.plans.filter((plan) => {
    const statusOk =
      state.activeStatus === "all" ||
      plan.optStatus === state.activeStatus ||
      (state.activeStatus === "PAUSED" && plan.optStatus === "DISABLE");
    const typeOk = state.activePlanType === "all" || normalizePlanSmartBidType(plan.smartBidType) === state.activePlanType;
    const text = `${plan.name} ${plan.product} ${plan.anchor}`.toLowerCase();
    return statusOk && typeOk && (!query || text.includes(query));
  });
  if (!state.planSortKey) return plans;
  const dir = state.planSortDir === "asc" ? 1 : -1;
  return [...plans].sort((a, b) => {
    const av = Number(a[state.planSortKey] || 0);
    const bv = Number(b[state.planSortKey] || 0);
    if (av === bv) return 0;
    return av > bv ? dir : -dir;
  });
}

function renderSortHeaders() {
  document.querySelectorAll("[data-sort-icon]").forEach((span) => {
    const key = span.dataset.sortIcon;
    span.textContent = state.planSortKey === key ? (state.planSortDir === "asc" ? "↑" : "↓") : "";
  });
  document.querySelectorAll(".sort-th").forEach((button) => {
    button.classList.toggle("active", button.dataset.sortKey === state.planSortKey);
  });
}

function clampPlanPage(totalPages) {
  state.planPage = Math.min(Math.max(1, state.planPage), Math.max(1, totalPages));
}

function renderPlanPagination(totalRows, totalPages) {
  if (!els.planPagination || !els.planPageInfo) return;
  clampPlanPage(totalPages);
  const start = totalRows ? (state.planPage - 1) * state.planPageSize + 1 : 0;
  const end = Math.min(totalRows, state.planPage * state.planPageSize);
  els.planPageInfo.textContent = `第 ${start}-${end} 条 / 共 ${totalRows} 条`;

  const pageButtons = [];
  const firstPage = Math.max(1, state.planPage - 2);
  const lastPage = Math.min(totalPages, state.planPage + 2);
  if (firstPage > 1) {
    pageButtons.push(`<button class="page-btn" data-page="1">1</button>`);
    if (firstPage > 2) pageButtons.push(`<span class="page-ellipsis">...</span>`);
  }
  for (let page = firstPage; page <= lastPage; page += 1) {
    pageButtons.push(
      `<button class="page-btn ${page === state.planPage ? "active" : ""}" data-page="${page}">${page}</button>`,
    );
  }
  if (lastPage < totalPages) {
    if (lastPage < totalPages - 1) pageButtons.push(`<span class="page-ellipsis">...</span>`);
    pageButtons.push(`<button class="page-btn" data-page="${totalPages}">${totalPages}</button>`);
  }

  els.planPagination.innerHTML = `
    <button class="page-btn" data-page="${state.planPage - 1}" ${state.planPage <= 1 ? "disabled" : ""}>上一页</button>
    ${pageButtons.join("")}
    <button class="page-btn" data-page="${state.planPage + 1}" ${state.planPage >= totalPages ? "disabled" : ""}>下一页</button>
  `;
}

function renderPlans() {
  renderSortHeaders();
  const allPlans = filteredPlans();
  const totalPages = Math.max(1, Math.ceil(allPlans.length / state.planPageSize));
  clampPlanPage(totalPages);
  renderPlanPagination(allPlans.length, totalPages);
  const pagePlans = allPlans.slice((state.planPage - 1) * state.planPageSize, state.planPage * state.planPageSize);
  const rows = pagePlans
    .map((plan) => {
      const firstHit = evaluatePlan(plan)[0];
      const hitHtml = firstHit
        ? `<span class="rule-hit ${isBudgetIncreaseAction(firstHit.rule.action) ? "ok" : "danger"}">${firstHit.rule.name}</span>`
        : `<span class="rule-hit neutral">未命中</span>`;
      const roiClass = plan.roi >= 2.2 ? "good" : plan.roi < 1.2 && plan.spend >= 120 ? "bad" : "";
      return `
        <tr>
          <td class="plan-cell">
            <div class="plan-title-line">
              <img class="product-thumb" src="${plan.image}" alt="${plan.product}">
              <div>
                <div class="plan-name" title="${plan.name}">${plan.name}</div>
                <div class="plan-sub" title="${plan.product}">${plan.ownerName || planPrefixLabel(plan.ownerPrefix)} · ${plan.product} · ${plan.anchor}</div>
              </div>
            </div>
          </td>
          <td><span class="type-pill ${plan.smartBidType === "SMART_BID_CONSERVATIVE" ? "volume" : "control"}">${planTypeLabel(plan.smartBidType)}</span></td>
          <td>${statusPill(plan)}</td>
          <td>${minutesText(plan.elapsedMinutes)}</td>
          <td class="money">￥${yuan(plan.spend)}</td>
          <td><span class="roi ${roiClass}">${plan.roi.toFixed(2)}</span><div class="plan-sub">支付 ${plan.payRoi.toFixed(2)} · 目标 ${plan.roiGoal}</div></td>
          <td class="money">￥${yuan(plan.budget)}</td>
          <td>${hitHtml}</td>
          <td>
            <div class="row-actions">
              ${
                plan.optStatus === "ENABLE"
                  ? `<button class="mini-btn" data-action="pause-plan" data-plan-id="${plan.id}">暂停</button>`
                  : `<button class="mini-btn" data-action="start-plan" data-plan-id="${plan.id}">启动</button>`
              }
              <button class="mini-btn" data-action="raise-budget" data-plan-id="${plan.id}">加预算</button>
              <button class="mini-btn" data-action="lower-budget" data-plan-id="${plan.id}">减预算</button>
            </div>
          </td>
        </tr>
      `;
    })
    .join("");
  els.planRows.innerHTML = rows || `<tr><td colspan="9">当前筛选下没有计划。</td></tr>`;
  const customCount = state.plans.filter((plan) => normalizePlanSmartBidType(plan.smartBidType) === "SMART_BID_CUSTOM").length;
  const volumeCount = state.plans.filter((plan) => normalizePlanSmartBidType(plan.smartBidType) === "SMART_BID_CONSERVATIVE").length;
  els.planPanelSub.textContent = `API 返回总数 ${state.totalPlans} · 当前筛选 ${allPlans.length} 条 · 控成本 ${customCount} · 放量 ${volumeCount}`;
  renderMetrics();
}

function renderRules() {
  const groupId = state.activeGroupId || activeGroup()?.id;
  const rules = groupId ? rulesInGroup(groupId) : activeRules();
  renderRuleWorkspaceMode();
  if (els.ruleActiveCount) els.ruleActiveCount.textContent = String(activeRules().length);
  if (els.ruleDeletedCount) els.ruleDeletedCount.textContent = String(trashedRules().length);
  if (els.ruleTotalCount) els.ruleTotalCount.textContent = String(state.rules.length);
  els.ruleList.innerHTML =
    rules
      .map((rule) => {
        const detail = ruleDetail(rule);
        return `
          <button class="rule-card ${rule.id === state.activeRuleId ? "active" : ""}" data-rule-id="${rule.id}">
            <span>
              <span class="rule-card-title">${rule.name}</span>
              <small>${detail}</small>
            </span>
            <span class="mode-pill ${rule.enabled ? "enabled" : "disabled"}">${rule.enabled ? "启用" : "停用"}</span>
          </button>
        `;
      })
      .join("") || `<div class="empty-state">这个分组下还没有规则。</div>`;
  if (!rules.find((rule) => rule.id === state.activeRuleId)) state.activeRuleId = rules[0]?.id || activeRules()[0]?.id || "";
  loadRuleForm();
  renderMetrics();
}

function renderTrash() {
  if (!els.trashRows) return;
  const rows = trashedRules().slice().sort((a, b) => new Date(b.deletedAt || 0) - new Date(a.deletedAt || 0));
  const visibleRows = state.trashGroupFilter === "all" ? rows : rows.filter((rule) => ruleGroupKey(rule) === state.trashGroupFilter);
  const counts = rows.reduce(
    (acc, rule) => {
      acc.all += 1;
      acc[ruleGroupKey(rule)] += 1;
      return acc;
    },
    { all: 0, "risk-stop": 0, "scale-budget": 0, "watch-notify": 0 },
  );
  if (els.trashTotalCount) els.trashTotalCount.textContent = String(counts.all);
  if (els.trashRiskCount) els.trashRiskCount.textContent = String(counts["risk-stop"]);
  if (els.trashScaleCount) els.trashScaleCount.textContent = String(counts["scale-budget"]);
  if (els.trashWatchCount) els.trashWatchCount.textContent = String(counts["watch-notify"]);
  document.querySelectorAll(".trash-filter").forEach((button) => {
    button.classList.toggle("active", button.dataset.trashGroup === state.trashGroupFilter);
  });
  els.trashRows.innerHTML =
    visibleRows
      .map((rule) => {
        const group = state.groups.find((item) => item.id === rule.groupId);
        const createdAt = rule.createdAt || rule.updatedAt || "";
        return `
          <tr>
            <td>
              <strong>${rule.name || "未命名规则"}</strong>
              <div class="plan-sub">${ruleDetail(rule)}</div>
            </td>
            <td>${group?.name || "未分组"}</td>
            <td>${ruleActionText(rule.action)}</td>
            <td><span class="status-pill ${rule.deletedWasEnabled ? "on" : "pause"}">${rule.deletedWasEnabled ? "启用" : "停用"}</span></td>
            <td>${dateTimeText(createdAt)}</td>
            <td>${dateTimeText(rule.deletedAt)}</td>
            <td>${rule.deletedBy || "-"}</td>
            <td><button class="mini-btn" data-action="restore-rule" data-rule-id="${rule.id}">恢复</button></td>
          </tr>
        `;
      })
      .join("") || `<tr><td colspan="8">当前分类没有已删除规则。</td></tr>`;
}

function loadGroupForm() {
  const group = activeGroup();
  if (!group) return;
  els.groupId.value = group.id;
  els.groupName.value = group.name || "";
  els.groupDescription.value = group.description || "";
}

function loadRuleForm() {
  const rule = activeRule();
  if (!rule) {
    els.deleteRuleBtn.disabled = true;
    return;
  }
  els.deleteRuleBtn.disabled = false;
  els.ruleName.value = rule.name || "";
  els.ruleGroup.value = rule.groupId || state.activeGroupId || state.groups[0]?.id || "";
  const prefixes = Array.isArray(rule.planPrefixes) ? rule.planPrefixes.map(normalizePlanPrefix).filter(Boolean) : [];
  els.ruleShopScope.value = prefixes[0] || "all";
  const smartBidTypes = rulePlanSmartBidTypes(rule);
  els.rulePlanTypeScope.value = smartBidTypes.length === PLAN_SMART_BID_TYPES.length ? "all" : smartBidTypes[0] || "SMART_BID_CUSTOM";
  els.ruleAction.value = rule.action || "NOTIFY";
  els.ruleEnabled.value = String(Boolean(rule.enabled));
  els.ruleAfterMinutes.value = Number(rule.afterMinutes || 0);
  els.ruleMinSpend.value = Number(rule.minSpend || 0);
  els.ruleHourlySpendAbove.value = Number(rule.hourlySpendAbove || 0);
  els.ruleSpendStep.value = Number(rule.spendStep || rule.minSpend || 100);
  els.ruleDelayMinutes.value = Number(rule.delayMinutes ?? 10);
  els.ruleRoiBelow.value = Number(rule.roiBelow || 0);
  els.ruleRoiAbove.value = Number(rule.roiAbove || 0);
  els.ruleBudgetRemainingPercent.value = Number(rule.budgetRemainingPercent || 0);
  els.ruleRoiGoalIncrement.value = Number(rule.roiGoalIncrement || 0);
  els.ruleMaxRoiGoal.value = Number(rule.maxRoiGoal || 0);
  els.ruleHoldMinutes.value = Number(rule.holdMinutes || 0);
  els.ruleCooldown.value = Number(rule.cooldown || 0);
  els.ruleBudgetMode.value = rule.budgetMode || "fixed";
  els.ruleBudgetValue.value = Number(rule.budgetValue || 0);
  els.ruleDailyCap.value = Number(rule.dailyCap || 0);
  els.ruleNotify.value = rule.notify || "wechat";
  syncRuleFieldState();
}

function setRuleControlDisabled(control, disabled) {
  if (!control) return;
  control.disabled = Boolean(disabled);
  const label = control.closest("label");
  if (label) label.classList.toggle("disabled-field", Boolean(disabled));
}

function readRuleMetricFields() {
  return {
    action: els.ruleAction.value,
    afterMinutes: Number(els.ruleAfterMinutes.value || 0),
    minSpend: Number(els.ruleMinSpend.value || 0),
    hourlySpendAbove: Number(els.ruleHourlySpendAbove.value || 0),
    spendStep: Number(els.ruleSpendStep.value || 0),
    delayMinutes: Number(els.ruleDelayMinutes.value || 0),
    roiBelow: Number(els.ruleRoiBelow.value || 0),
    roiAbove: Number(els.ruleRoiAbove.value || 0),
    budgetRemainingPercent: Number(els.ruleBudgetRemainingPercent.value || 0),
    roiGoalIncrement: Number(els.ruleRoiGoalIncrement.value || 0),
    maxRoiGoal: Number(els.ruleMaxRoiGoal.value || 0),
    holdMinutes: Number(els.ruleHoldMinutes.value || 0),
    cooldown: Number(els.ruleCooldown.value || 0),
    budgetMode: els.ruleBudgetMode.value,
    budgetValue: Number(els.ruleBudgetValue.value || 0),
    dailyCap: Number(els.ruleDailyCap.value || 0),
  };
}

function writeRuleMetricFields(values) {
  els.ruleAfterMinutes.value = Number(values.afterMinutes || 0);
  els.ruleMinSpend.value = Number(values.minSpend || 0);
  els.ruleHourlySpendAbove.value = Number(values.hourlySpendAbove || 0);
  els.ruleSpendStep.value = Number(values.spendStep || 0);
  els.ruleDelayMinutes.value = Number(values.delayMinutes || 0);
  els.ruleRoiBelow.value = Number(values.roiBelow || 0);
  els.ruleRoiAbove.value = Number(values.roiAbove || 0);
  els.ruleBudgetRemainingPercent.value = Number(values.budgetRemainingPercent || 0);
  els.ruleRoiGoalIncrement.value = Number(values.roiGoalIncrement || 0);
  els.ruleMaxRoiGoal.value = Number(values.maxRoiGoal || 0);
  els.ruleHoldMinutes.value = Number(values.holdMinutes || 0);
  els.ruleCooldown.value = Number(values.cooldown || 0);
  els.ruleBudgetMode.value = values.budgetMode || "fixed";
  els.ruleBudgetValue.value = Number(values.budgetValue || 0);
  els.ruleDailyCap.value = Number(values.dailyCap || 0);
}

function syncRuleFieldState() {
  const action = els.ruleAction.value;
  const isStepRule = action === "SPEND_STEP_ROI_STOP";
  const isNearBudgetRule = action === NEAR_BUDGET_ACTION;
  const isHourlyRoiGoalRule = action === HOURLY_ROI_GOAL_ACTION;
  const isAddBudgetRule = action === "ADD_BUDGET";
  writeRuleMetricFields(ruleFormLogic.normalizeRuleFormValues(readRuleMetricFields()));
  setRuleControlDisabled(els.ruleSpendStep, !isStepRule);
  setRuleControlDisabled(els.ruleDelayMinutes, !isStepRule);
  setRuleControlDisabled(els.ruleBudgetRemainingPercent, !isNearBudgetRule);
  setRuleControlDisabled(els.ruleHourlySpendAbove, !isHourlyRoiGoalRule);
  setRuleControlDisabled(els.ruleRoiGoalIncrement, !isHourlyRoiGoalRule);
  setRuleControlDisabled(els.ruleMaxRoiGoal, !isHourlyRoiGoalRule);
  setRuleControlDisabled(els.ruleAfterMinutes, isNearBudgetRule || isStepRule || isHourlyRoiGoalRule);
  setRuleControlDisabled(els.ruleMinSpend, isNearBudgetRule || isStepRule || isHourlyRoiGoalRule);
  setRuleControlDisabled(els.ruleRoiBelow, isNearBudgetRule || isHourlyRoiGoalRule || isAddBudgetRule);
  setRuleControlDisabled(els.ruleRoiAbove, !(isNearBudgetRule || isAddBudgetRule));
  setRuleControlDisabled(els.ruleHoldMinutes, true);
  setRuleControlDisabled(els.ruleCooldown, true);
  setRuleControlDisabled(els.ruleDailyCap, true);
  setRuleControlDisabled(els.ruleBudgetMode, !isAddBudgetRule);
  setRuleControlDisabled(els.ruleBudgetValue, !(isNearBudgetRule || isAddBudgetRule));
}

function collectRuleForm() {
  const selectedPrefix = normalizePlanPrefix(els.ruleShopScope.value);
  const selectedPlanType = normalizePlanSmartBidType(els.rulePlanTypeScope.value);
  const action = els.ruleAction.value;
  const metricValues = ruleFormLogic.normalizeRuleFormValues(readRuleMetricFields());
  return {
    name: els.ruleName.value.trim() || "未命名规则",
    groupId: els.ruleGroup.value || state.groups[0]?.id || "watch-notify",
    shopIds: [],
    planPrefixes: selectedPrefix ? [selectedPrefix] : [],
    planSmartBidTypes: selectedPlanType ? [selectedPlanType] : [...PLAN_SMART_BID_TYPES],
    action,
    enabled: els.ruleEnabled.value === "true",
    afterMinutes: metricValues.afterMinutes,
    minSpend: metricValues.minSpend,
    hourlySpendAbove: metricValues.hourlySpendAbove,
    spendStep: metricValues.spendStep,
    delayMinutes: metricValues.delayMinutes,
    roiBelow: metricValues.roiBelow,
    roiAbove: metricValues.roiAbove,
    budgetRemainingPercent: metricValues.budgetRemainingPercent,
    roiGoalIncrement: metricValues.roiGoalIncrement,
    maxRoiGoal: metricValues.maxRoiGoal,
    holdMinutes: metricValues.holdMinutes,
    cooldown: metricValues.cooldown,
    budgetMode: metricValues.budgetMode,
    budgetValue: metricValues.budgetValue,
    dailyCap: metricValues.dailyCap,
    notify: els.ruleNotify.value,
  };
}

async function saveRuleForm() {
  const rule = activeRule();
  if (!rule) return;
  if (!rule.createdAt) rule.createdAt = new Date().toISOString();
  rule.updatedAt = new Date().toISOString();
  Object.assign(rule, collectRuleForm());
  await persistRules();
  addLog("规则已保存", `${rule.name} 已同步到后端。`, "ok");
  renderAll();
  toast("规则已保存");
}

async function persistRules() {
  await apiFetch("/api/qianchuan/rules", {
    method: "POST",
    body: JSON.stringify({ rules: state.rules }),
  });
}

async function deleteActiveRule() {
  const rule = activeRule();
  if (!rule) return;
  if (!window.confirm(`把「${rule.name || "未命名规则"}」移入回收站？`)) return;
  if (!rule.createdAt) rule.createdAt = new Date().toISOString();
  rule.deletedAt = new Date().toISOString();
  rule.deletedBy = state.user?.displayName || state.user?.username || "";
  rule.deletedWasEnabled = Boolean(rule.enabled);
  rule.enabled = false;
  state.activeRuleId = "";
  state.ruleWorkspaceMode = "library";
  await persistRules();
  addLog("规则已移入回收站", `${rule.name || rule.id} 已停用，可在回收站恢复。`, "neutral");
  renderAll();
  toast("规则已移入回收站");
}

async function restoreRule(ruleId) {
  const rule = state.rules.find((item) => item.id === ruleId);
  if (!rule) return;
  rule.enabled = Boolean(rule.deletedWasEnabled);
  delete rule.deletedAt;
  delete rule.deletedBy;
  delete rule.deletedWasEnabled;
  rule.updatedAt = new Date().toISOString();
  state.activeGroupId = rule.groupId || state.groups[0]?.id || "";
  state.activeRuleId = rule.id;
  state.ruleWorkspaceMode = "editor";
  await persistRules();
  addLog("规则已恢复", `${rule.name || rule.id} 已回到规则列表。`, "ok");
  renderAll();
  toast("规则已恢复");
}

async function saveGroupForm() {
  const payload = {
    id: els.groupId.value || `group-${Date.now()}`,
    name: els.groupName.value.trim(),
    description: els.groupDescription.value.trim(),
  };
  const result = await apiFetch("/api/rule-groups", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.groups = result.groups || state.groups;
  state.activeGroupId = result.group?.id || payload.id;
  renderAll();
  toast("分组已保存");
}

function renderUsers() {
  els.userRows.innerHTML =
    state.users
      .map((user) => {
        const prefixNames = userPrefixLabels(user);
        return `
          <tr>
            <td><strong>${user.displayName || user.username}</strong><div class="plan-sub">${user.username}</div></td>
            <td>${roleText(user.role)}</td>
            <td>${prefixNames || (user.role === "admin" ? "全部计划" : "未绑定")}</td>
            <td><span class="status-pill ${user.status === "active" ? "on" : "pause"}">${statusText(user.status)}</span></td>
            <td>
              <div class="row-actions">
                <button class="mini-btn" data-action="edit-user" data-user-id="${user.id}">编辑</button>
                <button class="mini-btn danger-text" data-action="delete-user" data-user-id="${user.id}">删除</button>
              </div>
            </td>
          </tr>
        `;
      })
      .join("") || `<tr><td colspan="5">暂无子账号。</td></tr>`;
  renderUserShopChecks();
}

function renderUserShopChecks(selected = []) {
  const selectedSet = new Set(selected.map(normalizePlanPrefix).filter(Boolean));
  els.userShopChecks.innerHTML =
    state.planPrefixOptions
      .map(
        (item) => `
          <label class="check-line compact">
            <input type="checkbox" value="${item.prefix}" ${selectedSet.has(item.prefix) ? "checked" : ""}>
            <span>${item.label}</span>
          </label>
        `,
      )
      .join("") || `<div class="empty-state">还没有计划前缀。</div>`;
}

function clearUserForm() {
  els.userFormId.value = "";
  els.userFormUsername.value = "";
  els.userFormDisplayName.value = "";
  els.userFormPassword.value = "";
  els.userFormRole.value = "operator";
  els.userFormStatus.value = "active";
  renderUserShopChecks([]);
}

function editUser(userId) {
  const user = state.users.find((item) => Number(item.id) === Number(userId));
  if (!user) return;
  els.userFormId.value = user.id;
  els.userFormUsername.value = user.username;
  els.userFormDisplayName.value = user.displayName || "";
  els.userFormPassword.value = "";
  els.userFormRole.value = user.role;
  els.userFormStatus.value = user.status;
  renderUserShopChecks(user.planPrefixes || []);
}

async function saveUserForm() {
  const planPrefixes = Array.from(els.userShopChecks.querySelectorAll("input:checked"))
    .map((input) => normalizePlanPrefix(input.value))
    .filter(Boolean);
  const payload = {
    id: Number(els.userFormId.value || 0) || undefined,
    username: els.userFormUsername.value.trim(),
    displayName: els.userFormDisplayName.value.trim(),
    password: els.userFormPassword.value,
    role: els.userFormRole.value,
    status: els.userFormStatus.value,
    planPrefixes,
  };
  const result = await apiFetch("/api/admin/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.users = result.users || state.users;
  clearUserForm();
  renderUsers();
  toast("子账号已保存");
}

function clearShopForm() {
  els.shopFormOriginalId.value = "";
  els.shopFormName.value = "";
  els.shopFormShopId.value = "";
  els.shopFormAdvertiserId.value = "";
  els.shopFormStatus.value = "active";
}

function editShop(shopId) {
  const shop = state.shops.find((item) => Number(item.shopId) === Number(shopId));
  if (!shop) return;
  els.shopFormOriginalId.value = shop.shopId;
  els.shopFormName.value = shop.shopName;
  els.shopFormShopId.value = shop.shopId;
  els.shopFormAdvertiserId.value = shop.advertiserId;
  els.shopFormStatus.value = shop.status || "active";
}

async function saveShopForm() {
  const payload = {
    shopId: Number(els.shopFormShopId.value),
    shopName: els.shopFormName.value.trim(),
    advertiserId: Number(els.shopFormAdvertiserId.value),
    status: els.shopFormStatus.value,
  };
  const result = await apiFetch("/api/shops", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.shops = result.shops || state.shops;
  if (!state.selectedShopId) state.selectedShopId = payload.shopId;
  clearShopForm();
  renderAll();
  toast("来源账户已保存");
}

function renderLogs() {
  els.logList.innerHTML =
    state.logs
      .map(
        (log) => `
          <div class="log-item">
            <time>${log.time}</time>
            <div>
              <strong>${log.title}</strong>
              <span>${log.text}</span>
            </div>
            <span class="rule-hit ${log.type === "danger" ? "danger" : log.type === "ok" ? "ok" : "neutral"}">${log.type === "ok" ? "成功" : log.type === "danger" ? "失败" : "记录"}</span>
          </div>
        `,
      )
      .join("") || `<div class="empty-state">暂无日志。</div>`;
}

function renderOperations() {
  if (!els.operationRows) return;
  const board = normalizeOperationBoard(state.operationBoard);
  const autoPause = board.autoPause;
  const latestReset = board.budgetReset.latest;
  els.operationPauseTotal.textContent = String(autoPause.total || 0);
  els.operationPendingTotal.textContent = String(autoPause.pending || 0);
  els.operationRestoredTotal.textContent = String(autoPause.restored || 0);
  if (latestReset) {
    els.operationBudgetResetStatus.textContent = latestReset.ok ? "成功" : "失败";
    els.operationBudgetResetStatus.classList.toggle("danger-number", !latestReset.ok);
    els.operationBudgetResetSub.textContent = `归位 ${latestReset.updateCount || 0} 个，跳过 ${latestReset.skippedCount || 0} 个`;
  } else {
    els.operationBudgetResetStatus.textContent = "-";
    els.operationBudgetResetStatus.classList.remove("danger-number");
    els.operationBudgetResetSub.textContent = "等待记录";
  }
  const sourceText = board.source === "local-operation-board" ? "本地实时" : "操作记录";
  els.operationPanelSub.textContent = `${board.date || dateInputValue()} · ${sourceText} · 每15秒自动刷新 · 待恢复 ${autoPause.pending || 0} 个，已恢复 ${autoPause.restored || 0} 个`;
  const rows = [...(autoPause.records || [])].sort((a, b) => {
    if ((a.status === "pending") !== (b.status === "pending")) return a.status === "pending" ? -1 : 1;
    return String(b.pausedAt || "").localeCompare(String(a.pausedAt || ""));
  });
  els.operationRows.innerHTML =
    rows
      .map((item) => {
        const restored = item.status === "restored" || item.restored;
        const plan = state.plans.find((candidate) => Number(candidate.id) === Number(item.planId));
        const canStart = !restored && plan;
        return `
          <tr>
            <td>
              <strong>${item.planName || `计划 ${item.planId}`}</strong>
              <div class="muted-line">${item.product || "-"}</div>
            </td>
            <td>${item.ownerPrefix || "-"} ${item.ownerName || ""}</td>
            <td><span class="type-pill ${item.smartBidType === "SMART_BID_CONSERVATIVE" ? "volume" : "control"}">${item.smartBidLabel || planTypeLabel(item.smartBidType)}</span></td>
            <td>${item.ruleName || item.ruleAction || "自动止损"}</td>
            <td>${shortDateTimeText(item.pausedAt)}</td>
            <td><span class="status-pill ${restored ? "on" : "pause"}">${restored ? "已恢复" : "待恢复"}</span></td>
            <td>
              ${canStart ? `<button class="mini-btn" data-action="start-plan" data-plan-id="${item.planId}">启动</button>` : `<span class="muted-line">${restored ? shortDateTimeText(item.restoredAt) : "先刷新计划"}</span>`}
            </td>
          </tr>
        `;
      })
      .join("") || `<tr><td colspan="7"><div class="empty-state">今天还没有自动止损暂停记录。</div></td></tr>`;
}

async function loadBackendData() {
  state.planLoadRequestId += 1;
  const result = await apiFetch("/api/local/sync-now", {
    method: "POST",
    body: JSON.stringify({ source: "manual" }),
  });
  applyStartupSnapshot(result, "云端已更新");
  const sync = result.sync || {};
  addLog("云端同步完成", `成功 ${sync.successCount || 0}/${sync.totalCount || 0} 项，当前显示 ${state.plans.length}/${state.totalPlans || state.plans.length} 条计划。`, "ok");
  saveBrowserStartupSnapshot();
}

async function loadOperationBoard(options = {}) {
  if (operationBoardLoadPromise) return operationBoardLoadPromise;
  operationBoardLoadPromise = (async () => {
    const date = encodeURIComponent(dateInputValue());
    const data = await apiFetch(`/api/qianchuan/operation-board?date=${date}&fresh=1&_=${Date.now()}`);
    state.operationBoard = normalizeOperationBoard(data);
    renderOperations();
    saveBrowserStartupSnapshot();
    return state.operationBoard;
  })();
  try {
    return await operationBoardLoadPromise;
  } catch (error) {
    if (!options.silent) throw error;
    return state.operationBoard;
  } finally {
    operationBoardLoadPromise = null;
  }
}

async function refreshAll() {
  try {
    await loadBackendData();
    toast("云端已更新");
  } catch (error) {
    addLog("云端更新失败", error.message, "danger");
    toast("云端更新失败");
  }
}

async function loadReport() {
  const start = els.reportStartDate.value || dateInputValue();
  const end = els.reportEndDate.value || start;
  els.loadReportBtn.disabled = true;
  try {
    const report = normalizeReport(await apiFetch(`/api/local/reports/qianchuan?date_from=${encodeURIComponent(start)}&date_to=${encodeURIComponent(end)}&marketing_goal=VIDEO_PROM_GOODS`));
    state.report = report;
    renderReport();
    saveBrowserStartupSnapshot();
    if (report?._cache?.source) {
      addLog("本地报表已显示", `已读取 ${report.plans?.length || 0} 条本地计划明细，后台刷新中。`, "ok");
      toast("已显示本地报表");
    } else {
      addLog("报表同步完成", `已保存 ${report.plans?.length || 0} 条计划明细到本地。`, "ok");
      toast("报表已更新");
    }
  } catch (error) {
    addLog("报表加载失败", error.message, "danger");
    toast("报表加载失败");
  } finally {
    els.loadReportBtn.disabled = false;
  }
}

function planActionPayload(plan) {
  return {
    shopId: Number(plan.shopId || selectedShop()?.shopId || 0),
    advertiser_id: Number(plan.advertiserId || selectedShop()?.advertiserId || DEFAULT_ADVERTISER_ID),
    ad_id: Number(plan.id),
    planName: plan.name,
    ownerPrefix: plan.ownerPrefix,
    marketing_goal: "VIDEO_PROM_GOODS",
    smart_bid_type: normalizePlanSmartBidType(plan.smartBidType) || "SMART_BID_CUSTOM",
    smartBidType: normalizePlanSmartBidType(plan.smartBidType) || "SMART_BID_CUSTOM",
  };
}

async function runRules() {
  try {
    const result = await apiFetch("/api/qianchuan/actions/run-rules", {
      method: "POST",
      body: JSON.stringify({
        marketing_goal: "VIDEO_PROM_GOODS",
        page: 1,
        page_size: 500,
      }),
    });
    const actions = result.actions || [];
    if (!actions.length) {
      addLog("规则执行完成", "当前规则没有命中计划。", "neutral");
      toast("当前没有命中的计划");
      return;
    }
    for (const item of actions.slice(0, 10)) {
      const plan = item.plan || {};
      const rule = item.rule || {};
      const ok = item.response?.code === 0;
      addLog(
        `${ok ? "已提交" : "提交失败"} · ${rule.name || rule.action}`,
        `${plan.name || plan.id}，接口返回：${item.response?.message || item.response?.code || "OK"}。`,
        ok ? (isBudgetIncreaseAction(rule.action) ? "ok" : "danger") : "neutral",
      );
    }
    for (const item of result.productShutdownNotifications || []) {
      const notificationOk = item.notification?.ok || item.notification?.skipped;
      addLog(
        "商品全停提醒",
        `${item.productName || "未命名商品"} 已全停，计划 ${item.planCount || 0} 个，本次自动暂停 ${item.actionCount || 0} 个。`,
        notificationOk ? "ok" : "neutral",
      );
    }
    await loadBackendData();
    toast(`已执行 ${actions.length} 个动作`);
  } catch (error) {
    addLog("规则执行失败", error.message, "danger");
    toast("规则执行失败");
  }
}

async function pausePlan(planId) {
  const plan = state.plans.find((item) => Number(item.id) === Number(planId));
  if (!plan) return;
  try {
    const result = await apiFetch("/api/qianchuan/actions/pause", {
      method: "POST",
      body: JSON.stringify(planActionPayload(plan)),
    });
    addLog(result.ok ? "暂停已提交" : "暂停失败", `${plan.name}，接口返回：${result.response?.message || result.response?.code}。`, result.ok ? "danger" : "neutral");
    await loadBackendData();
    toast(result.ok ? "暂停已提交" : "暂停失败");
  } catch (error) {
    addLog("暂停失败", error.message, "danger");
    toast("暂停失败");
  }
}

async function startPlan(planId) {
  const plan = state.plans.find((item) => Number(item.id) === Number(planId));
  if (!plan) return;
  try {
    const result = await apiFetch("/api/qianchuan/actions/enable", {
      method: "POST",
      body: JSON.stringify(planActionPayload(plan)),
    });
    addLog(result.ok ? "启动已提交" : "启动失败", `${plan.name}，接口返回：${result.response?.message || result.response?.code}。`, result.ok ? "ok" : "neutral");
    await loadBackendData();
    if (state.activeView === "operations") await loadOperationBoard();
    toast(result.ok ? "启动已提交" : "启动失败");
  } catch (error) {
    addLog("启动失败", error.message, "danger");
    toast("启动失败");
  }
}

async function raiseBudget(planId) {
  const plan = state.plans.find((item) => Number(item.id) === Number(planId));
  if (!plan) return;
  const amount = Number(window.prompt("输入增加预算金额", "100") || 0);
  if (amount <= 0) return;
  if (amount < 100) {
    toast("单次调整至少 100 元");
    return;
  }
  const newBudget = Number(plan.budget || 0) + amount;
  try {
    const result = await apiFetch("/api/qianchuan/actions/budget", {
      method: "POST",
      body: JSON.stringify({ ...planActionPayload(plan), budget: newBudget }),
    });
    addLog(result.ok ? "加预算已提交" : "加预算失败", `${plan.name}，新预算 ${yuan(newBudget)} 元，接口返回：${result.response?.message || result.response?.code}。`, result.ok ? "ok" : "neutral");
    await loadBackendData();
    toast(result.ok ? "加预算已提交" : "加预算失败");
  } catch (error) {
    addLog("加预算失败", error.message, "danger");
    toast("加预算失败");
  }
}

async function lowerBudget(planId) {
  const plan = state.plans.find((item) => Number(item.id) === Number(planId));
  if (!plan) return;
  const amount = Number(window.prompt("输入减少预算金额", "100") || 0);
  if (amount <= 0) return;
  if (amount < 100) {
    toast("单次调整至少 100 元");
    return;
  }
  const newBudget = Math.max(1, Number(plan.budget || 0) - amount);
  try {
    const result = await apiFetch("/api/qianchuan/actions/budget", {
      method: "POST",
      body: JSON.stringify({ ...planActionPayload(plan), budget: newBudget }),
    });
    addLog(result.ok ? "减预算已提交" : "减预算失败", `${plan.name}，新预算 ${yuan(newBudget)} 元，接口返回：${result.response?.message || result.response?.code}。`, result.ok ? "ok" : "neutral");
    await loadBackendData();
    toast(result.ok ? "减预算已提交" : "减预算失败");
  } catch (error) {
    addLog("减预算失败", error.message, "danger");
    toast("减预算失败");
  }
}

function addRule() {
  const id = `rule-${Date.now()}`;
  const groupId = state.activeGroupId || state.groups[0]?.id || "watch-notify";
  state.rules.push({
    ...ruleFormLogic.defaultRuleForGroup(groupId, new Date().toISOString(), CONTROL_PLAN_SMART_BID_TYPES),
    id,
  });
  state.activeRuleId = id;
  state.activeGroupId = groupId;
  state.ruleWorkspaceMode = "editor";
  renderAll();
}

function addGroup() {
  const id = `group-${Date.now()}`;
  state.groups.push({ id, name: "新分组", description: "待配置", shopId: null });
  state.activeGroupId = id;
  renderAll();
}

async function deleteUser(userId) {
  if (!window.confirm("确认删除这个子账号？")) return;
  const result = await apiFetch("/api/admin/users/delete", {
    method: "POST",
    body: JSON.stringify({ id: Number(userId) }),
  });
  state.users = result.users || state.users;
  renderUsers();
  toast("子账号已删除");
}

async function deleteShop(shopId) {
  if (!window.confirm("确认停用这个来源账户？")) return;
  const result = await apiFetch("/api/shops/delete", {
    method: "POST",
    body: JSON.stringify({ shopId: Number(shopId) }),
  });
  state.shops = result.shops || state.shops;
  state.selectedShopId = state.shops[0]?.shopId || 0;
  renderAll();
  toast("来源账户已停用");
}

async function bindPlanPrefix(prefix) {
  const normalized = normalizePlanPrefix(prefix);
  const select = els.shopRows.querySelector(`[data-prefix-select="${normalized}"]`);
  const userId = Number(select?.value || 0);
  if (!normalized || !userId) {
    toast("先选择投手");
    return;
  }
  const target = state.users.find((user) => Number(user.id) === userId);
  if (!target) {
    toast("没有找到这个投手");
    return;
  }
  const changedUsers = state.users.filter(
    (user) =>
      user.role !== "admin" &&
      (Number(user.id) === userId || (user.planPrefixes || []).map(normalizePlanPrefix).includes(normalized)),
  );
  let latestUsers = state.users;
  for (const user of changedUsers) {
    const existing = (user.planPrefixes || []).map(normalizePlanPrefix).filter(Boolean);
    const nextPrefixes =
      Number(user.id) === userId
        ? Array.from(new Set([...existing, normalized])).sort()
        : existing.filter((item) => item !== normalized);
    const result = await apiFetch("/api/admin/users", {
      method: "POST",
      body: JSON.stringify({
        id: Number(user.id),
        username: user.username,
        displayName: user.displayName,
        role: user.role,
        status: user.status,
        planPrefixes: nextPrefixes,
      }),
    });
    latestUsers = result.users || latestUsers;
  }
  state.users = latestUsers;
  addLog("计划前缀已绑定", `${normalized} 已绑定给 ${target.displayName || target.username}。`, "ok");
  toast("绑定已保存");
  await loadBackendData();
}

function renderAll() {
  if (!state.selectedShopId && state.shops.length) state.selectedShopId = state.shops[0].shopId;
  renderShell();
  renderDashboardTables();
  renderShopRows();
  renderGroups();
  renderRules();
  renderTrash();
  renderPlans();
  renderProducts();
  renderOperations();
  renderUsers();
  renderReport();
  renderLogs();
}

function bindEvents() {
  els.reportStartDate.value = dateInputValue();
  els.reportEndDate.value = dateInputValue();
  els.loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await login(els.loginUsername.value.trim(), els.loginPassword.value);
      showApp();
      await loadBackendData();
    } catch (error) {
      els.loginHint.textContent = error.message;
    }
  });

  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      switchView(button.dataset.view);
      if (button.dataset.view === "operations") {
        loadOperationBoard().catch((error) => {
          addLog("操作看板刷新失败", error.message, "danger");
          toast("操作看板刷新失败");
        });
      }
    });
  });
  els.refreshOperationsBtn?.addEventListener("click", async () => {
    try {
      await loadOperationBoard();
      toast("操作看板已刷新");
    } catch (error) {
      addLog("操作看板刷新失败", error.message, "danger");
      toast("操作看板刷新失败");
    }
  });
  els.shopSelect.addEventListener("change", async () => {
    state.selectedShopId = Number(els.shopSelect.value);
    state.planPage = 1;
    renderAll();
    saveBrowserStartupSnapshot();
  });
  document.querySelectorAll(".segment").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".segment").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      state.activeStatus = button.dataset.status;
      state.planPage = 1;
      renderPlans();
    });
  });
  document.querySelectorAll(".plan-type-segment").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".plan-type-segment").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      state.activePlanType = button.dataset.planType || "all";
      state.planPage = 1;
      renderPlans();
    });
  });
  document.querySelectorAll(".product-segment").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".product-segment").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      state.activeProductStatus = button.dataset.productStatus;
      renderProducts();
    });
  });
  document.querySelectorAll(".trash-filter").forEach((button) => {
    button.addEventListener("click", () => {
      state.trashGroupFilter = button.dataset.trashGroup || "all";
      renderTrash();
    });
  });
  document.querySelectorAll(".sort-th").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.sortKey;
      if (state.planSortKey === key) {
        state.planSortDir = state.planSortDir === "desc" ? "asc" : "desc";
      } else {
        state.planSortKey = key;
        state.planSortDir = "desc";
      }
      state.planPage = 1;
      renderPlans();
    });
  });
  document.querySelectorAll(".product-sort-th").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.productSortKey;
      if (state.productSortKey === key) {
        state.productSortDir = state.productSortDir === "desc" ? "asc" : "desc";
      } else {
        state.productSortKey = key;
        state.productSortDir = "desc";
      }
      renderProducts();
    });
  });
  els.planSearch.addEventListener("input", () => {
    state.planPage = 1;
    renderPlans();
  });
  els.productSearch.addEventListener("input", renderProducts);
  els.planPagination.addEventListener("click", (event) => {
    const button = event.target.closest("[data-page]");
    if (!button || button.disabled) return;
    state.planPage = Number(button.dataset.page || 1);
    renderPlans();
  });
  els.loadReportBtn.addEventListener("click", loadReport);
  els.reportPlanSearch.addEventListener("input", renderReport);
  document.querySelector("#refreshBtn").addEventListener("click", refreshAll);
  document.querySelector("#runRulesBtn").addEventListener("click", runRules);
  document.querySelector("#logoutBtn").addEventListener("click", logout);
  document.querySelectorAll(".rule-mode-tab").forEach((button) => {
    button.addEventListener("click", () => setRuleWorkspaceMode(button.dataset.ruleMode));
  });
  document.querySelector("#newRuleBtn").addEventListener("click", addRule);
  els.goTrashBtn.addEventListener("click", () => {
    switchView("trash");
  });
  document.querySelector("#newGroupBtn").addEventListener("click", addGroup);
  document.querySelector("#newUserBtn").addEventListener("click", clearUserForm);
  document.querySelector("#newShopBtn").addEventListener("click", clearShopForm);
  document.querySelector("#clearLogsBtn").addEventListener("click", () => {
    state.logs = [];
    renderLogs();
    toast("本页日志已清空");
  });
  els.groupList.addEventListener("click", (event) => {
    const card = event.target.closest("[data-group-id]");
    if (!card) return;
    state.activeGroupId = card.dataset.groupId;
    state.activeRuleId = rulesInGroup(state.activeGroupId)[0]?.id || "";
    state.ruleWorkspaceMode = "library";
    renderGroups();
    renderRules();
  });
  els.ruleList.addEventListener("click", (event) => {
    const card = event.target.closest("[data-rule-id]");
    if (!card) return;
    state.activeRuleId = card.dataset.ruleId;
    state.ruleWorkspaceMode = "editor";
    renderRules();
  });
  els.ruleForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await saveRuleForm();
    } catch (error) {
      addLog("规则保存失败", error.message, "danger");
      toast("规则保存失败");
    }
  });
  els.ruleAction.addEventListener("change", syncRuleFieldState);
  els.deleteRuleBtn.addEventListener("click", () => {
    deleteActiveRule().catch((error) => {
      addLog("规则删除失败", error.message, "danger");
      toast("规则删除失败");
    });
  });
  els.trashRows.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action='restore-rule']");
    if (!button) return;
    restoreRule(button.dataset.ruleId).catch((error) => {
      addLog("规则恢复失败", error.message, "danger");
      toast("规则恢复失败");
    });
  });
  els.groupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await saveGroupForm();
    } catch (error) {
      addLog("分组保存失败", error.message, "danger");
      toast("分组保存失败");
    }
  });
  els.userForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await saveUserForm();
    } catch (error) {
      addLog("子账号保存失败", error.message, "danger");
      toast("子账号保存失败");
    }
  });
  els.shopForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await saveShopForm();
    } catch (error) {
      addLog("来源账户保存失败", error.message, "danger");
      toast("来源账户保存失败");
    }
  });
  els.userRows.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    if (button.dataset.action === "edit-user") editUser(button.dataset.userId);
    if (button.dataset.action === "delete-user") deleteUser(button.dataset.userId);
  });
  els.shopRows.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    if (button.dataset.action === "bind-prefix") bindPlanPrefix(button.dataset.prefix);
    if (button.dataset.action === "edit-shop") editShop(button.dataset.shopId);
    if (button.dataset.action === "delete-shop") deleteShop(button.dataset.shopId);
  });
  els.planRows.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    if (button.dataset.action === "pause-plan") pausePlan(button.dataset.planId);
    if (button.dataset.action === "start-plan") startPlan(button.dataset.planId);
    if (button.dataset.action === "raise-budget") raiseBudget(button.dataset.planId);
    if (button.dataset.action === "lower-budget") lowerBudget(button.dataset.planId);
  });
  els.productRows.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    if (button.dataset.action === "view-product-plans") {
      els.planSearch.value = decodeURIComponent(button.dataset.productName || "");
      state.planPage = 1;
      switchView("plans");
      renderPlans();
    }
  });
}

async function init() {
  bindEvents();
  showLogin();
  if (window.lucide) window.lucide.createIcons();
  const restored = restoreBrowserStartupSnapshot();
  if (restored) showApp();
  try {
    const localRestored = await loadLocalStartupSnapshot();
    if (localRestored) showApp();
    if (restored || localRestored) {
      refreshConfigData().catch((error) => addLog("规则配置刷新失败", error.message, "danger"));
      return;
    }
    showLogin(state.sessionToken ? "本机暂无可显示缓存，请重新登录后点击更新云端。" : "请输入管理员或子账号。");
  } catch (error) {
    showLogin(error.message || "登录初始化失败");
  }
}

init();
