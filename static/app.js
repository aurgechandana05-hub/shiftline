const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const state = {
  mode: "demo",
  provider: "Local demo memory",
  memories: [],
  selectedOutcome: "Unverified",
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(date);
}

function icon(name) {
  return `<svg aria-hidden="true"><use href="#i-${name}"></use></svg>`;
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(`The server returned an unreadable response (${response.status}).`);
  }
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
  return data;
}

function toast(message, isError = false) {
  const element = document.createElement("div");
  element.className = `toast${isError ? " error" : ""}`;
  element.textContent = message;
  $("#toast-region").append(element);
  window.setTimeout(() => element.remove(), 4300);
}

function setProviderBadge(provider, isError = false, isConnected = false) {
  const badge = $("#provider-badge");
  badge.classList.toggle("demo-provider", provider === "Local demo memory");
  badge.classList.toggle("error-provider", isError);
  $("#seed-history").hidden = provider !== "Hindsight" || isError;
  const description = isError
    ? "Hindsight unavailable"
    : provider === "Hindsight"
      ? (isConnected ? "Hindsight connected" : "Hindsight live memory")
      : "Local demo · not Hindsight";
  badge.innerHTML = `<span class="connection-dot"></span><span>${escapeHtml(description)}</span>${icon("chevron")}`;
  $("#provider-foot").textContent = isError
    ? "Hindsight request failed. No successful memory operation was recorded."
    : provider === "Hindsight"
      ? (isConnected
        ? "Hindsight API connected · use Load demo history to retain the fictional handoff scenario."
        : "Live provider · retained memories and recall results come from Hindsight.")
      : "Local demo memory · a lightweight SQLite fixture, not Hindsight.";
  $("#provider-foot").classList.toggle("demo-foot", provider !== "Hindsight" && !isError);
  state.provider = provider;
}

function renderTimeline(events) {
  const timeline = $("#timeline");
  if (!events.length) {
    timeline.innerHTML = '<div class="activity-empty">No shift events have been recorded yet.</div>';
    return;
  }
  timeline.innerHTML = events.map((event) => {
    const category = escapeHtml(event.category);
    const content = escapeHtml(event.content);
    const source = escapeHtml(event.source);
    const outcome = String(event.outcome || "").toLowerCase();
    const marker = outcome === "failed" || category.toLowerCase().includes("failed")
      ? "close"
      : category.toLowerCase().includes("constraint")
        ? "clock"
        : "check";
    const markerClass = marker === "close" ? "failed-marker" : marker === "clock" ? "constraint-marker" : "";
    return `<div class="timeline-item">
      <span class="timeline-marker ${markerClass}">${icon(marker)}</span>
      <div class="timeline-copy"><strong>${category}</strong><p>${content}<br><span class="source-link">${icon("copy")} ${source}</span></p></div>
      <span class="timeline-time">${escapeHtml(formatTime(event.created_at))}</span>
    </div>`;
  }).join("");
}

function renderActivity(items) {
  const container = $("#activity-list");
  if (!items.length) {
    container.innerHTML = '<div class="activity-empty">No memory operations yet.</div>';
    return;
  }
  container.innerHTML = items.slice(0, 5).map((item) => {
    const demo = item.status === "demo";
    const symbol = item.action === "recall" ? "search" : "check";
    const label = item.action === "recall" ? "RECALL" : "RETAIN";
    return `<div class="activity-row">
      <span class="activity-symbol ${demo ? "demo-symbol" : ""}">${icon(symbol)}</span>
      <span class="activity-copy"><strong>${escapeHtml(item.detail)}</strong><small>${label} · ${escapeHtml(formatTime(item.created_at))}</small></span>
    </div>`;
  }).join("");
}

function renderBrief(data) {
  state.memories = data.memories || [];
  const sections = data.sections || {};
  const total = state.memories.length;
  $("#memory-count").textContent = total === 1 ? "1 memory recalled" : `${total} memories recalled`;
  const container = $("#brief-sections");
  if (!container) return;
  const cards = [
    { key: "checks", label: "SAFE NEXT CHECK", icon: "check", style: "safe", empty: "No safe check has been recalled. Confirm the current ticket and ask the on-call owner." },
    { key: "avoid", label: "AVOID REPEATING", icon: "close", style: "avoid", empty: "No failed approach was recalled. Check the incident record before retrying a change." },
    { key: "constraints", label: "KEEP IN MIND", icon: "clock", style: "constraint", empty: "No customer constraint was recalled. Confirm constraints with the customer before acting." },
  ];
  container.innerHTML = cards.map((card) => {
    const entries = sections[card.key] || [];
    const body = entries.length
      ? entries.slice(0, 2).map((entry, index) =>
        `<p>${escapeHtml(entry.content)} <span class="brief-source">H-${String(index + 1).padStart(2, "0")}</span></p>
         <span class="brief-provenance">${escapeHtml(entry.source || "Hindsight memory")}${entry.outcome ? ` · ${escapeHtml(entry.outcome)}` : ""}</span>`
      ).join("")
      : `<p class="empty-memory">${escapeHtml(card.empty)}</p>`;
    const unverified = card.key === "checks" && entries.some((entry) => (entry.outcome || "").toLowerCase() === "unverified");
    return `<div class="brief-section">
      <div class="brief-section-heading"><span class="brief-icon ${card.style}">${icon(card.icon)}</span><span>${card.label}</span>${unverified ? '<span class="unverified-pill">UNVERIFIED</span>' : ""}</div>
      ${body}
    </div>`;
  }).join("");
  const ring = $(".ring-value");
  if (ring) ring.style.strokeDasharray = `${Math.min(total, 4) / 4 * 82}, 100`;
}

async function loadState() {
  try {
    const data = await request("/api/state");
    state.mode = data.mode;
    state.provider = data.provider;
    renderTimeline(data.events || []);
    renderActivity(data.activity || []);
    if (data.mode === "hindsight") {
      $("#memory-count").textContent = "Awaiting Hindsight recall";
    }
  } catch (error) {
    toast(error.message, true);
  }
}

async function checkHealth() {
  try {
    const data = await request("/api/health");
    state.mode = data.mode;
    setProviderBadge(data.provider, false, data.mode === "hindsight");
  } catch (error) {
    setProviderBadge("Hindsight", true);
    $("#provider-foot").textContent = error.message;
  }
}

async function recall(query, destination) {
  const data = await request("/api/recall", {
    method: "POST",
    body: JSON.stringify({ query, synthesize: destination === "answer" }),
  });
  setProviderBadge(data.provider);
  renderBrief(data);
  await loadState();
  if (destination === "answer") renderAnswer(data);
  return data;
}

function renderAnswer(data) {
  const panel = $("#answer-panel");
  const memories = data.memories || [];
  const text = data.answer || (memories.length
    ? memories.slice(0, 4).map((item) => item.content).join(" ")
    : "I couldn't recall relevant prior context for that question. No previous-shift facts are being inferred. Check the current ticket or retain a sourced shift note first.");
  const sources = memories.length
    ? memories.slice(0, 4).map((item) => escapeHtml(item.source || "Memory result")).join(" · ")
    : "No relevant memories returned";
  panel.innerHTML = `<div class="answer-label">${icon("spark")} ${escapeHtml(data.answer_kind || "RECALL RESULTS")} · ${escapeHtml(data.provider)}</div>
    <p>${escapeHtml(text)}</p><div class="answer-source">Sources: ${sources}</div>`;
  panel.hidden = false;
}

async function openCompare() {
  const modal = $("#compare-modal");
  const result = $("#compare-results");
  modal.hidden = false;
  document.body.style.overflow = "hidden";
  result.innerHTML = '<div class="compare-loading"><span class="loading-dot"></span> Recalling the incident…</div>';
  try {
    const data = await request("/api/compare", {
      method: "POST",
      body: JSON.stringify({ query: "What should I know before taking over Acme Logistics incident INC-2048?" }),
    });
    setProviderBadge(data.provider);
    const facts = (data.memory_on.memories || []).slice(0, 4);
    const localLabel = data.provider === "Hindsight" ? "REAL HINDSIGHT RECALL" : "LOCAL DEMO · NOT HINDSIGHT";
    const factContent = facts.length
      ? facts.map((item) => `<div class="compare-fact">${escapeHtml(item.content)}<small>${escapeHtml(item.source || "Recalled memory")} · ${escapeHtml(item.outcome || "Remembered")}</small></div>`).join("")
      : '<p>No matching memories were returned. Seed the bank with the handoff events before comparing.</p>';
    result.innerHTML = `<article class="compare-column">
      <h3>Without memory <span>FRESH SESSION</span></h3>
      <p>${escapeHtml(data.memory_off.answer)}</p>
      <p>This side intentionally has no access to earlier shift events.</p>
    </article>
    <article class="compare-column memory-column">
      <h3>${escapeHtml(data.provider)} <span>${localLabel}</span></h3>
      ${factContent}
    </article>`;
    await loadState();
  } catch (error) {
    result.innerHTML = `<div class="empty-error">${escapeHtml(error.message)}</div>`;
    toast(error.message, true);
  }
}

function showModal(id) {
  $(id).hidden = false;
  document.body.style.overflow = "hidden";
  const firstField = $("textarea, input, select", $(id));
  if (firstField) window.setTimeout(() => firstField.focus(), 30);
}

function closeModal(id) {
  $(id).hidden = true;
  if ($("#memory-modal").hidden && $("#compare-modal").hidden) document.body.style.overflow = "";
}

function closeVisibleModals() {
  closeModal("#memory-modal");
  closeModal("#compare-modal");
}

$("#add-memory").addEventListener("click", () => showModal("#memory-modal"));
$("#close-modal").addEventListener("click", () => closeModal("#memory-modal"));
$("#cancel-modal").addEventListener("click", () => closeModal("#memory-modal"));
$("#close-compare").addEventListener("click", () => closeModal("#compare-modal"));
$("#compare-button").addEventListener("click", openCompare);
$("#compare-nav").addEventListener("click", openCompare);
$("#seed-history").addEventListener("click", async () => {
  const button = $("#seed-history");
  button.disabled = true;
  try {
    const data = await request("/api/seed", { method: "POST", body: "{}" });
    toast(data.message);
    await Promise.all([loadState(), recall("Acme Logistics INC-2048 customer constraint failed replay safe check", "brief")]);
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
});
$("#jump-brief").addEventListener("click", () => $("#handoff-brief").scrollIntoView({ behavior: "smooth", block: "start" }));
$("#show-trail").addEventListener("click", () => $("#memory").scrollIntoView({ behavior: "smooth", block: "center" }));
$("#refresh-state").addEventListener("click", async () => {
  await Promise.all([loadState(), recall("Acme Logistics INC-2048 customer constraint failed replay safe next check", "brief")]);
  toast("Incident and memory trail refreshed.");
});

$("#memory-modal").addEventListener("click", (event) => {
  if (event.target === $("#memory-modal")) closeModal("#memory-modal");
});
$("#compare-modal").addEventListener("click", (event) => {
  if (event.target === $("#compare-modal")) closeModal("#compare-modal");
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeVisibleModals();
});

$("#memory-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $('button[type="submit"]', event.currentTarget);
  button.disabled = true;
  try {
    const data = await request("/api/retain", {
      method: "POST",
      body: JSON.stringify({
        content: $("#memory-content").value.trim(),
        category: $("#memory-category").value,
        source: $("#memory-source").value.trim(),
        outcome: $("#memory-outcome").value,
      }),
    });
    closeModal("#memory-modal");
    event.currentTarget.reset();
    $("#memory-source").value = "Operator note · INC-2048";
    toast(`Retained by ${data.provider}.`);
    await Promise.all([loadState(), recall("Acme Logistics INC-2048 customer constraint failed replay next safe check", "brief")]);
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
});

$("#ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("#ask-input");
  const query = input.value.trim();
  if (!query) {
    toast("Enter a handoff question first.", true);
    input.focus();
    return;
  }
  const form = event.currentTarget;
  form.classList.add("is-loading");
  try {
    await recall(query, "answer");
  } catch (error) {
    toast(error.message, true);
  } finally {
    form.classList.remove("is-loading");
  }
});

$$(".suggested-questions button").forEach((button) => {
  button.addEventListener("click", async () => {
    const query = button.dataset.question;
    $("#ask-input").value = query;
    $("#ask-form").classList.add("is-loading");
    try {
      await recall(query, "answer");
    } catch (error) {
      toast(error.message, true);
    } finally {
      $("#ask-form").classList.remove("is-loading");
    }
  });
});

$$(".outcome-choice").forEach((button) => {
  button.addEventListener("click", () => {
    state.selectedOutcome = button.dataset.outcome;
    $$(".outcome-choice").forEach((choice) => choice.classList.toggle("selected", choice === button));
  });
});

$("#outcome-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const note = $("#outcome-note").value.trim();
  if (!note) {
    toast("Describe what happened before saving this outcome.", true);
    $("#outcome-note").focus();
    return;
  }
  const button = $('button[type="submit"]', event.currentTarget);
  button.disabled = true;
  try {
    const data = await request("/api/outcome", {
      method: "POST",
      body: JSON.stringify({ outcome: state.selectedOutcome, note }),
    });
    $("#outcome-note").value = "";
    toast(`Outcome retained by ${data.provider}.`);
    await Promise.all([loadState(), recall("Acme Logistics INC-2048 latest operator-confirmed outcome and handoff", "brief")]);
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
});

$("#share-button").addEventListener("click", async () => {
  const brief = [
    "SHIFTLINE HANDOFF · INC-2048 · Acme Logistics",
    "",
    "Customer impact: Duplicate webhook events on live orders.",
    "Verified: Duplicates began after a replay at 14:32 UTC.",
    "Constraint: Do not rotate the signing secret before Friday.",
    "Avoid: Replaying the affected batch increased duplicates.",
    "Next check: Compare delivery IDs and idempotency keys; still unverified.",
    "",
    "Synthetic walkthrough data. Verify source context before action.",
  ].join("\n");
  try {
    await navigator.clipboard.writeText(brief);
    toast("Handoff copied to clipboard.");
  } catch {
    toast("Clipboard access was denied by the browser.", true);
  }
});

$("#mobile-menu").addEventListener("click", () => $("#sidebar").classList.toggle("mobile-open"));

async function boot() {
  await Promise.all([checkHealth(), loadState()]);
  try {
    const data = await request("/api/brief?q=Acme%20Logistics%20INC-2048%20customer%20constraint%20failed%20replay%20safe%20check");
    setProviderBadge(data.provider);
    renderBrief(data);
    await loadState();
  } catch (error) {
    $("#brief-sections").innerHTML = `<div class="empty-error">${escapeHtml(error.message)}</div>`;
    toast(error.message, true);
  }
}

boot();
