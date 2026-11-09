/* 知天命 · 前端应用 */
"use strict";

/* ---------- 五行对照（与后端 tables.py 一致） ---------- */
const STEM_EL = {甲:"木",乙:"木",丙:"火",丁:"火",戊:"土",己:"土",庚:"金",辛:"金",壬:"水",癸:"水"};
const BRANCH_EL = {子:"水",丑:"土",寅:"木",卯:"木",辰:"土",巳:"火",午:"火",未:"土",申:"金",酉:"金",戌:"土",亥:"水"};

/* ---------- 全局状态 ---------- */
const S = {
  token: localStorage.getItem("kf_token") || "",
  user: null,
  payload: null,      // 当前展示的命盘 {chart_id, round, status, chart, fortune, statements}
  answers: {},        // 校验答案 id -> bool
  convId: null,       // 当前对话 id
  roundsUsed: 0,
  convs: [],
  authMode: "login",
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

/* ---------- API ---------- */
async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json" };
  if (S.token) headers.Authorization = "Bearer " + S.token;
  const res = await fetch(path, { ...opts, headers });
  let data = null;
  try { data = await res.json(); } catch (e) {}
  if (!res.ok) {
    const err = new Error((data && data.detail) || `请求失败（${res.status}）`);
    err.status = res.status;
    throw err;
  }
  return data;
}

/* ---------- 工具 ---------- */
function toast(msg, ms = 2600) {
  const t = $("#toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(t._h); t._h = setTimeout(() => (t.hidden = true), ms);
}
function overlay(show, text) {
  $("#overlay").hidden = !show;
  if (text) $("#overlayText").textContent = text;
}
function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
/* 轻量 markdown：AI 回复中的 **加粗**、# 标题、- 列表 */
function mdLite(s) {
  let h = esc(s);
  h = h.replace(/^#{1,4}\s+(.*)$/gm, "<b>$1</b>");
  h = h.replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>");
  h = h.replace(/\*([^*\n]+)\*/g, "<i>$1</i>");
  h = h.replace(/^[-•]\s+/gm, "· ");
  return h;
}
const EL_CLASS = e => "e-" + e;

/* ---------- 视图切换 ---------- */
function setView(name) {
  $$(".view").forEach(v => (v.hidden = true));
  $("#view-" + name).hidden = false;
  $$(".nav-tab").forEach(b => b.classList.toggle("active", b.dataset.view === name));
  if (name === "chat") refreshChatShell();
  if (name === "archive") loadArchive();
  if (name === "chart" && !S.payload) {
    if (S.user && S.hasFinal === false) setView("onboard");
  }
}

/* ============================================================
   登录 / 注册
   ============================================================ */
$$(".auth-tab").forEach(btn => btn.addEventListener("click", () => {
  S.authMode = btn.dataset.tab;
  $$(".auth-tab").forEach(b => b.classList.toggle("active", b === btn));
  $("#authSubmit").textContent = S.authMode === "login" ? "进入知天命" : "立 卷 · 注 册";
  $("#nickRow").hidden = S.authMode !== "register";
  $("#authPass").autocomplete = S.authMode === "login" ? "current-password" : "new-password";
  $("#authMsg").textContent = "";
}));

/* ---------- 登录弹窗：首页默认不展示，需要时唤起 ---------- */
function openAuth(mode) {
  $("#authModal").hidden = false;
  if (mode) { const t = $(`.auth-tab[data-tab="${mode}"]`); if (t) t.click(); }
  setTimeout(() => $("#authEmail").focus(), 60);
}
function closeAuth() { $("#authModal").hidden = true; $("#authMsg").textContent = ""; }
$("#heroStart").addEventListener("click", () => openAuth());
$("#loginBtn").addEventListener("click", () => openAuth());
$("#authClose").addEventListener("click", closeAuth);
$("#authModal").addEventListener("click", e => { if (e.target === $("#authModal")) closeAuth(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") closeAuth(); });

$("#authForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = $("#authEmail").value.trim();
  const password = $("#authPass").value;
  if (!email || !password) return;
  $("#authSubmit").disabled = true;
  try {
    const body = S.authMode === "register"
      ? { email, password, nickname: $("#authNick").value.trim() || null }
      : { email, password };
    const data = await api(`/api/auth/${S.authMode}`, { method: "POST", body: JSON.stringify(body) });
    S.token = data.token;
    localStorage.setItem("kf_token", S.token);
    S.user = data.user;
    await afterLogin();
    closeAuth();
  } catch (err) {
    $("#authMsg").textContent = err.message;
  } finally {
    $("#authSubmit").disabled = false;
  }
});

$("#logoutBtn").addEventListener("click", () => {
  localStorage.removeItem("kf_token");
  S.token = ""; S.user = null; S.payload = null; S.convId = null;
  $("#logoutBtn").hidden = true; $("#userChip").hidden = true; $("#mainNav").hidden = true;
  $("#loginBtn").hidden = false;
  closeAuth();
  setView("landing");
});
$("#brandHome").addEventListener("click", () => {
  if (!S.user) return setView("landing");
  setView(S.hasFinal ? "chart" : "onboard");
});

async function afterLogin() {
  const me = await api("/api/auth/me");
  S.user = me.user; S.hasFinal = me.has_final_chart;
  $("#userChip").hidden = false;
  $("#userChip").innerHTML = `缘主 <b>${esc(me.user.nickname || me.user.email)}</b>`;
  $("#logoutBtn").hidden = false;
  $("#mainNav").hidden = false;
  $("#loginBtn").hidden = true;
  if (me.has_final_chart) {
    S.payload = await api("/api/chart/current");
    renderChart(true);
    setView("chart");
  } else {
    setView("onboard");
  }
}

/* ============================================================
   排盘表单
   ============================================================ */
async function loadCities() {
  const { groups } = await api("/api/cities");
  const sel = $("#obCity");
  sel.innerHTML = groups.map(g =>
    `<optgroup label="${esc(g.group)}">${g.cities.map(c => `<option>${esc(c)}</option>`).join("")}</optgroup>`
  ).join("");
  sel.value = "北京";
}

/* ---------- 农历输入 ---------- */
const LUNAR_MONTHS = ["正月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "冬月", "腊月"];
function lunarDayName(n) {
  if (n <= 10) return "初" + "一二三四五六七八九十"[n - 1];
  if (n <= 20) return (n === 20 ? "二十" : "十" + "一二三四五六七八九"[n - 11]);
  if (n < 30) return "廿" + "一二三四五六七八九"[n - 21];
  return "三十";
}
(function initLunarFields() {
  $("#obLM").innerHTML = LUNAR_MONTHS.map((n, i) => `<option value="${i + 1}">${n}</option>`).join("");
  $("#obLD").innerHTML = Array.from({ length: 30 }, (_, i) =>
    `<option value="${i + 1}">${lunarDayName(i + 1)}</option>`).join("");
  $$('input[name="obCal"]').forEach(r => r.addEventListener("change", () => setCal(r.value)));
})();
function setCal(mode) {
  $("#wrapDateSolar").hidden = mode !== "solar";
  $("#wrapDateLunar").hidden = mode !== "lunar";
}
const curCal = () => document.querySelector('input[name="obCal"]:checked').value;
$("#obStart").addEventListener("click", async () => {
  const cal = curCal();
  let date;
  if (cal === "lunar") {
    const ly = $("#obLY").value, ld = $("#obLD").value;
    if (!ly || !ld) return toast("农历出生日期须填全年 / 日");
    date = `${ly}-${String($("#obLM").value).padStart(2, "0")}-${String(ld).padStart(2, "0")}`;
  } else {
    date = $("#obDate").value;
  }
  const time = $("#obTime").value;
  if (!date || !time) return toast("出生日期与时间须填全");
  const gender = document.querySelector('input[name="obGender"]:checked').value;
  $("#obNotice").hidden = true;
  overlay(true, "天 人 交 感 · 正 在 起 局 …");
  try {
    S.payload = await api("/api/chart/start", {
      method: "POST",
      body: JSON.stringify({
        date, time, city: $("#obCity").value, gender,
        calendar: cal, leap: cal === "lunar" && $("#obLL").checked,
      }),
    });
    S.answers = {};
    renderChart(false);
    setView("chart");
    window.scrollTo({ top: 0 });
  } catch (err) {
    if (err.status === 401) return setView("landing");
    toast(err.message);
  } finally {
    overlay(false);
  }
});

/* ============================================================
   命盘渲染
   ============================================================ */
function renderChart(confirmed) {
  const p = S.payload;
  if (!p || !p.chart) return;
  const c = p.chart;
  $("#chartTitle").innerHTML = p.status === "confirmed" ? "命 盘 <small>已 定 案</small>" : "命 盘 <small>校 验 中</small>";
  $("#roundBadge").textContent = p.status === "confirmed"
    ? `第 ${p.round} 轮 · 定案` : `校验轮次 ${p.round} / 3`;
  $("#variantNote").textContent = (p.variant_note || "") +
    (c.adjust_note ? ` · ${c.adjust_note}（起盘按 ${c.plot_time}）` : ` · 起盘按 ${c.plot_time}`);

  let html = "";

  /* --- 四柱 --- */
  html += `<div class="pillar-grid${p.status === "confirmed" ? " final-banner" : ""}">`;
  for (const col of c.pillars) {
    const isDay = col.gan_shishen === "日主";
    html += `<div class="pillar-col">
      <div class="col-head">${col.position}<small>${esc(col.ganzhi)}</small></div>
      <div class="pillar-cell">
        <span class="cell-label">天干</span>
        <div class="char-tile ${EL_CLASS(STEM_EL[col.gan])}">${col.gan}</div>
        <span class="shishen-tag${isDay ? " daymaster" : ""}">${col.gan_shishen}</span>
      </div>
      <div class="pillar-cell" style="padding-top:6px">
        <span class="cell-label">地支</span>
        <div class="char-tile ${EL_CLASS(BRANCH_EL[col.zhi])}">${col.zhi}</div>
      </div>
      <div class="hide-row">
        <div class="row-cap">藏干 · 十神</div>
        ${col.hide_gan.map((g, i) =>
          `<div class="hide-item"><b class="${EL_CLASS(STEM_EL[g])}">${g}</b>${col.hide_shishen[i]}</div>`).join("")}
      </div>
      <div class="nayin-row"><i>纳音</i>${esc(col.nayin)}</div>
    </div>`;
  }
  if (p.status === "confirmed") html += `<div class="stamp" style="grid-column:1/-1;justify-self:end">命格<small>已定案</small></div>`;
  html += `</div>`;

  /* --- 五行 + 强弱/喜用 --- */
  const wx = c.wuxing_count, maxWx = Math.max(...Object.values(wx), 1);
  const xy = c.xiyong;
  html += `<div class="analysis-grid">
    <div class="card panel">
      <h4>五行分布</h4>
      ${["木","火","土","金","水"].map(e => `
        <div class="wx-bar">
          <span class="wx-name ${EL_CLASS(e)}">${e}</span>
          <div class="wx-track"><div class="wx-fill ${EL_CLASS(e)}" data-w="${(wx[e] / maxWx * 100)}"></div></div>
          <span class="wx-count">${wx[e]}${wx[e] === 0 ? " ⚠" : ""}</span>
        </div>`).join("")}
      <p class="hint" style="margin-top:14px">
        ${Object.entries(wx).filter(([, v]) => v === 0).map(([k]) => `命局<b style="color:var(--seal)">缺${k}</b>`).join("，") || "五行俱全，气机流转不息"}。
        十神力量：${Object.entries(c.group_score).map(([k, v]) => `${k} ${v}`).join(" · ")}。
      </p>
    </div>
    <div class="card panel">
      <h4>日主强弱 · 喜用神</h4>
      <div class="gauge-wrap">
        <div class="gauge"><div class="gauge-needle" data-left="${c.strength.support_pct}%"></div></div>
        <div class="gauge-scale"><span>身弱 · 克泄耗</span><span>中和</span><span>身强 · 生扶</span></div>
        <p class="level-line">日主 <b>${c.day_master.gan}${c.day_master.element}</b>（${c.day_master.yinyang}），
          生扶力量 <b>${c.strength.support_pct}%</b> → <b>${c.strength.level}</b></p>
      </div>
      <div class="xy-chips">
        <div class="xy-chip yong"><small>用 神</small><b>${xy.yong_shen}</b>·${xy.yong_shen_shishen}</div>
        ${xy.xi_shen.length ? `<div class="xy-chip"><small>喜 神</small>${xy.xi_shen.map(e => `<b>${e}</b>`).join(" ")}</div>` : ""}
        <div class="xy-chip ji"><small>忌 神</small>${xy.ji_shen.map(e => `<b>${e}</b>`).join(" ")}</div>
        ${xy.adjusted_by === "ai" ? `<div class="xy-chip" style="border-color:var(--accent);color:var(--accent)">AI 复核改判</div>` : ""}
      </div>
      <p class="xy-advice">
        利行业：<b>${esc(xy.advice.industry)}</b><br>
        利方位：<b>${xy.advice.direction.join("、")}</b> · 利色系：<b>${xy.advice.color.join("、")}</b> · 利数：<b>${xy.advice.number.join("、")}</b>
      </p>
    </div>
  </div>`;

  /* --- 大运 --- */
  const thisYear = new Date().getFullYear();
  html += `<div class="card dayun-wrap panel"><h4>大运 · ${c.qiyun.age}岁起运（${c.qiyun.date}）</h4>
    <div class="dayun-scroll">
    ${c.dayun.slice(0, 9).map(d => `
      <div class="dayun-card${d.start_year <= thisYear && thisYear < d.end_year ? " current" : ""}">
        <span class="dy-luck ${d.luck}">${d.luck}</span>
        <div class="dy-gz">${d.ganzhi}</div>
        <div class="dy-ss">${d.gan_shishen}运</div>
        <div class="dy-years">${d.start_year}–${d.end_year}</div>
      </div>`).join("")}
    </div></div>`;

  /* --- 关键流年 --- */
  html += `<div class="card panel" style="margin-bottom:26px"><h4>关键流年 · 未来十载</h4>
    <ul class="key-years">
    ${c.key_years.map(k => `
      <li>
        <span class="ky-year">${k.year}<small>${k.ganzhi}年 · ${k.gan_shishen}</small></span>
        <span class="ky-notes">${k.notes.map(esc).join("；") || "平稳之年，按部就班"}
          <span class="ky-tag ${k.score > 0 ? "good" : k.score < 0 ? "bad" : ""}">${k.score > 0 ? "吉" : k.score < 0 ? "慎" : "平"}</span>
        </span>
      </li>`).join("")}
    </ul>
    <p class="hint">流年吉凶以喜用${xy.yong_shen}、忌${xy.ji_shen.join("、")}为纲，兼察六冲桃花。</p>
  </div>`;

  /* --- 命格断语 --- */
  const f = p.fortune;
  html += `<div class="fortune-grid">
    <div class="fortune-block"><h5>性 情</h5><p>${esc(f.personality)}</p></div>
    <div class="fortune-block"><h5>事 业</h5><p>${esc(f.career)}</p></div>
    <div class="fortune-block"><h5>姻 缘</h5><p>${esc(f.romance)}</p></div>
    <div class="fortune-block"><h5>大 运</h5><p>${esc(f.dayun)}</p></div>
  </div>`;

  /* --- 校验面板 or 定案入口 --- */
  if (p.status === "pending") {
    html += renderVerifyPanel();
  } else {
    html += `<div class="card" style="text-align:center">
      <p style="font-size:14px;color:var(--ink-soft);margin-bottom:18px">命格已定案存档。此时不知命，更待何时——</p>
      <button class="btn-gold" onclick="gotoChat()">携 命 格 · 问 AI 先 生</button>
    </div>`;
  }

  $("#chartBody").innerHTML = html;
  requestAnimationFrame(() => {
    $$(".wx-fill").forEach(el => (el.style.width = el.dataset.w + "%"));
    $$(".gauge-needle").forEach(el => (el.style.left = el.dataset.left));
  });
}

/* ---------- 校验面板 ---------- */
const ROUND_FOCUS = {
  1: "本轮为初排命盘",
  2: "本轮命盘已由 AI 复核、重定喜用",
  3: "本轮命盘经 AI 综合审定，为终审之轮",
};
function renderVerifyPanel() {
  const p = S.payload;
  return `<div class="card verify-panel" id="verifyPanel">
    <div class="verify-title"><h3>命格校验 · 第 ${p.round} 轮</h3>
      <span>${p.statements.length} 题（性情际遇 ×2 · 大运流年 ×3）</span></div>
    <p class="verify-desc">${ROUND_FOCUS[p.round] || ""}——以下断语皆由你的四柱推演而来，请逐条核对。
      <b>5 题至少 4 题符合即定案</b>；未达标时，你的校验结果将交 AI 依子平命理重新核定强弱与喜用，必要时更换推算方法重算。
      <b>三轮打磨仍未达标则本次不予存档</b>——请核对出生日期与时辰后重新提交。</p>
    ${p.statements.map(st => `
      <div class="stmt" data-id="${st.id}">
        <span class="stmt-cat">${st.category}</span>
        <span class="stmt-text">${esc(st.text)}</span>
        <span class="stmt-btns">
          <button class="vbtn yes" onclick="answerStmt(${st.id}, true, this)">符</button>
          <button class="vbtn no" onclick="answerStmt(${st.id}, false, this)">不 符</button>
        </span>
      </div>`).join("")}
    <div class="verify-foot">
      <span class="rate-tip" id="rateTip">已答 0 / ${p.statements.length}</span>
      <button class="btn-gold" id="verifySubmit" disabled onclick="submitVerify()">提 交 校 验</button>
    </div>
  </div>`;
}

function answerStmt(id, val, btn) {
  S.answers[id] = val;
  const row = btn.closest(".stmt");
  row.querySelectorAll(".vbtn").forEach(b => b.classList.remove("on"));
  btn.classList.add("on");
  const total = S.payload.statements.length;
  const done = Object.keys(S.answers).length;
  $("#rateTip").textContent = `已答 ${done} / ${total}`;
  $("#verifySubmit").disabled = done < total;
}

async function submitVerify() {
  const stmts = S.payload.statements;
  const answers = stmts.map(st => !!S.answers[st.id]);
  overlay(true, "校 验 汇 呈 · AI 复 核 命 格 …");
  try {
    const res = await api(`/api/chart/${S.payload.chart_id}/feedback`, {
      method: "POST", body: JSON.stringify({ answers }),
    });
    if (res.done) {
      S.payload = res; S.hasFinal = true;
      renderChart(true);
      toast(`校验通过（算准 ${res.agree}/${S.payload.statements.length || 5} 题），命格已定案`);
    } else if (res.failed) {
      const inp = (S.payload && S.payload.chart && S.payload.chart.input) || {};
      S.payload = null; S.answers = {}; S.hasFinal = false;
      if (inp.date) {
        if (inp.calendar === "lunar") {
          document.querySelector('input[name="obCal"][value="lunar"]').checked = true;
          setCal("lunar");
          const [ly, lm, ld] = inp.date.split("-");
          $("#obLY").value = ly; $("#obLM").value = Number(lm); $("#obLD").value = Number(ld);
          $("#obLL").checked = !!inp.leap;
        } else {
          document.querySelector('input[name="obCal"][value="solar"]').checked = true;
          setCal("solar");
          $("#obDate").value = inp.date;
        }
      }
      if (inp.time) $("#obTime").value = inp.time;
      if (inp.city) $("#obCity").value = inp.city;
      if (inp.gender) {
        const r = document.querySelector(`input[name="obGender"][value="${inp.gender}"]`);
        if (r) r.checked = true;
      }
      const n = $("#obNotice");
      n.textContent = res.message; n.hidden = false;
      setView("onboard");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      S.payload = res; S.answers = {};
      renderChart(false);
      toast(res.recomputed_reason, 5200);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  } catch (err) {
    toast(err.message);
  } finally {
    overlay(false);
  }
}

/* ============================================================
   AI 答疑
   ============================================================ */
function gotoChat() { setView("chat"); }

function renderMsgs(msgs, closed) {
  const box = $("#chatMsgs");
  if (!msgs.length) {
    box.innerHTML = `<div class="msg assistant"><div class="bubble">缘主请坐。你的命格我已阅尽——事业进退、姻缘早晚、流年趋避，心中有何大事，问将出来。</div></div>`;
  } else {
    box.innerHTML = msgs.map(m =>
      `<div class="msg ${m.role}"><div class="bubble">${m.role === "assistant" ? mdLite(m.content) : esc(m.content)}</div></div>`).join("");
  }
  box.scrollTop = box.scrollHeight;
  const dots = $("#roundDots");
  dots.innerHTML = Array.from({ length: 3 }, (_, i) =>
    `<i class="${i < S.roundsUsed ? "on" : ""}"></i>`).join("");
  const disabled = S.roundsUsed >= 3;
  $("#chatText").disabled = disabled;
  $("#chatSend").disabled = disabled;
  $("#chatSend").textContent = disabled ? "已 满 三 轮" : "开 问";
  $("#newChatBtn").hidden = !disabled;
  $("#chatCounter").textContent = disabled
    ? "本次三轮咨询圆满。天机不可泄尽——如需再问，可开启新的咨询。"
    : `本次咨询共 3 轮 · 已用 ${S.roundsUsed} 轮 · 余 ${3 - S.roundsUsed} 轮`;
}

async function refreshChatShell() {
  try {
    const { conversations, max_rounds } = await api("/api/chat/conversations");
    S.convs = conversations;
    const list = $("#convList");
    list.innerHTML = conversations.length ? conversations.map(c => `
      <button class="conv-item${c.id === S.convId ? " active" : ""}" onclick="openConv(${c.id})">
        ${esc(c.title)}<small>${c.created_at.slice(0, 16).replace("T", " ")} · ${c.rounds_used}/3 轮</small>
      </button>`).join("") : `<p class="hint">尚无咨询记录。</p>`;
    if (S.convId) {
      const detail = await api(`/api/chat/conversations/${S.convId}`);
      S.roundsUsed = detail.rounds_used;
      renderMsgs(detail.messages);
    } else if (conversations.length) {
      await openConv(conversations[0].id);
    } else {
      S.roundsUsed = 0;
      renderMsgs([]);
    }
  } catch (err) {
    toast(err.message);
  }
}

async function openConv(id) {
  S.convId = id;
  const detail = await api(`/api/chat/conversations/${id}`);
  S.roundsUsed = detail.rounds_used;
  renderMsgs(detail.messages);
  refreshChatShell();
}

$("#newChatBtn").addEventListener("click", () => {
  S.convId = null; S.roundsUsed = 0;
  renderMsgs([]);
  $$(".conv-item").forEach(b => b.classList.remove("active"));
  $("#chatText").focus();
});

$("#chatSend").addEventListener("click", sendChat);
$("#chatText").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
});

/* 解析 SSE 流：event: meta|delta|done|error */
async function readSSE(res, onEvent) {
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const blocks = buf.split("\n\n");
    buf = blocks.pop();
    for (const blk of blocks) {
      let ev = "message", data = "";
      for (const line of blk.split("\n")) {
        if (line.startsWith("event:")) ev = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (data) onEvent(ev, JSON.parse(data));
    }
  }
}

async function sendChat() {
  const text = $("#chatText").value.trim();
  if (!text) return;
  $("#chatText").value = "";
  $("#chatText").disabled = true; $("#chatSend").disabled = true;

  const box = $("#chatMsgs");
  box.insertAdjacentHTML("beforeend", `<div class="msg user"><div class="bubble">${esc(text)}</div></div>`);
  box.insertAdjacentHTML("beforeend",
    `<div class="msg assistant" id="pending"><div class="bubble typing"><i></i><i></i><i></i></div></div>`);
  box.scrollTop = box.scrollHeight;
  const pend = $("#pending .bubble");
  let acc = "", doneData = null, errData = null;

  try {
    const headers = { "Content-Type": "application/json" };
    if (S.token) headers.Authorization = "Bearer " + S.token;
    const res = await fetch("/api/chat/stream", {
      method: "POST", headers, body: JSON.stringify({ conversation_id: S.convId, text }),
    });
    if (!res.ok) {
      let detail = `请求失败（${res.status}）`;
      try { detail = (await res.json()).detail || detail; } catch (e) {}
      const err = new Error(detail); err.status = res.status; throw err;
    }
    await readSSE(res, (ev, d) => {
      if (ev === "meta") S.convId = d.conversation_id;
      else if (ev === "delta") {
        acc += d.text;
        pend.classList.remove("typing");
        pend.textContent = acc;                 // 流式期间纯文本，结束后再渲染 markdown
        box.scrollTop = box.scrollHeight;
      }
      else if (ev === "done") doneData = d;
      else if (ev === "error") errData = d;
    });
    if (errData) { const err = new Error(errData.message); err.status = errData.status; throw err; }

    const reply = (doneData && doneData.reply) || acc;
    $("#pending").remove();
    box.insertAdjacentHTML("beforeend", `<div class="msg assistant"><div class="bubble">${mdLite(reply)}</div></div>`);
    box.scrollTop = box.scrollHeight;
    if (doneData) { S.roundsUsed = doneData.rounds_used; renderMsgsFromDom(doneData.closed); }
  } catch (err) {
    $("#pending")?.remove();
    box.insertAdjacentHTML("beforeend", `<div class="msg system"><div class="bubble">${esc(err.message)}</div></div>`);
    box.scrollTop = box.scrollHeight;
    $("#chatText").disabled = false;
    if (err.status === 400 && S.roundsUsed >= 3) {
      $("#chatSend").disabled = true;
      $("#newChatBtn").hidden = false;
    } else {
      $("#chatSend").disabled = false;
    }
  }
}

function renderMsgsFromDom(closed) {
  const dots = $("#roundDots");
  dots.innerHTML = Array.from({ length: 3 }, (_, i) => `<i class="${i < S.roundsUsed ? "on" : ""}"></i>`).join("");
  $("#chatText").disabled = closed;
  $("#chatSend").disabled = closed;
  $("#chatSend").textContent = closed ? "已 满 三 轮" : "开 问";
  $("#newChatBtn").hidden = !closed;
  $("#chatCounter").textContent = closed
    ? "本次三轮咨询圆满。天机不可泄尽——如需再问，可开启新的咨询。"
    : `本次咨询共 3 轮 · 已用 ${S.roundsUsed} 轮 · 余 ${3 - S.roundsUsed} 轮`;
}

/* ============================================================
   存档
   ============================================================ */
async function loadArchive() {
  try {
    const arc = await api("/api/chart/archive");
    const rows = [];
    for (const r of arc.charts) {
      const detail = await api(`/api/chart/${r.chart_id}`);
      const gz = detail.chart.pillars.map(p => p.ganzhi).join(" ");
      rows.push(`<div class="chart-row">
        <span class="cr-pillars">${gz}</span>
        <span class="cr-meta">第 ${r.round} 轮 · ${esc(r.variant_note)}<br>
          ${r.reject_rate != null ? `否定率 ${Math.round(r.reject_rate * 100)}% · ` : ""}${r.created_at.slice(0, 16).replace("T", " ")}</span>
        <span class="status-tag ${r.status}">${{ confirmed: "已定案", rejected: "已重算", failed: "未定案" }[r.status] || "待校验"}</span>
        ${r.is_final ? `<span class="status-tag final">现行命格</span>` : ""}
        <button class="btn-ghost sm" onclick="viewArchivedChart(${r.chart_id})">查看</button>
      </div>`);
    }
    $("#archiveCharts").innerHTML = rows.length
      ? `<div class="chart-rows">${rows.join("")}</div>`
      : `<p class="hint">尚无排盘记录。</p>`;
  } catch (err) {
    toast(err.message);
  }
}

async function viewArchivedChart(id) {
  S.payload = await api(`/api/chart/${id}`);
  renderChart(S.payload.status === "confirmed");
  setView("chart");
  window.scrollTo({ top: 0 });
}

/* ---------- 导航 ---------- */
$$(".nav-tab").forEach(btn => btn.addEventListener("click", () => {
  if (btn.dataset.view === "chart" && !S.payload) return setView("onboard");
  setView(btn.dataset.view);
}));

/* ============================================================
   启动
   ============================================================ */
(async function boot() {
  await loadCities();
  if (S.token) {
    try {
      await afterLogin();
      return;
    } catch (e) {
      localStorage.removeItem("kf_token");
      S.token = "";
    }
  }
  $("#loginBtn").hidden = false;
  setView("landing");
})();
