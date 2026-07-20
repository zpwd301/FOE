/* global TREASURY_DATA */
(function () {
  "use strict";
  const data = window.TREASURY_DATA;
  const $ = (selector) => document.querySelector(selector);
  const fmt = new Intl.NumberFormat("en-US");
  const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
  const dateFmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
  const shortDateFmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
  let selectedDays = 90;
  let sortMode = "delta";

  const asDate = (value) => new Date(`${value}T00:00:00Z`);
  const formatDate = (value, short = false) => (short ? shortDateFmt : dateFmt).format(asDate(value));
  const signed = (number) => `${number >= 0 ? "+" : "-"}${fmt.format(Math.abs(number))}`;
  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
  const ageNames = [...new Set(data.goods.map((good) => good.age))];
  const currentIndex = () => data.dates.length - 1;
  const startIndex = () => {
    const end = asDate(data.dates.at(-1));
    const cutoff = new Date(end);
    cutoff.setUTCDate(cutoff.getUTCDate() - (selectedDays - 1));
    const index = data.dates.findIndex((date) => asDate(date) >= cutoff);
    return index === -1 ? 0 : index;
  };
  const periodGoods = () => data.goods.map((good) => ({ ...good, start: good.values[startIndex()], current: good.values[currentIndex()], min: Math.min(...good.values.slice(startIndex())), delta: good.values[currentIndex()] - good.values[startIndex()] }));
  const sum = (values) => values.reduce((total, value) => total + value, 0);
  const totalAt = (index) => sum(data.goods.map((good) => good.values[index]));
  const totalSeries = () => data.dates.slice(startIndex()).map((date, offset) => ({ date, value: totalAt(startIndex() + offset) }));
  const ageRows = () => ageNames.map((age) => { const goods = periodGoods().filter((good) => good.age === age); return { age, goods, start: sum(goods.map((good) => good.start)), current: sum(goods.map((good) => good.current)), delta: sum(goods.map((good) => good.delta)) }; }).sort((a, b) => a.delta - b.delta);

  function drawLineChart(svg, series, color, fill) {
    const rect = svg.getBoundingClientRect(); const width = Math.max(300, Math.round(rect.width)); const height = Math.max(130, Math.round(rect.height));
    const pad = { top: 18, right: 12, bottom: 20, left: 52 }; const values = series.map((item) => item.value); const low = Math.min(...values); const high = Math.max(...values); const spread = Math.max(high - low, Math.max(high * .007, 1)); const min = low - spread * .2; const max = high + spread * .2;
    const x = (index) => pad.left + (index / Math.max(series.length - 1, 1)) * (width - pad.left - pad.right); const y = (value) => pad.top + (1 - (value - min) / (max - min)) * (height - pad.top - pad.bottom); const points = series.map((item, index) => `${x(index)},${y(item.value)}`).join(" ");
    const grid = [0, .5, 1].map((ratio) => { const value = min + (max - min) * ratio; const lineY = y(value); return `<line x1="${pad.left}" x2="${width - pad.right}" y1="${lineY}" y2="${lineY}" stroke="#ddd3bd"/><text x="0" y="${lineY + 4}" fill="#71695b" font-size="12">${compact.format(value)}</text>`; }).join("");
    const baseline = height - pad.bottom; const area = `${pad.left},${baseline} ${points} ${x(series.length - 1)},${baseline}`;
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.innerHTML = `${grid}<polygon points="${area}" fill="${fill}"/><polyline points="${points}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><circle cx="${x(0)}" cy="${y(series[0].value)}" r="4" fill="#fffdf6" stroke="${color}" stroke-width="2"/><circle cx="${x(series.length - 1)}" cy="${y(series[series.length - 1].value)}" r="4" fill="#fffdf6" stroke="${color}" stroke-width="2"/>`;
    return { x, y, width, height };
  }

  function renderTrend() {
    const series = totalSeries(); const svg = $("#trend-chart"); const chart = drawLineChart(svg, series, "#9c7b35", "rgba(156,123,53,.13)"); const tooltip = $("#chart-tooltip");
    $("#chart-start").textContent = formatDate(series[0].date, true); $("#chart-end").textContent = formatDate(series.at(-1).date, true); $("#trend-note").textContent = `${series.length} daily snapshots`;
    svg.onmousemove = (event) => { const bounds = svg.getBoundingClientRect(); const index = Math.round(((event.clientX - bounds.left) / bounds.width) * (series.length - 1)); const point = series[Math.max(0, Math.min(series.length - 1, index))]; tooltip.hidden = false; tooltip.textContent = `${formatDate(point.date, true)}  ${fmt.format(point.value)}`; tooltip.style.left = `${(chart.x(index) / chart.width) * 100}%`; tooltip.style.top = `${(chart.y(point.value) / chart.height) * 100}%`; };
    svg.onmouseleave = () => { tooltip.hidden = true; };
  }

  function renderOverview() {
    const series = totalSeries(); const first = series[0].value; const last = series.at(-1).value; const net = last - first; const elapsed = Math.max(1, Math.round((asDate(series.at(-1).date) - asDate(series[0].date)) / 86400000)); const goods = periodGoods(); const criticalGoods = goods.filter((good) => good.current < data.meta.lowStockThreshold).sort((a, b) => a.current - b.current); const weakAge = ageRows()[0];
    $("#total-value").textContent = fmt.format(last); $("#goods-count").textContent = `${data.goods.length} goods, Bronze Age excluded`;
    $("#net-value").textContent = signed(net); $("#net-value").className = net >= 0 ? "positive" : "negative"; $("#net-sub").textContent = `${(net / first * 100).toFixed(2)}% across selected period`;
    $("#pace-value").textContent = signed(Math.round(net / elapsed)); $("#pace-value").className = net >= 0 ? "positive" : "negative"; $("#pace-sub").textContent = "average net goods per day";
    const alert = $("#critical-alert");
    const hasCriticalGoods = criticalGoods.length > 0;
    alert.hidden = false;
    alert.classList.toggle("is-healthy", !hasCriticalGoods);
    alert.setAttribute("role", hasCriticalGoods ? "alert" : "status");
    $("#critical-mark").textContent = hasCriticalGoods ? "!" : "✓";
    $("#critical-label").textContent = hasCriticalGoods ? "Critical stock alert" : "Treasury status";
    if (criticalGoods.length) {
      const list = criticalGoods.map((good) => `${good.name} (${good.age}): ${fmt.format(good.current)}`).join(", ");
      const shortfall = sum(criticalGoods.map((good) => data.meta.lowStockThreshold - good.current));
      $("#critical-summary").textContent = `${list} in stock. ${fmt.format(shortfall)} needed to reach the ${fmt.format(data.meta.lowStockThreshold)} target.`;
      $("#critical-guidance").textContent = "GBG officers: Please avoid spending any good marked as critically low unless it is truly necessary. Donations to replenish low goods are greatly appreciated! ❤️";
    } else {
      $("#critical-summary").textContent = "Treasury thriving. Thank you, Guardians! ✨";
      $("#critical-guidance").textContent = "Every tracked good is safely above the critical threshold. Your steady contributions are keeping GoE prepared and prosperous. Fantastic teamwork!";
    }
    const best = [...goods].sort((a, b) => b.delta - a.delta)[0]; const weakest = [...goods].sort((a, b) => a.delta - b.delta)[0]; const lowest = [...goods].sort((a, b) => a.current - b.current)[0];
    $("#insights").innerHTML = `<div class="insight"><strong class="${weakAge.delta >= 0 ? "positive" : "negative"}">${signed(weakAge.delta)}</strong><span>${escapeHtml(weakAge.age)} is the weakest age group.</span><span class="insight-tag">AGE MOVEMENT</span></div><div class="insight"><strong class="positive">${escapeHtml(best.name)}</strong><span>Largest gain: ${signed(best.delta)} goods.</span><span class="insight-tag">BEST CONTRIBUTOR</span></div><div class="insight"><strong class="negative">${escapeHtml(weakest.name)}</strong><span>Largest draw: ${signed(weakest.delta)} goods.</span><span class="insight-tag">REFILL PRIORITY</span></div>`;
    $("#coverage-copy").textContent = `Showing ${series.length} days of available history, ${formatDate(series[0].date)} to ${formatDate(series.at(-1).date)}. Current lowest stock: ${lowest.name} at ${fmt.format(lowest.current)}.`;
  }

  function renderAges() {
    $("#age-list").innerHTML = ageRows().map((row) => `<button class="age-row" type="button" data-age="${escapeHtml(row.age)}"><span class="age-name">${escapeHtml(row.age)}</span><span class="age-stock">${fmt.format(row.current)} in stock</span><span class="age-delta ${row.delta >= 0 ? "positive" : "negative"}">${signed(row.delta)} <span aria-hidden="true">${row.delta >= 0 ? "&#8599;" : "&#8600;"}</span></span></button>`).join("");
    document.querySelectorAll("[data-age]").forEach((button) => button.addEventListener("click", () => openDetail(button.dataset.age)));
  }

  function renderGoods() {
    let goods = periodGoods();
    if (sortMode === "stock") goods.sort((a, b) => a.current - b.current); else if (sortMode === "gain") goods.sort((a, b) => b.delta - a.delta); else goods.sort((a, b) => a.delta - b.delta);
    $("#goods-list").innerHTML = goods.slice(0, 12).map((good) => `<tr><td><strong>${escapeHtml(good.name)}</strong></td><td>${escapeHtml(good.age)}</td><td class="${good.current < data.meta.lowStockThreshold ? "stock-low" : ""}">${fmt.format(good.current)}</td><td class="${good.delta >= 0 ? "positive" : "negative"}">${signed(good.delta)}</td><td>${fmt.format(good.min)}</td></tr>`).join("");
  }

  function openDetail(age) {
    const row = ageRows().find((item) => item.age === age); const series = data.dates.slice(startIndex()).map((date, index) => ({ date, value: sum(row.goods.map((good) => good.values[startIndex() + index])) }));
    $("#detail-title").textContent = age; $("#detail-summary").textContent = `${fmt.format(row.current)} goods in stock, ${signed(row.delta)} over the selected period.`; drawLineChart($("#detail-chart"), series, "#3c7556", "rgba(60,117,86,.13)");
    $("#detail-goods").innerHTML = [...row.goods].sort((a, b) => a.delta - b.delta).map((good) => `<tr><td><strong>${escapeHtml(good.name)}</strong></td><td class="${good.current < data.meta.lowStockThreshold ? "stock-low" : ""}">${fmt.format(good.current)}</td><td class="${good.delta >= 0 ? "positive" : "negative"}">${signed(good.delta)}</td><td>${fmt.format(good.min)}</td></tr>`).join("");
    $("#detail-dialog").showModal();
  }

  function render() {
    const usable = Math.min(selectedDays, data.dates.length); document.querySelectorAll("[data-range]").forEach((button) => button.classList.toggle("active", Number(button.dataset.range) === selectedDays));
    $("#trend-note").textContent = `${usable} daily snapshots`; renderOverview(); renderTrend(); renderAges(); renderGoods();
  }

  $("#as-of").textContent = `Data through ${formatDate(data.meta.latestDate)}`;
  document.querySelectorAll("[data-range]").forEach((button) => button.addEventListener("click", () => { selectedDays = Number(button.dataset.range); render(); }));
  $("#goods-sort").addEventListener("change", (event) => { sortMode = event.target.value; renderGoods(); }); $("#detail-close").addEventListener("click", () => $("#detail-dialog").close());
  window.addEventListener("resize", renderTrend); render();
}());
