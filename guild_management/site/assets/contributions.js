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
  const adminMemberId = "855340115";
  const adminPasscode = "856444949🦆";
  // Player IDs keep celebrations attached to members when their display names change.
  const memberCelebrations = {
    "15316773": ["🏕", "🦌", "🎯"], // 3 Point
    "854838909": ["🏛️", "⚔️", "🛡️"], // 427troy
    "15707921": ["🌙", "💎", "✨"], // Aint2Lucid
    "850173136": ["🌹", "💗", "🌿"], // anitarose228
    "854199299": ["⚡", "🐞", "🪩"], // Arcadius2 ElectricBugalu
    "852925920": ["🥩", "🔥", "🥢"], // Bulgoki
    "853996216": ["⛵", "✂️", "🌊"], // Clipper
    "856372577": ["5️⃣", "🎲", "⭐"], // david5555
    "13880455": ["🐸", "🫎", "🧞"], // Fergus Ferguson
    "11336148": ["🔥", "🗡️", "8️⃣"], // Fireblade84
    "850068349": ["🎨", "🟢", "🖌️"], // Greenpaint9
    "20790356": ["🐷", "🎸", "🪨"], // hamstein
    "856227627": ["🎭"], // Jaqen Hghar
    "19531771": ["🎤", "🦇", "🤘"], // JOsborne32
    "856034122": ["🐈‍⬛"], // Justin 2556
    "852609056": ["👒", "🫖", "🌼"], // Little lady
    "856211546": ["🦊", "♟️", "👑"], // Livia 2135 the Cunning
    "855603707": ["🦎", "🎀", "✨"], // Lizzie1998
    "851256976": ["🐺", "👑", "🌫️"], // Lord Gray Wolf
    "855865172": ["🥀", "🗡️", "🖤"], // Melina 2169 the Cruel
    "857089839": ["🪞", "⚖️", "💫"], // Messalina 5303 the Fair
    "855901906": ["🤔", "💭", "🙃"], // Not well thought out
    "856604772": ["😺", "😸", "😹", "😼", "😻"], // oneye
    "855761769": ["🦨", "💨", "🌹"], // Pepe Le Pew II
    "856213206": ["💎", "👸", "🏹"], // Roxana 2195
    "856444949": ["🦆"], // Seleukus the Hard
    "14923207": ["🏍️", "💥", "🔥"], // Sir BackFire
    "15857412": ["🏦", "📈", "💰", "💵", "🥃"], // SirWalter929
    "14210627": ["🌲", "🥾", "🏕️"], // Theoutdoorsman71
    "19909277": ["🎣", "🐟", "🌊"], // Tiberius the Fisher
    "8629248": ["🚂", "2️⃣", "1️⃣"], // treyn21
    "13368644": ["🌸", "🌼", "🌺", "🌷", "🌻"], // Trinity-Primrose
    "2605963": ["♊", "✌️"], // Twogelius
    "849341420": ["⚖️", "📜", "⭐"], // Urania 1690 the Lawgiver
    "17463852": ["👑", "⚔️", "💐", "🫶"], // WARRIOR MOTHER1115
    "852268218": ["🤖", "🦾", "🛰️"], // WeRBorg
    "851889177": ["🐒", "🐵", "🙈", "🙉", "🙊"], // WMonkey the Fuzzy
    "855340115": ["😊"], // zpwd
  };
  const digitEmojis = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"];
  const sessionUnlockKey = "goe-contribution-unlocked-members-v2";
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
  const isAdminMember = (playerId) => String(playerId) === adminMemberId;
  const expectedPasscode = (playerId) => isAdminMember(playerId) ? adminPasscode : String(playerId);

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
    activeLeaderCelebration = leader
      ? memberCelebrations[String(leader.id)] || ["🎉", "✨", ...String(leader.id).split("").map((digit) => digitEmojis[Number(digit)]).filter(Boolean)]
      : null;
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

  function shuffledEmojiDeck(count) {
    const deck = Array.from({ length: count }, (_, index) => activeLeaderCelebration[index % activeLeaderCelebration.length]);
    for (let index = deck.length - 1; index > 0; index -= 1) {
      const swapIndex = Math.floor(Math.random() * (index + 1));
      [deck[index], deck[swapIndex]] = [deck[swapIndex], deck[index]];
    }
    return deck;
  }

  function distributedTargetSlots(count, launchCount) {
    const launchSlots = Array.from({ length: launchCount }, (_, index) => Math.round(index * (count - 1) / Math.max(launchCount - 1, 1)));
    const launchSet = new Set(launchSlots);
    const remainingSlots = Array.from({ length: count }, (_, index) => index).filter((index) => !launchSet.has(index));
    for (let index = remainingSlots.length - 1; index > 0; index -= 1) {
      const swapIndex = Math.floor(Math.random() * (index + 1));
      [remainingSlots[index], remainingSlots[swapIndex]] = [remainingSlots[swapIndex], remainingSlots[index]];
    }
    return [...launchSlots, ...remainingSlots];
  }

  function positionCelebrationParticle(particle, bounds, startX, startY, mobile, depth, targetSlot, targetCount) {
    const edgePadding = mobile ? 16 : 30;
    const slotWidth = (window.innerWidth - edgePadding * 2) / targetCount;
    const peakX = edgePadding + (targetSlot + 0.5) * slotWidth + (Math.random() - 0.5) * slotWidth * 0.55;
    const peakY = 18 + Math.random() * (mobile ? 100 : 125);
    const drift = (Math.random() - 0.5) * (mobile ? 70 : 140);
    const clampX = (value) => Math.max(edgePadding * 0.5, Math.min(window.innerWidth - edgePadding * 0.5, value));
    const middleX = clampX(peakX + drift * 0.48);
    const middleY = peakY + (window.innerHeight - peakY) * (0.3 + Math.random() * 0.18);
    const spin = (Math.random() - 0.5) * (depth === 0 ? 620 : 1080);
    particle.style.setProperty("--x-start", `${startX + (Math.random() - 0.5) * bounds.width * 0.55}px`);
    particle.style.setProperty("--y-start", `${startY + (Math.random() - 0.5) * bounds.height * 0.35}px`);
    particle.style.setProperty("--x-peak", `${peakX}px`);
    particle.style.setProperty("--y-peak", `${peakY}px`);
    particle.style.setProperty("--x-mid", `${middleX}px`);
    particle.style.setProperty("--y-mid", `${middleY}px`);
    particle.style.setProperty("--x-end", `${clampX(peakX + drift)}px`);
    particle.style.setProperty("--y-end", `${window.innerHeight + 70}px`);
    particle.style.setProperty("--x-linger", `${clampX(peakX + drift * 0.2)}px`);
    particle.style.setProperty("--y-linger", `${peakY + 20 + Math.random() * 42}px`);
    particle.style.setProperty("--spin-peak", `${spin * 0.22}deg`);
    particle.style.setProperty("--spin-mid", `${spin * 0.58}deg`);
    particle.style.setProperty("--spin", `${spin}deg`);
  }

  function launchReducedMotionCelebration(bounds, layer) {
    const fragment = document.createDocumentFragment();
    const count = Math.min(activeLeaderCelebration.length, 5);
    const radiusX = Math.min(bounds.width * 0.43, 130);
    const radiusY = Math.min(bounds.height * 0.42, 48);
    for (let index = 0; index < count; index += 1) {
      const angle = -Math.PI + (Math.PI * index / Math.max(count - 1, 1));
      const emoji = document.createElement("span");
      emoji.className = "leader-confetti leader-confetti--reduced";
      emoji.setAttribute("aria-hidden", "true");
      emoji.textContent = activeLeaderCelebration[index];
      emoji.style.setProperty("--x-rest", `${bounds.left + bounds.width / 2 + Math.cos(angle) * radiusX}px`);
      emoji.style.setProperty("--y-rest", `${bounds.top + bounds.height / 2 + Math.sin(angle) * radiusY}px`);
      emoji.style.setProperty("--delay", `${index * 70}ms`);
      fragment.appendChild(emoji);
    }
    layer.appendChild(fragment);
  }

  function launchLeaderConfetti() {
    if (!activeLeaderCelebration) return;
    const card = $("#leading-producer-card");
    const bounds = card.getBoundingClientRect();
    const startX = bounds.left + bounds.width / 2;
    const startY = bounds.top + bounds.height / 2;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    $(".leader-celebration-layer")?.remove();

    const layer = document.createElement("div");
    layer.className = "leader-celebration-layer";
    layer.setAttribute("aria-hidden", "true");
    if (reducedMotion) {
      launchReducedMotionCelebration(bounds, layer);
      document.body.appendChild(layer);
      window.setTimeout(() => layer.remove(), 1500);
      return;
    }

    const mobile = window.innerWidth < 600;
    const emojiCount = mobile ? 18 : 30;
    const sparkCount = mobile ? 8 : 12;
    const heroCount = mobile ? 2 : 3;
    const launchCount = Math.min(6, emojiCount);
    const targetCount = emojiCount + sparkCount;
    const targetSlots = distributedTargetSlots(targetCount, launchCount);
    const emojiDeck = shuffledEmojiDeck(emojiCount);
    const addEmoji = (fragment, index, immediate) => {
      const emoji = document.createElement("span");
      const depth = index % 3;
      emoji.className = `leader-confetti leader-confetti--emoji leader-confetti--depth-${depth}${index < heroCount ? " leader-confetti--hero" : ""}`;
      emoji.setAttribute("aria-hidden", "true");
      emoji.textContent = emojiDeck[index];
      emoji.style.setProperty("--particle-size", `${(mobile ? 18 : 22) + depth * 6 + Math.random() * (mobile ? 8 : 12)}px`);
      emoji.style.setProperty("--delay", immediate ? "0ms" : `${12 + Math.random() * 78}ms`);
      emoji.style.setProperty("--duration", `${index < heroCount ? 2500 + Math.random() * 500 : 2400 + depth * 300 + Math.random() * 500}ms`);
      positionCelebrationParticle(emoji, bounds, startX, startY, mobile, depth, targetSlots[index], targetCount);
      fragment.appendChild(emoji);
    };

    const launchFragment = document.createDocumentFragment();
    for (let index = 0; index < launchCount; index += 1) addEmoji(launchFragment, index, true);
    layer.appendChild(launchFragment);
    document.body.appendChild(layer);

    window.requestAnimationFrame(() => {
      if (!layer.isConnected) return;
      const fragment = document.createDocumentFragment();
      for (let index = launchCount; index < emojiCount; index += 1) addEmoji(fragment, index, false);
      for (let index = 0; index < sparkCount; index += 1) {
        const spark = document.createElement("span");
        const depth = index % 3;
        spark.className = `leader-confetti leader-confetti--spark leader-confetti--depth-${depth}`;
        spark.setAttribute("aria-hidden", "true");
        spark.textContent = index % 2 ? "✦" : "◆";
        spark.style.setProperty("--particle-size", `${7 + depth * 2 + Math.random() * 5}px`);
        spark.style.setProperty("--spark-color", index % 3 === 0 ? "#f0ca68" : index % 3 === 1 ? "#2f7b53" : "#fff2b8");
        spark.style.setProperty("--delay", `${20 + Math.random() * 100}ms`);
        spark.style.setProperty("--duration", `${2200 + depth * 280 + Math.random() * 450}ms`);
        positionCelebrationParticle(spark, bounds, startX, startY, mobile, depth, targetSlots[emojiCount + index], targetCount);
        fragment.appendChild(spark);
      }
      layer.appendChild(fragment);
    });
    window.setTimeout(() => layer.remove(), 4000);
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
    $("#era-production-list").innerHTML = period.eras.map(([era, amount], index) => {
      const contributors = ((period.eraContributors && period.eraContributors[era]) || []).slice(0, 3);
      const contributorRows = contributors.map((contributor, contributorIndex) => `<li><span><span class="era-contributor-rank">${contributorIndex + 1}</span><strong>${escapeHtml(contributor.name)}</strong></span><strong>${fmt.format(contributor.total)}</strong></li>`).join("");
      return `<li class="era-production-item"><details class="era-production-detail"><summary><span class="era-production-rank">${index + 1}</span><span class="era-production-summary"><strong>${escapeHtml(eraName(era))}</strong><small>${(amount / Math.max(period.total, 1) * 100).toFixed(1)}% of contributions</small><span class="era-production-bar" style="--era-width:${Math.max(3, amount / maximum * 100).toFixed(2)}%"></span></span><strong class="era-production-total">${fmt.format(amount)}</strong><span class="era-production-expander" aria-hidden="true"></span></summary><div class="era-contributors"><span>Top contributors in this period</span><ol>${contributorRows}</ol></div></details></li>`;
    }).join("");
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
    $("#producer-admin-usage").hidden = true;
    $("#producer-dialog").classList.remove("producer-dialog--admin");
    $("#producer-records").hidden = true;
    $("#member-usage-purpose-list").innerHTML = "";
    $("#member-usage-goods-list").innerHTML = "";
    $("#member-usage-era-list").innerHTML = "";
    $("#admin-usage-rows").innerHTML = "";
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

  function renderAdminGoods(goods) {
    const topGoods = goods.slice(0, 3).map(([good, amount]) => `${escapeHtml(good)} <strong>${fmt.format(amount)}</strong>`).join(" · ");
    const allGoods = goods.map(([good, amount]) => `<span><b>${escapeHtml(good)}</b><em>${fmt.format(amount)}</em></span>`).join("");
    return `<details class="admin-goods-detail"><summary><span>${topGoods || "No goods"}</span><small>${plural(goods.length, "good")} · expand all</small></summary><div class="admin-goods-cloud">${allGoods}</div></details>`;
  }

  function renderAdminUsage(detail) {
    const section = $("#producer-admin-usage");
    const usage = detail.adminUsagePeriods?.[selectedRange];
    $("#producer-dialog").classList.toggle("producer-dialog--admin", isAdminMember(detail.playerId) && Boolean(usage));
    if (!isAdminMember(detail.playerId) || !usage) {
      section.hidden = true;
      return;
    }
    section.hidden = false;
    $("#producer-admin-usage-period").textContent = `${periodLabel()} · grouped by member and purpose. Expand any goods mix to inspect every good.`;
    $("#admin-usage-total").textContent = `−${fmt.format(usage.total)}`;
    $("#admin-usage-player-count").textContent = fmt.format(usage.playerCount);
    $("#admin-usage-purpose-count").textContent = fmt.format(usage.purposeCount);
    $("#admin-usage-record-count").textContent = fmt.format(usage.recordCount);
    $("#admin-usage-rows").innerHTML = usage.rows.map((row) => {
      const share = row.total / Math.max(usage.total, 1) * 100;
      return `<tr><td><strong>${escapeHtml(row.playerName)}</strong></td><td><span class="admin-purpose">${escapeHtml(row.purpose)}</span></td><td class="admin-usage-value">−${fmt.format(row.total)}</td><td>${share.toFixed(1)}%</td><td>${fmt.format(row.recordCount)}</td><td>${renderAdminGoods(row.goods)}</td></tr>`;
    }).join("");
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
      renderAdminUsage(detail);
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
    const admin = isAdminMember(producer.id);
    $("#producer-dialog-title").textContent = producer.name;
    $("#producer-dialog-period").textContent = `Contribution summary for ${periodLabel()}. Detailed records require an assigned passcode.`;
    $("#producer-validation-title").textContent = "View recent detailed records";
    $("#producer-validation-copy").textContent = "Members can view their own most recent 500 contribution records by entering their assigned passcode.";
    $("#producer-passcode-label").textContent = "Assigned passcode";
    $("#producer-passcode-help").textContent = "Enter the passcode assigned to this member. Verification lasts for this browser session.";
    $("#producer-validation-submit").textContent = "View details";
    $("#producer-passcode").setAttribute("inputmode", admin ? "text" : "numeric");
    if (admin) $("#producer-passcode").removeAttribute("pattern");
    else $("#producer-passcode").setAttribute("pattern", "[0-9]*");
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
    if (passcode.value.trim() !== expectedPasscode(pendingProducerId)) {
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
