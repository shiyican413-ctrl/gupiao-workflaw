const state = {
  workflow: null,
  latestRun: null,
  results: [],
  watchlist: [],
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => el.classList.remove("show"), 2200);
}

function fillWorkflowForm(workflow) {
  $("#wfName").value = workflow.name;
  $("#minMarketCap").value = workflow.universe_config.min_market_cap;
  $("#minListingYears").value = workflow.universe_config.min_listing_years;
  $("#minRevenueGrowth").value = workflow.filter_config.min_revenue_growth;
  $("#minProfitGrowth").value = workflow.filter_config.min_profit_growth;
  $("#minRoe").value = workflow.filter_config.min_roe;
  $("#maxDebtRatio").value = workflow.filter_config.max_debt_ratio;
  $("#maxPe").value = workflow.filter_config.max_pe;
  $("#minTrend").value = workflow.filter_config.min_ma_trend;
  $$(".board").forEach((box) => {
    box.checked = workflow.universe_config.boards.includes(box.value);
  });
}

function collectWorkflowForm() {
  return {
    name: $("#wfName").value.trim() || "A股选股 Workflow",
    universe_config: {
      boards: $$(".board")
        .filter((box) => box.checked)
        .map((box) => box.value),
      min_market_cap: Number($("#minMarketCap").value || 0),
      min_listing_years: Number($("#minListingYears").value || 0),
      exclude_st: true,
      exclude_suspended: true,
    },
    filter_config: {
      min_revenue_growth: Number($("#minRevenueGrowth").value || 0),
      min_profit_growth: Number($("#minProfitGrowth").value || 0),
      min_roe: Number($("#minRoe").value || 0),
      max_debt_ratio: Number($("#maxDebtRatio").value || 100),
      max_pe: Number($("#maxPe").value || 999),
      min_ma_trend: Number($("#minTrend").value || 0),
    },
  };
}

function renderMetrics() {
  $("#latestRun").textContent = state.latestRun ? state.latestRun.run_time.replace("T", " ").slice(0, 16) : "未运行";
  $("#candidateCount").textContent = state.results.length;
  $("#avgScore").textContent = state.latestRun?.summary?.avg_score ?? 0;
  $("#watchCount").textContent = state.watchlist.length;
  $("#runSummary").textContent = state.latestRun?.summary?.message || "运行后展示候选股票、评分和入选原因。";
}

function renderResults() {
  const body = $("#resultsBody");
  if (!state.results.length) {
    body.innerHTML = `<tr><td colspan="10" class="empty">暂无结果，点击右上角运行 Workflow。</td></tr>`;
    return;
  }
  body.innerHTML = state.results
    .map(
      (item) => `
        <tr>
          <td>${item.rank}</td>
          <td>
            <span class="stock-name">${item.stock_name}</span>
            <span class="stock-code">${item.stock_code}</span>
          </td>
          <td>${item.industry}</td>
          <td><span class="score">${item.total_score}</span></td>
          <td>${item.growth_score}</td>
          <td>${item.quality_score}</td>
          <td>${item.valuation_score}</td>
          <td>${item.trend_score}</td>
          <td><div class="reason">${item.reasons.slice(0, 2).join("；")}</div></td>
          <td><button data-add="${item.stock_code}">加入观察</button></td>
        </tr>
      `,
    )
    .join("");
}

function renderWatchlist() {
  const body = $("#watchlistBody");
  if (!state.watchlist.length) {
    body.innerHTML = `<div class="empty">观察池为空，可以从选股结果里加入股票。</div>`;
    return;
  }
  body.innerHTML = state.watchlist
    .map(
      (item) => `
        <article class="watch-card">
          <header>
            <div>
              <strong>${item.stock_name}</strong>
              <span>${item.stock_code} · 当前评分 ${item.current_score ?? "-"}</span>
            </div>
            <button data-remove="${item.stock_code}">移除</button>
          </header>
          <p>${item.note || "来自最近一次 workflow 运行结果。"}</p>
          <div class="tag-row">
            ${(item.tags || []).map((tag) => `<span class="tag">${tag}</span>`).join("")}
          </div>
        </article>
      `,
    )
    .join("");
}

function renderAll() {
  renderMetrics();
  renderResults();
  renderWatchlist();
}

async function loadInitial() {
  const workflows = await api("/api/workflows");
  state.workflow = workflows[0];
  fillWorkflowForm(state.workflow);

  const latest = await api("/api/latest");
  state.latestRun = latest.run;
  state.results = latest.results || [];

  state.watchlist = await api("/api/watchlist");
  renderAll();
}

async function saveWorkflow() {
  const payload = collectWorkflowForm();
  if (!payload.universe_config.boards.length) {
    toast("至少选择一个股票范围");
    return false;
  }
  state.workflow = await api(`/api/workflows/${state.workflow.id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  fillWorkflowForm(state.workflow);
  toast("Workflow 已保存");
  return true;
}

async function runWorkflow() {
  $("#runBtn").disabled = true;
  $("#runBtn").textContent = "运行中...";
  try {
    const payload = await api(`/api/workflows/${state.workflow.id}/run`, { method: "POST" });
    state.latestRun = payload.run;
    state.results = payload.results || [];
    renderAll();
    toast("运行完成");
  } finally {
    $("#runBtn").disabled = false;
    $("#runBtn").textContent = "运行 Workflow";
  }
}

async function addWatch(stockCode) {
  const item = state.results.find((result) => result.stock_code === stockCode);
  if (!item) return;
  await api("/api/watchlist", {
    method: "POST",
    body: JSON.stringify({
      stock_code: item.stock_code,
      stock_name: item.stock_name,
      tags: [item.industry, `评分 ${item.total_score}`],
      note: item.reasons[0],
      added_from_run_id: item.run_id,
      added_score: item.total_score,
      current_score: item.total_score,
      alert_config: { score_drop: 8, risk_event: true },
    }),
  });
  state.watchlist = await api("/api/watchlist");
  renderAll();
  toast(`${item.stock_name} 已加入观察池`);
}

async function removeWatch(stockCode) {
  await api(`/api/watchlist/${stockCode}`, { method: "DELETE" });
  state.watchlist = await api("/api/watchlist");
  renderAll();
  toast("已移出观察池");
}

document.addEventListener("click", (event) => {
  const addCode = event.target.dataset?.add;
  const removeCode = event.target.dataset?.remove;
  if (addCode) addWatch(addCode);
  if (removeCode) removeWatch(removeCode);
});

$("#saveBtn").addEventListener("click", saveWorkflow);
$("#runBtn").addEventListener("click", async () => {
  const saved = await saveWorkflow();
  if (!saved) return;
  await runWorkflow();
});

loadInitial().catch((error) => {
  console.error(error);
  toast("加载失败，请查看控制台");
});
