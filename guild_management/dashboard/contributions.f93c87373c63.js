/* global CONTRIBUTION_DATA */
(function () {
  "use strict";

  const data = window.CONTRIBUTION_DATA;
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
  const allRecords = data.records.map((row) => ({ timestamp: row[0], playerId: row[1], playerName: row[2], era: row[3], good: row[4], amount: row[5], message: row[6], date: new Date(row[0]) }));
  const records = allRecords.filter((record) => record.amount > 0);
  const latestDate = new Date(data.meta.latestTimestamp);
  const sessionUnlockKey = "goe-contribution-unlocked-members-v1";
  const unlockedMembers = (() => {
    try {
      const stored = JSON.parse(window.sessionStorage.getItem(sessionUnlockKey) || "[]");
      return new Set(Array.isArray(stored) ? stored.map(String) : []);
    } catch (error) {
      return new Set();
    }
  })();
  let selectedRange = "all";
  let pendingProducerId = "";
  let activeLeaderCelebration = null;

  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
  const sum = (items) => items.reduce((total, item) => total + item.amount, 0);
  const plural = (count, singular) => `${fmt.format(count)} ${count === 1 ? singular : `${singular}s`}`;
  const eraName = (era) => era.replace(/^\d+\s*-\s*/, "");
  const sourceName = (message) => message === "Guild treasury donation" ? "Direct contribution" : message;

  function rememberUnlockedMember(playerId) {
    unlockedMembers.add(String(playerId));
    try {
      window.sessionStorage.setItem(sessionUnlockKey, JSON.stringify([...unlockedMembers]));
    } catch (error) {
      // The in-memory set still avoids repeat prompts until this page unloads.
    }
  }

  function recordsInPeriod(items) {
    if (selectedRange === "all") return items;
    const days = Number(selectedRange);
    const cutoff = new Date(latestDate);
    if (days === 1) {
      cutoff.setTime(latestDate.getTime() - 86400000);
    } else {
      cutoff.setHours(0, 0, 0, 0);
      cutoff.setDate(cutoff.getDate() - (days - 1));
    }
    return items.filter((record) => record.date >= cutoff);
  }

  const periodRecords = () => recordsInPeriod(records);

  function periodLabel(current = periodRecords()) {
    if (!current.length) return "the selected period";
    let start = current[current.length - 1].date;
    if (selectedRange !== "all") {
      const days = Number(selectedRange);
      start = new Date(latestDate);
      if (days === 1) {
        start.setTime(latestDate.getTime() - 86400000);
      } else {
        start.setHours(0, 0, 0, 0);
        start.setDate(start.getDate() - (days - 1));
      }
    }
    return `${dateFmt.format(start)} to ${dateFmt.format(latestDate)}`;
  }

  function groupBy(items, key) {
    const groups = new Map();
    items.forEach((item) => groups.set(item[key], (groups.get(item[key]) || 0) + item.amount));
    return [...groups.entries()].sort((a, b) => b[1] - a[1]);
  }

  function producersFor(items) {
    const producers = new Map();
    items.forEach((record) => {
      if (!producers.has(record.playerId)) producers.set(record.playerId, { id: record.playerId, name: record.playerName, total: 0, count: 0, records: [] });
      const producer = producers.get(record.playerId);
      producer.total += record.amount;
      producer.count += 1;
      producer.records.push(record);
    });
    return [...producers.values()].sort((a, b) => b.total - a.total || a.name.localeCompare(b.name));
  }

  function contributionDays(current) {
    if (selectedRange !== "all") return Number(selectedRange);
    return Math.max(1, new Set(current.map((record) => record.timestamp.slice(0, 10))).size);
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
    const current = periodRecords();
    const total = sum(current);
    const producers = producersFor(current);
    const leader = producers[0];
    $("#production-total").textContent = fmt.format(total);
    $("#producer-count").textContent = fmt.format(producers.length);
    $("#daily-production").textContent = fmt.format(Math.round(total / contributionDays(current)));
    $("#leading-producer").textContent = leader ? leader.name : "—";
    $("#leading-producer-total").textContent = leader ? `${fmt.format(leader.total)} goods contributed` : "No contributions in this period";
    $("#production-coverage").textContent = `${periodLabel(current)} · ${plural(current.length, "contribution record")} available`;
    updateLeaderEasterEgg(leader);
  }

  function renderProducers() {
    const current = periodRecords();
    const total = sum(current);
    const search = $("#producer-search").value.trim().toLocaleLowerCase();
    const allProducers = producersFor(current);
    const visible = search
      ? allProducers.filter((producer) => producer.name.toLocaleLowerCase().includes(search))
      : allProducers.slice(0, 10);
    const body = $("#producer-rows");
    body.innerHTML = visible.map((producer, index) => {
      const rank = allProducers.findIndex((candidate) => candidate.id === producer.id) + 1;
      const topEra = groupBy(producer.records, "era")[0];
      const share = total ? producer.total / total * 100 : 0;
      return `<tr data-producer-index="${index}" tabindex="0" aria-label="Open contribution details for ${escapeHtml(producer.name)}"><td><span class="producer-rank">${rank}</span></td><td><strong>${escapeHtml(producer.name)}</strong></td><td class="production-value">${fmt.format(producer.total)}</td><td>${share.toFixed(1)}%</td><td>${fmt.format(producer.count)}</td><td>${escapeHtml(topEra ? eraName(topEra[0]) : "—")}</td></tr>`;
    }).join("");
    $("#producer-empty").hidden = visible.length > 0;
    body.querySelectorAll("[data-producer-index]").forEach((row) => {
      const producer = visible[Number(row.dataset.producerIndex)];
      row.addEventListener("click", () => openProducer(producer.id));
      row.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openProducer(producer.id); } });
    });
  }

  function renderEras() {
    const current = periodRecords();
    const total = sum(current);
    const eras = groupBy(current, "era").slice(0, 8);
    const maximum = eras.length ? eras[0][1] : 1;
    $("#era-production-list").innerHTML = eras.map(([era, amount], index) => `<li><span class="era-production-rank">${index + 1}</span><span><strong>${escapeHtml(eraName(era))}</strong><small>${(amount / Math.max(total, 1) * 100).toFixed(1)}% of contributions</small><span class="era-production-bar" style="--era-width:${Math.max(3, amount / maximum * 100).toFixed(2)}%"></span></span><strong>${fmt.format(amount)}</strong></li>`).join("");
  }

  function renderBreakdown(items, key, formatter = (value) => value) {
    const total = sum(items);
    return groupBy(items, key).slice(0, 8).map(([label, amount]) => `<li><span><strong>${escapeHtml(formatter(label))}</strong><small>${(amount / Math.max(total, 1) * 100).toFixed(1)}%</small></span><strong>${fmt.format(amount)}</strong></li>`).join("");
  }

  function renderUsageBreakdown(items, key, formatter = (value) => value) {
    const total = items.reduce((value, record) => value + Math.abs(record.amount), 0);
    const groups = new Map();
    items.forEach((record) => groups.set(record[key], (groups.get(record[key]) || 0) + Math.abs(record.amount)));
    return [...groups.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8).map(([label, amount]) => `<li><span><strong>${escapeHtml(formatter(label))}</strong><small>${(amount / Math.max(total, 1) * 100).toFixed(1)}% of usage</small></span><strong class="negative">−${fmt.format(amount)}</strong></li>`).join("");
  }

  function openProducer(playerId) {
    const current = periodRecords();
    const memberRecords = current.filter((record) => record.playerId === playerId);
    if (!memberRecords.length) return;
    pendingProducerId = playerId;
    $("#producer-dialog-title").textContent = memberRecords[0].playerName;
    $("#producer-dialog-period").textContent = `Contribution summary for ${periodLabel(current)}. Detailed records require an assigned passcode.`;
    renderProductionSummary(playerId);
    $("#producer-passcode").value = "";
    $("#producer-passcode").removeAttribute("aria-invalid");
    $("#producer-passcode-error").hidden = true;
    $("#producer-validation").hidden = false;
    $("#producer-protected-details").hidden = true;
    $("#producer-usage").hidden = true;
    $("#producer-usage-empty").hidden = true;
    $("#member-usage-purpose-list").innerHTML = "";
    $("#member-usage-goods-list").innerHTML = "";
    $("#member-usage-era-list").innerHTML = "";
    $("#member-production-record-list").innerHTML = "";
    $("#producer-record-count").textContent = "";
    const isUnlocked = unlockedMembers.has(String(playerId));
    $("#producer-validation").hidden = isUnlocked;
    $("#producer-protected-details").hidden = !isUnlocked;
    if (isUnlocked) {
      renderProductionRecords(playerId);
      renderUsageDetails(playerId);
    }
    $("#producer-dialog").showModal();
  }

  function renderProductionSummary(playerId) {
    const current = periodRecords();
    const memberRecords = current.filter((record) => record.playerId === playerId);
    const total = sum(current);
    const memberTotal = sum(memberRecords);
    $("#member-production-total").textContent = fmt.format(memberTotal);
    $("#member-production-share").textContent = `${(memberTotal / Math.max(total, 1) * 100).toFixed(1)}%`;
    $("#member-production-records").textContent = fmt.format(memberRecords.length);
    $("#member-goods-list").innerHTML = renderBreakdown(memberRecords, "good");
    $("#member-eras-list").innerHTML = renderBreakdown(memberRecords, "era", eraName);
    $("#member-sources-list").innerHTML = renderBreakdown(memberRecords, "message", sourceName);
  }

  function renderProductionRecords(playerId) {
    const memberRecords = periodRecords().filter((record) => record.playerId === playerId);
    $("#producer-record-count").textContent = plural(memberRecords.length, "record");
    $("#member-production-record-list").innerHTML = memberRecords.map((record) => `<tr><td><time datetime="${escapeHtml(record.timestamp)}">${escapeHtml(timestampFmt.format(record.date))}</time></td><td><strong>${escapeHtml(record.good)}</strong></td><td>${escapeHtml(eraName(record.era))}</td><td>${escapeHtml(sourceName(record.message))}</td><td class="positive">+${fmt.format(record.amount)}</td></tr>`).join("");
  }

  function renderUsageDetails(playerId) {
    const usageRecords = recordsInPeriod(allRecords).filter((record) => record.playerId === playerId && record.amount < 0);
    const usageSection = $("#producer-usage");
    const emptyState = $("#producer-usage-empty");
    usageSection.hidden = usageRecords.length === 0;
    emptyState.hidden = usageRecords.length > 0;
    if (usageRecords.length) {
      const usageTotal = usageRecords.reduce((value, record) => value + record.amount, 0);
      $("#member-usage-total").textContent = `−${fmt.format(Math.abs(usageTotal))}`;
      $("#member-usage-count").textContent = plural(usageRecords.length, "usage record");
      $("#member-usage-purpose-list").innerHTML = renderUsageBreakdown(usageRecords, "message");
      $("#member-usage-goods-list").innerHTML = renderUsageBreakdown(usageRecords, "good");
      $("#member-usage-era-list").innerHTML = renderUsageBreakdown(usageRecords, "era", eraName);
    } else {
      $("#member-usage-purpose-list").innerHTML = "";
      $("#member-usage-goods-list").innerHTML = "";
      $("#member-usage-era-list").innerHTML = "";
    }
    return usageRecords.length ? usageSection : emptyState;
  }

  function render() {
    $$('[data-production-range]').forEach((button) => { const active = button.dataset.productionRange === selectedRange; button.classList.toggle("active", active); button.setAttribute("aria-pressed", String(active)); });
    renderSummary();
    renderProducers();
    renderEras();
  }

  $$('[data-production-range]').forEach((button) => button.addEventListener("click", () => { selectedRange = button.dataset.productionRange; render(); }));
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
    renderProductionRecords(pendingProducerId);
    renderUsageDetails(pendingProducerId);
    $("#producer-validation").hidden = true;
    $("#producer-protected-details").hidden = false;
    $("#producer-protected-details").focus();
  });
  $("#producer-passcode").addEventListener("input", () => { $("#producer-passcode").removeAttribute("aria-invalid"); $("#producer-passcode-error").hidden = true; });
  $("#producer-dialog-close").addEventListener("click", () => $("#producer-dialog").close());
  $("#producer-dialog").addEventListener("click", (event) => { if (event.target === $("#producer-dialog")) $("#producer-dialog").close(); });
  $("#producer-dialog").addEventListener("close", () => { pendingProducerId = ""; $("#producer-validation").hidden = false; $("#producer-protected-details").hidden = true; $("#producer-usage").hidden = true; $("#producer-usage-empty").hidden = true; });
  render();
}());
