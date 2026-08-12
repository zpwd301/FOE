/* global CONTRIBUTION_SUMMARY */
(function () {
  "use strict";

  const data = window.CONTRIBUTION_SUMMARY;
  if (!data || !data.periods) return;

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const fmt = new Intl.NumberFormat("en-US");
  const dateFmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });
  const timestampFmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  const leaderCelebrations = {
    "WMonkey the Fuzzy": ["🐒", "🐵", "🙈", "🙉", "🙊"],
    zpwd: ["😊"],
    "Seleukus the Hard": ["🦆"],
    "Trinity-Primrose": ["🌸", "🌼", "🌺", "🌷", "🌻"],
    "3 Point": ["⛺", "🦌"],
    "Justin 2556": ["🐈‍⬛"],
  };
  const sessionUnlockKey = "goe-contribution-unlocked-members-v1";
  const detailCache = new Map();
  const unlockedMembers = (() => {
    try {
      const stored = JSON.parse(window.sessionStorage.getItem(sessionUnlockKey) || "[]");
      return new Set(Array.isArray(stored) ? stored.map(String) : []);
    } catch (error) {
      return new Set();
    }
  })();
  let selectedRange = "30";
  let pendingProducerId = "";
  let activeLeaderCelebration = null;

  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
  const plural = (count, singular) => `${fmt.format(count)} ${count === 1 ? singular : `${singular}s`}`;
  const eraName = (era) => String(era).replace(/^\d+\s*-\s*/, "");
  const sourceName = (message) => message === "Guild treasury donation" ? "Direct contribution" : message;
  const selectedPeriod = () => data.periods[selectedRange];

  function rememberUnlockedMember(playerId) {
    unlockedMembers.add(String(playerId));
    try {
      window.sessionStorage.setItem(sessionUnlockKey, JSON.stringify([...unlockedMembers]));
    } catch (error) {
      // The in-memory set still avoids repeat prompts until this page unloads.
    }
  }

  function periodLabel(period = selectedPeriod()) {
    const start = new Date(`${period.startDate}T00:00:00`);
    const end = new Date(`${period.endDate}T00:00:00`);
    return `${dateFmt.format(start)} to ${dateFmt.format(end)}`;
  }

  function detailRecordsInPeriod(rows) {
    const period = selectedPeriod();
    return rows.filter((row) => {
      const date = String(row[0]).slice(0, 10);
      return date >= period.startDate && date <= period.endDate;
    });
  }

  function renderBreakdown(groups, total, formatter = (value) => value, usage = false) {
    return groups.slice(0, 8).map(([label, amount]) => `<li><span><strong>${escapeHtml(formatter(label))}</strong><small>${(amount / Math.max(total, 1) * 100).toFixed(1)}%${usage ? " of usage" : ""}</small></span><strong${usage ? ' class="negative"' : ""}>${usage ? "−" : ""}${fmt.format(amount)}</strong></li>`).join("");
  }

  function updateLeaderEasterEgg(leader) {
    const card = $("#leading-producer-card");
    activeLeaderCelebration = leader ? leaderCelebrations[leader.name] || null : null;
    if (activeLeaderCelebration) {
      card.setAttribute("role", "button");
      card.setAttribute("tabindex", "0");
      card.setAttribute("aria-label", `Celebrate ${leader.name}, leading contributor`);
    } else {
      card.removeAttribute("role");
      card.removeAttribute("tabindex");
      card.removeAttribute("aria-label");
    }
  }

  function launchLeaderConfetti() {
    if (!activeLeaderCelebration) return;
    const card = $("#leading-producer-card");
    card.classList.remove("leader-celebration");
    void card.offsetWidth;
    card.classList.add("leader-celebration");
    window.setTimeout(() => card.classList.remove("leader-celebration"), 650);
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const bounds = card.getBoundingClientRect();
    const startX = bounds.left + bounds.width / 2;
    const startY = bounds.top + bounds.height / 2;
    const count = window.innerWidth < 600 ? 30 : 48;
    const fragment = document.createDocumentFragment();
    for (let index = 0; index < count; index += 1) {
      const emoji = document.createElement("span");
      const horizontalSpread = (Math.random() - 0.5) * Math.min(window.innerWidth * 0.9, 900);
      const drift = (Math.random() - 0.5) * 180;
      emoji.className = "leader-confetti";
      emoji.setAttribute("aria-hidden", "true");
      emoji.textContent = activeLeaderCelebration[index % activeLeaderCelebration.length];
      emoji.style.setProperty("--x-start", `${startX + (Math.random() - 0.5) * bounds.width * 0.65}px`);
      emoji.style.setProperty("--y-start", `${startY + (Math.random() - 0.5) * bounds.height * 0.45}px`);
      emoji.style.setProperty("--x-peak", `${startX + horizontalSpread}px`);
      emoji.style.setProperty("--y-peak", `${Math.max(18, startY - 130 - Math.random() * 260)}px`);
      emoji.style.setProperty("--x-end", `${startX + horizontalSpread + drift}px`);
      emoji.style.setProperty("--y-end", `${window.innerHeight + 70}px`);
      const spin = (Math.random() - 0.5) * 1080;
      emoji.style.setProperty("--spin-mid", `${spin * 0.45}deg`);
      emoji.style.setProperty("--spin", `${spin}deg`);
      emoji.style.setProperty("--delay", `${Math.random() * 250}ms`);
      emoji.style.setProperty("--duration", `${3600 + Math.random() * 1600}ms`);
      fragment.appendChild(emoji);
      window.setTimeout(() => emoji.remove(), 5800);
    }
    document.body.appendChild(fragment);
  }

  function renderSummary() {
    const period = selectedPeriod();
    const leader = period.producers[0];
    $("#production-total").textContent = fmt.format(period.total);
    $("#producer-count").textContent = fmt.format(period.producers.length);
    $("#daily-production").textContent = fmt.format(period.dailyAverage);
    $("#leading-producer").textContent = leader ? leader.name : "—";
    $("#leading-producer-total").textContent = leader ? `${fmt.format(leader.total)} goods contributed` : "No contributions in this period";
    $("#production-coverage").textContent = `${periodLabel(period)} · ${plural(period.recordCount, "contribution record")} available`;
    updateLeaderEasterEgg(leader);
  }

  function renderProducers() {
    const period = selectedPeriod();
    const search = $("#producer-search").value.trim().toLocaleLowerCase();
    const visible = search
      ? period.producers.filter((producer) => producer.name.toLocaleLowerCase().includes(search))
      : period.producers.slice(0, 10);
    const rankById = new Map(period.producers.map((producer, index) => [String(producer.id), index + 1]));
    const body = $("#producer-rows");
    body.innerHTML = visible.map((producer) => {
      const share = producer.total / Math.max(period.total, 1) * 100;
      return `<tr data-producer-id="${escapeHtml(producer.id)}" tabindex="0" aria-label="Open contribution details for ${escapeHtml(producer.name)}"><td><span class="producer-rank">${rankById.get(String(producer.id))}</span></td><td><strong>${escapeHtml(producer.name)}</strong></td><td class="production-value">${fmt.format(producer.total)}</td><td>${share.toFixed(1)}%</td><td>${fmt.format(producer.count)}</td><td>${escapeHtml(producer.topEra ? eraName(producer.topEra) : "—")}</td></tr>`;
    }).join("");
    $("#producer-empty").hidden = visible.length > 0;
    body.querySelectorAll("[data-producer-id]").forEach((row) => {
      row.addEventListener("click", () => openProducer(row.dataset.producerId));
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openProducer(row.dataset.producerId);
        }
      });
    });
  }

  function renderEras() {
    const period = selectedPeriod();
    const maximum = period.eras.length ? period.eras[0][1] : 1;
    $("#era-production-list").innerHTML = period.eras.map(([era, amount], index) => `<li><span class="era-production-rank">${index + 1}</span><span><strong>${escapeHtml(eraName(era))}</strong><small>${(amount / Math.max(period.total, 1) * 100).toFixed(1)}% of contributions</small><span class="era-production-bar" style="--era-width:${Math.max(3, amount / maximum * 100).toFixed(2)}%"></span></span><strong>${fmt.format(amount)}</strong></li>`).join("");
  }

  function renderProductionSummary(producer) {
    const period = selectedPeriod();
    $("#member-production-total").textContent = fmt.format(producer.total);
    $("#member-production-share").textContent = `${(producer.total / Math.max(period.total, 1) * 100).toFixed(1)}%`;
    $("#member-production-records").textContent = fmt.format(producer.count);
    $("#member-goods-list").innerHTML = renderBreakdown(producer.goods, producer.total);
    $("#member-eras-list").innerHTML = renderBreakdown(producer.eras, producer.total, eraName);
    $("#member-sources-list").innerHTML = renderBreakdown(producer.sources, producer.total, sourceName);
  }

  function resetProtectedDetails() {
    $("#producer-protected-details").hidden = true;
    $("#producer-detail-loading").hidden = true;
    $("#producer-detail-loading").classList.remove("is-error");
    $("#producer-usage").hidden = true;
    $("#producer-usage-empty").hidden = true;
    $("#producer-records").hidden = true;
    $("#member-usage-purpose-list").innerHTML = "";
    $("#member-usage-goods-list").innerHTML = "";
    $("#member-usage-era-list").innerHTML = "";
    $("#member-production-record-list").innerHTML = "";
    $("#producer-record-count").textContent = "";
  }

  async function loadMemberDetails(playerId) {
    const id = String(playerId);
    if (detailCache.has(id)) return detailCache.get(id);
    const url = data.details[id];
    if (!url) throw new Error("No detailed records are available for this member.");
    const request = window.fetch(url, { credentials: "same-origin" }).then((response) => {
      if (!response.ok) throw new Error(`Detailed record request failed with ${response.status}.`);
      return response.json();
    });
    detailCache.set(id, request);
    try {
      return await request;
    } catch (error) {
      detailCache.delete(id);
      throw error;
    }
  }

  function renderProductionRecords(detail) {
    const memberRecords = detailRecordsInPeriod(detail.records).filter((row) => Number(row[5]) > 0);
    const periodCount = Number(detail.contributionRecordCounts?.[selectedRange]) || memberRecords.length;
    const retainedNote = periodCount > memberRecords.length
      ? ` · newest ${fmt.format(memberRecords.length)} of ${fmt.format(periodCount)} for this period`
      : "";
    $("#producer-record-count").textContent = `${plural(memberRecords.length, "record")} shown${retainedNote}`;
    $("#member-production-record-list").innerHTML = memberRecords.map((row) => `<tr><td><time datetime="${escapeHtml(row[0])}">${escapeHtml(timestampFmt.format(new Date(row[0])))}</time></td><td><strong>${escapeHtml(row[4])}</strong></td><td>${escapeHtml(eraName(row[3]))}</td><td>${escapeHtml(sourceName(row[6]))}</td><td class="positive">+${fmt.format(row[5])}</td></tr>`).join("");
  }

  function renderUsageDetails(detail) {
    const usage = detail.usagePeriods?.[selectedRange] || {
      recordCount: 0,
      total: 0,
      purposes: [],
      goods: [],
      eras: [],
    };
    const usageSection = $("#producer-usage");
    const emptyState = $("#producer-usage-empty");
    usageSection.hidden = usage.recordCount === 0;
    emptyState.hidden = usage.recordCount > 0;
    if (usage.recordCount) {
      $("#member-usage-total").textContent = `−${fmt.format(usage.total)}`;
      $("#member-usage-count").textContent = plural(usage.recordCount, "usage record");
      $("#member-usage-purpose-list").innerHTML = renderBreakdown(usage.purposes, usage.total, (value) => value, true);
      $("#member-usage-goods-list").innerHTML = renderBreakdown(usage.goods, usage.total, (value) => value, true);
      $("#member-usage-era-list").innerHTML = renderBreakdown(usage.eras, usage.total, eraName, true);
    }
  }

  async function showProtectedDetails(playerId) {
    const id = String(playerId);
    const loading = $("#producer-detail-loading");
    $("#producer-validation").hidden = true;
    $("#producer-protected-details").hidden = false;
    loading.textContent = "Loading your detailed records…";
    loading.classList.remove("is-error");
    loading.hidden = false;
    $("#producer-usage").hidden = true;
    $("#producer-usage-empty").hidden = true;
    $("#producer-records").hidden = true;
    try {
      const detail = await loadMemberDetails(id);
      if (pendingProducerId !== id || !$("#producer-dialog").open) return;
      renderProductionRecords(detail);
      renderUsageDetails(detail);
      loading.hidden = true;
      $("#producer-records").hidden = false;
      $("#producer-protected-details").focus();
    } catch (error) {
      if (pendingProducerId !== id) return;
      loading.textContent = "We couldn’t load the detailed records. Close this panel and try again.";
      loading.classList.add("is-error");
      loading.hidden = false;
    }
  }

  function updateProducerDialog(producer) {
    $("#producer-dialog-title").textContent = producer.name;
    $("#producer-dialog-period").textContent = `Contribution summary for ${periodLabel()}. Detailed records require an assigned passcode.`;
    renderProductionSummary(producer);
  }

  function openProducer(playerId) {
    const id = String(playerId);
    const producer = selectedPeriod().producers.find((candidate) => String(candidate.id) === id);
    if (!producer) return;
    pendingProducerId = id;
    updateProducerDialog(producer);
    $("#producer-passcode").value = "";
    $("#producer-passcode").removeAttribute("aria-invalid");
    $("#producer-passcode-error").hidden = true;
    $("#producer-validation").hidden = false;
    resetProtectedDetails();
    $("#producer-dialog").showModal();
    if (unlockedMembers.has(id)) void showProtectedDetails(id);
  }

  function render() {
    $$('[data-production-range]').forEach((button) => {
      const active = button.dataset.productionRange === selectedRange;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    renderSummary();
    renderProducers();
    renderEras();
  }

  $$('[data-production-range]').forEach((button) => button.addEventListener("click", () => {
    selectedRange = button.dataset.productionRange;
    render();
    if ($("#producer-dialog").open && pendingProducerId) {
      const producer = selectedPeriod().producers.find((candidate) => String(candidate.id) === pendingProducerId);
      if (!producer) {
        $("#producer-dialog").close();
        return;
      }
      updateProducerDialog(producer);
      resetProtectedDetails();
      if (unlockedMembers.has(pendingProducerId)) void showProtectedDetails(pendingProducerId);
      else $("#producer-validation").hidden = false;
    }
  }));
  $("#producer-search").addEventListener("input", renderProducers);
  $("#leading-producer-card").addEventListener("click", launchLeaderConfetti);
  $("#leading-producer-card").addEventListener("keydown", (event) => {
    if (activeLeaderCelebration && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      launchLeaderConfetti();
    }
  });
  $("#producer-validation-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const passcode = $("#producer-passcode");
    if (passcode.value.trim() !== pendingProducerId) {
      passcode.setAttribute("aria-invalid", "true");
      $("#producer-passcode-error").hidden = false;
      passcode.focus();
      passcode.select();
      return;
    }
    passcode.removeAttribute("aria-invalid");
    $("#producer-passcode-error").hidden = true;
    rememberUnlockedMember(pendingProducerId);
    void showProtectedDetails(pendingProducerId);
  });
  $("#producer-passcode").addEventListener("input", () => {
    $("#producer-passcode").removeAttribute("aria-invalid");
    $("#producer-passcode-error").hidden = true;
  });
  $("#producer-dialog-close").addEventListener("click", () => $("#producer-dialog").close());
  $("#producer-dialog").addEventListener("click", (event) => {
    if (event.target === $("#producer-dialog")) $("#producer-dialog").close();
  });
  $("#producer-dialog").addEventListener("close", () => {
    pendingProducerId = "";
    $("#producer-validation").hidden = false;
    resetProtectedDetails();
  });
  render();
}());
