    (() => {
      "use strict";

      const UNIT = 48;
      const PAD = UNIT * 1.15;
      const SIDE_COS = Math.cos(Math.PI / 6);
      const SIDE_SIN = Math.sin(Math.PI / 6);
      const SIDE_LABEL_BASE_INSET = 0.94;
      const SIDE_LABEL_MAX_INSET = 0.99;
      const SIDE_LABEL_MAX_HORIZONTAL_SHARE = 0.68;
      const LABEL_FIT_SAFETY = 0.9;
      const MAX_LABEL_SCREEN_SIZE = 18;
      const data = JSON.parse(document.getElementById("city-map-data").textContent);
      const svg = document.getElementById("city-map");
      const mapLayer = document.getElementById("map-layer");
      const unlockedLayer = document.getElementById("unlocked-layer");
      const buildingLayer = document.getElementById("building-layer");
      const details = document.getElementById("building-details");
      const searchInput = document.getElementById("building-search");
      const zoomStatus = document.getElementById("zoom-status");
      const rotationStatus = document.getElementById("rotation-status");
      const searchStatus = document.getElementById("search-status");
      const noRoadToggle = document.getElementById("no-road-toggle");

      const palette = {
        street:          { color: "#858a8f", label: "Road", text: "dark" },
        main_building:   { color: "#ffb000", label: "Town Hall", text: "dark" },
        greatbuilding:   { color: "#ed4f2a", label: "Great Building", text: "dark" },
        residential:     { color: "#6aaff0", label: "Residential", text: "dark" },
        production:      { color: "#4169e1", label: "Production", text: "light" },
        goods:           { color: "#8677e8", label: "Goods", text: "light" },
        military:        { color: "#ffffff", label: "Military", text: "dark" },
        culture:         { color: "#e58ab1", label: "Culture", text: "dark" },
        decoration:      { color: "#e58ab1", label: "Decoration", text: "dark" },
        tower:           { color: "#36aeba", label: "Tower", text: "dark" },
        diplomacy:       { color: "#a48bdd", label: "Diplomacy", text: "dark" },
        generic_building:{ color: "#713bc2", label: "Special Building", text: "light" },
        off_grid:        { color: "#51a89d", label: "Off-grid", text: "dark" },
        unknown:         { color: "#e9edf0", label: "Other", text: "dark" }
      };

      const state = {
        rotation: 45,
        viewBox: { x: 0, y: 0, width: 100, height: 100 },
        fitWidth: 100,
        panning: false,
        moved: false,
        pointerId: null,
        pressedBuildingIndex: null,
        pointerStartX: 0,
        pointerStartY: 0,
        lastX: 0,
        lastY: 0,
        selectedIndex: null,
        printViewBox: null,
        searchMatches: [],
        searchPosition: -1,
        highlightNoRoad: true
      };
      let labelScaleFrame = null;

      function safeType(type) {
        return Object.prototype.hasOwnProperty.call(palette, type) ? type : "unknown";
      }

      function displayType(type) {
        return palette[safeType(type)].label;
      }

      function brighterShade(hexColor, amount = 0.46) {
        const match = /^#([0-9a-f]{6})$/i.exec(hexColor);
        if (!match) return "#ffffff";
        const value = Number.parseInt(match[1], 16);
        const channels = [
          (value >> 16) & 255,
          (value >> 8) & 255,
          value & 255
        ].map(channel => Math.round(channel + (255 - channel) * amount));
        return `#${channels.map(channel => channel.toString(16).padStart(2, "0")).join("")}`;
      }

      function hoverShade(hexColor) {
        return hexColor.toLowerCase() === "#ffffff"
          ? "#eef6ff"
          : brighterShade(hexColor);
      }

      function setViewBox(next) {
        state.viewBox = next;
        svg.setAttribute("viewBox", `${next.x} ${next.y} ${next.width} ${next.height}`);
        const zoom = Math.round((state.fitWidth / next.width) * 100);
        zoomStatus.textContent = `${zoom}%`;
        scheduleLabelZoomCap();
      }

      function contentBounds() {
        const raw = data.stats.bounds;
        const x = raw.x * UNIT;
        const y = raw.y * UNIT;
        const width = raw.width * UNIT;
        const height = raw.length * UNIT;
        if (state.rotation === 0) {
          return { x, y, width, height };
        }
        const matrix = sideViewMatrix();
        const points = [
          [x, y],
          [x + width, y],
          [x + width, y + height],
          [x, y + height]
        ].map(([px, py]) => applyMatrix(matrix, px, py));
        const xs = points.map(point => point[0]);
        const ys = points.map(point => point[1]);
        const minX = Math.min(...xs);
        const minY = Math.min(...ys);
        return {
          x: minX,
          y: minY,
          width: Math.max(...xs) - minX,
          height: Math.max(...ys) - minY
        };
      }

      function fittedViewBox() {
        const bounds = contentBounds();
        let width = bounds.width + PAD * 2;
        let height = bounds.height + PAD * 2;
        const aspect = Math.max(0.2, svg.clientWidth / Math.max(1, svg.clientHeight));
        if (width / height < aspect) {
          width = height * aspect;
        } else {
          height = width / aspect;
        }
        return {
          x: bounds.x + bounds.width / 2 - width / 2,
          y: bounds.y + bounds.height / 2 - height / 2,
          width,
          height
        };
      }

      function fitMap() {
        const next = fittedViewBox();
        state.fitWidth = next.width;
        setViewBox(next);
      }

      function zoomAt(factor, clientX, clientY) {
        const rect = svg.getBoundingClientRect();
        const rx = clientX == null ? 0.5 : (clientX - rect.left) / rect.width;
        const ry = clientY == null ? 0.5 : (clientY - rect.top) / rect.height;
        const old = state.viewBox;
        const width = Math.min(state.fitWidth * 18, Math.max(state.fitWidth / 32, old.width / factor));
        const height = width * (old.height / old.width);
        const anchorX = old.x + old.width * rx;
        const anchorY = old.y + old.height * ry;
        setViewBox({
          x: anchorX - width * rx,
          y: anchorY - height * ry,
          width,
          height
        });
      }

      function centerBuilding(building) {
        const center = projectPoint(
          (building.x + building.width / 2) * UNIT,
          (building.y + building.length / 2) * UNIT
        );
        const targetWidth = Math.max(
          UNIT * 8,
          Math.max(building.width, building.length) * UNIT * 4.2
        );
        const aspect = svg.clientWidth / Math.max(1, svg.clientHeight);
        const width = Math.min(state.fitWidth, targetWidth);
        const height = width / aspect;
        setViewBox({
          x: center.x - width / 2,
          y: center.y - height / 2,
          width,
          height
        });
      }

      function sideViewMatrix() {
        const bounds = data.stats.bounds;
        const cx = (bounds.x + bounds.width / 2) * UNIT;
        const cy = (bounds.y + bounds.length / 2) * UNIT;
        const a = SIDE_COS;
        const b = SIDE_SIN;
        const c = -SIDE_COS;
        const d = SIDE_SIN;
        return {
          a,
          b,
          c,
          d,
          e: cx - (a * cx + c * cy),
          f: cy - (b * cx + d * cy)
        };
      }

      function applyMatrix(matrix, x, y) {
        return [
          matrix.a * x + matrix.c * y + matrix.e,
          matrix.b * x + matrix.d * y + matrix.f
        ];
      }

      function inverseSideLabelTransform(centerX, centerY) {
        const matrix = sideViewMatrix();
        const determinant = matrix.a * matrix.d - matrix.b * matrix.c;
        const a = matrix.d / determinant;
        const b = -matrix.b / determinant;
        const c = -matrix.c / determinant;
        const d = matrix.a / determinant;
        return `translate(${centerX} ${centerY}) matrix(${a} ${b} ${c} ${d} 0 0) translate(${-centerX} ${-centerY})`;
      }

      function sideLabelDimensions(width, height) {
        const shortEdge = Math.min(width, height);
        const longEdge = Math.max(width, height);
        const aspectRatio = longEdge / Math.max(1, shortEdge);
        const elongation = Math.min(1, Math.log2(aspectRatio) / 3);
        const inset = SIDE_LABEL_BASE_INSET
          + (SIDE_LABEL_MAX_INSET - SIDE_LABEL_BASE_INSET) * elongation;
        const horizontalShare = 0.5
          + (SIDE_LABEL_MAX_HORIZONTAL_SHARE - 0.5) * elongation;

        return {
          width: 2 * shortEdge * SIDE_COS * horizontalShare * inset,
          height: 2 * shortEdge * SIDE_SIN * (1 - horizontalShare) * inset
        };
      }

      function configureLabelBoxForView(labelBox) {
        const centerX = Number(labelBox.dataset.centerX);
        const centerY = Number(labelBox.dataset.centerY);
        const topX = Number(labelBox.dataset.topX);
        const topY = Number(labelBox.dataset.topY);
        const topWidth = Number(labelBox.dataset.topWidth);
        const topHeight = Number(labelBox.dataset.topHeight);

        if (state.rotation === 0) {
          labelBox.setAttribute("x", topX);
          labelBox.setAttribute("y", topY);
          labelBox.setAttribute("width", topWidth);
          labelBox.setAttribute("height", topHeight);
          labelBox.removeAttribute("transform");
          return;
        }

        // Allocate more horizontal room to elongated footprints while keeping
        // every corner within the isometric building boundary.
        const sideSize = sideLabelDimensions(topWidth, topHeight);
        const sideWidth = sideSize.width;
        const sideHeight = sideSize.height;
        labelBox.setAttribute("x", centerX - sideWidth / 2);
        labelBox.setAttribute("y", centerY - sideHeight / 2);
        labelBox.setAttribute("width", sideWidth);
        labelBox.setAttribute("height", sideHeight);
        labelBox.setAttribute("transform", inverseSideLabelTransform(centerX, centerY));
      }

      function projectPoint(x, y) {
        if (state.rotation === 0) return { x, y };
        const [projectedX, projectedY] = applyMatrix(sideViewMatrix(), x, y);
        return { x: projectedX, y: projectedY };
      }

      function setRotation(nextRotation) {
        state.rotation = nextRotation;
        if (state.rotation === 0) {
          mapLayer.removeAttribute("transform");
        } else {
          const matrix = sideViewMatrix();
          mapLayer.setAttribute(
            "transform",
            `matrix(${matrix.a} ${matrix.b} ${matrix.c} ${matrix.d} ${matrix.e} ${matrix.f})`
          );
        }
        document.querySelectorAll(".building-label-box").forEach(configureLabelBoxForView);
        svg.classList.toggle("is-side-view", state.rotation !== 0);
        const rotateButton = document.getElementById("rotate-map");
        const isSideView = state.rotation !== 0;
        rotateButton.setAttribute("aria-pressed", isSideView ? "true" : "false");
        rotateButton.textContent = isSideView ? "45° View" : "Top View";
        rotateButton.title = isSideView ? "Switch to top view" : "Switch to 45 degree side view";
        rotateButton.setAttribute(
          "aria-label",
          isSideView
            ? "Current view: 45 degree side view. Switch to top view"
            : "Current view: top view. Switch to 45 degree side view"
        );
        rotationStatus.textContent = isSideView ? "45° side view" : "top view";
        fitAllLabels();
        fitMap();
      }

      function showDetails(building, index, sticky = false) {
        if (sticky) {
          clearSelection(false);
          state.selectedIndex = index;
          const selected = document.querySelector(`[data-index="${index}"]`);
          selected?.classList.add("is-selected");
          selected?.setAttribute("aria-pressed", "true");
          if (selected) buildingLayer.appendChild(selected);
          applySelectedStroke(selected);
          svg.classList.add("has-selection");
        }
        document.getElementById("details-category").textContent = displayType(building.type);
        document.getElementById("details-name").textContent = building.name;
        const pieces = [
          `${building.length} × ${building.width} tiles (vertical × horizontal)`,
          `Grid ${building.x}, ${building.y}`
        ];
        if (building.level != null) pieces.push(`Level ${building.level}`);
        if (building.era) pieces.push(building.era.replace(/([a-z])([A-Z])/g, "$1 $2"));
        if (building.requiresRoad === false) pieces.push("No road required");
        if (building.requiresRoad === true) pieces.push("Road required");
        document.getElementById("details-meta").textContent = pieces.join(" · ");
        details.classList.add("is-visible");
      }

      function clearSelection(hidePanel = true) {
        state.selectedIndex = null;
        svg.classList.remove("has-selection");
        document.querySelectorAll(".building.is-selected").forEach(node => {
          node.classList.remove("is-selected");
          node.setAttribute("aria-pressed", "false");
          node.querySelector(".building-shape")?.style.removeProperty("stroke");
        });
        if (hidePanel) details.classList.remove("is-visible");
      }

      function selectionStrokeFor(buildingNode) {
        if (
          state.highlightNoRoad
          && buildingNode?.dataset.roadIndependent === "true"
        ) {
          return getComputedStyle(document.documentElement)
            .getPropertyValue("--no-road-selected")
            .trim() || "#e9d5ff";
        }
        return buildingNode?.dataset.selectionStroke || "#ffffff";
      }

      function applySelectedStroke(buildingNode) {
        if (!buildingNode) return;
        const shape = buildingNode.querySelector(".building-shape");
        shape?.style.setProperty("stroke", selectionStrokeFor(buildingNode));
      }

      function refreshSelectedStroke() {
        const selected = document.querySelector(".building.is-selected");
        applySelectedStroke(selected);
      }

      function toggleBuildingSelection(building, index) {
        if (state.selectedIndex === index) {
          clearSelection();
          return;
        }
        showDetails(building, index, true);
      }

      function hideDetails(index) {
        if (state.selectedIndex == null || state.selectedIndex === index) {
          if (state.selectedIndex == null) details.classList.remove("is-visible");
        }
      }

      function createSvgElement(name, attributes = {}) {
        const element = document.createElementNS("http://www.w3.org/2000/svg", name);
        for (const [key, value] of Object.entries(attributes)) {
          element.setAttribute(key, value);
        }
        return element;
      }

      function renderUnlockedAreas() {
        for (const area of data.unlockedAreas) {
          unlockedLayer.appendChild(createSvgElement("rect", {
            x: area.x * UNIT,
            y: area.y * UNIT,
            width: area.width * UNIT,
            height: area.length * UNIT,
            fill: "url(#tile-grid)"
          }));
        }
      }

      function renderBuildings() {
        data.buildings.forEach((building, index) => {
          const type = safeType(building.type);
          const style = palette[type];
          const x = building.x * UNIT;
          const y = building.y * UNIT;
          const width = building.width * UNIT;
          const height = building.length * UNIT;
          const roadIndependent = type !== "street" && building.requiresRoad === false;
          const selectionStroke = brighterShade(style.color);
          const hoverFill = hoverShade(style.color);
          const group = createSvgElement("g", {
            class: "building",
            tabindex: "0",
            role: "button",
            "aria-pressed": "false",
            "aria-label": `${building.name}, ${building.length} vertical by ${building.width} horizontal tiles${roadIndependent ? ", no road required" : ""}`,
            "data-index": index,
            "data-road-independent": roadIndependent ? "true" : "false",
            "data-selection-stroke": selectionStroke,
            "data-search": `${building.name} ${building.entityId}`.toLocaleLowerCase()
          });
          const shape = createSvgElement("rect", {
            class: "building-shape",
            x,
            y,
            width,
            height,
            fill: style.color
          });
          group.style.setProperty("--selection-stroke", selectionStroke);
          group.style.setProperty("--hover-fill", hoverFill);
          group.appendChild(shape);

          if (type !== "street") {
            const inset = Math.min(4, Math.max(1.5, Math.min(width, height) * 0.035));
            const labelBox = createSvgElement("foreignObject", {
              class: "building-label-box",
              x: x + inset,
              y: y + inset,
              width: width - inset * 2,
              height: height - inset * 2,
              "data-center-x": x + width / 2,
              "data-center-y": y + height / 2,
              "data-top-x": x + inset,
              "data-top-y": y + inset,
              "data-top-width": width - inset * 2,
              "data-top-height": height - inset * 2
            });
            const label = document.createElement("div");
            label.className = `building-label${style.text === "light" ? " light-text" : ""}`;
            const name = document.createElement("span");
            name.textContent = building.name;
            const dimensions = document.createElement("span");
            dimensions.className = "dimensions";
            dimensions.textContent = `${building.length}×${building.width}`;
            name.appendChild(dimensions);
            label.appendChild(name);
            labelBox.appendChild(label);
            group.appendChild(labelBox);
          }

          group.addEventListener("pointerenter", () => {
            if (state.selectedIndex == null) showDetails(building, index);
          });
          group.addEventListener("pointerleave", () => hideDetails(index));
          group.addEventListener("focus", () => showDetails(building, index));
          group.addEventListener("blur", () => hideDetails(index));
          group.addEventListener("dblclick", event => {
            event.stopPropagation();
            showDetails(building, index, true);
            centerBuilding(building);
          });
          group.addEventListener("keydown", event => {
            if (event.key !== "Enter" && event.key !== " ") return;
            event.preventDefault();
            event.stopPropagation();
            toggleBuildingSelection(building, index);
          });
          buildingLayer.appendChild(group);
        });
      }

      function fitLabel(label) {
        const labelBox = label.parentElement;
        const boxWidth = Number(labelBox.getAttribute("width"));
        const boxHeight = Number(labelBox.getAttribute("height"));
        const shortestSide = Math.min(boxWidth, boxHeight);
        const dynamicPadding = Math.min(4, Math.max(1, shortestSide * 0.045));
        label.style.padding = `${dynamicPadding.toFixed(2)}px`;

        const availableWidth = label.clientWidth;
        const availableHeight = label.clientHeight;
        if (availableWidth <= 0 || availableHeight <= 0) return;

        // Find the largest local font that fits, then keep a small buffer for
        // glyph overhang and browser rounding at the edges.
        let low = 1;
        let high = Math.max(1, Math.min(availableWidth, availableHeight) * 0.96);
        for (let iteration = 0; iteration < 16; iteration += 1) {
          const size = (low + high) / 2;
          label.style.fontSize = `${size}px`;
          if (label.scrollHeight <= label.clientHeight + 0.5 && label.scrollWidth <= label.clientWidth + 0.5) {
            low = size;
          } else {
            high = size;
          }
        }
        const fittedSize = Math.max(1, low * LABEL_FIT_SAFETY);
        label.style.fontSize = `${fittedSize.toFixed(2)}px`;
        label.dataset.fitFontSize = fittedSize.toFixed(2);
      }

      function fitAllLabels() {
        document.querySelectorAll(".building-label").forEach(fitLabel);
        scheduleLabelZoomCap();
      }

      function applyLabelZoomCap() {
        const scaleX = svg.clientWidth / Math.max(1, state.viewBox.width);
        const scaleY = svg.clientHeight / Math.max(1, state.viewBox.height);
        const mapScale = Math.max(0.001, Math.min(scaleX, scaleY));
        const localScreenCap = MAX_LABEL_SCREEN_SIZE / mapScale;

        document.querySelectorAll(".building-label").forEach(label => {
          const fittedSize = Number(label.dataset.fitFontSize);
          if (!Number.isFinite(fittedSize)) return;
          label.style.fontSize = `${Math.min(fittedSize, localScreenCap).toFixed(2)}px`;
        });
      }

      function scheduleLabelZoomCap() {
        if (labelScaleFrame !== null) return;
        labelScaleFrame = window.requestAnimationFrame(() => {
          labelScaleFrame = null;
          applyLabelZoomCap();
        });
      }

      function renderLegend() {
        const order = [
          "street", "main_building", "greatbuilding", "residential",
          "production", "goods", "military", "culture", "decoration",
          "tower", "diplomacy", "generic_building", "off_grid", "unknown"
        ];
        const counts = data.stats.categoryCounts;
        const container = document.getElementById("legend-items");
        for (const key of order) {
          const normalizedKey = key === "unknown"
            ? Object.keys(counts).filter(type => !palette[type]).reduce((sum, type) => sum + counts[type], 0)
            : counts[key];
          if (!normalizedKey) continue;
          const item = document.createElement("span");
          item.className = "legend-item";
          const swatch = document.createElement("span");
          swatch.className = "swatch";
          swatch.style.background = palette[key].color;
          const text = document.createElement("span");
          text.textContent = `${palette[key].label} ${normalizedKey}`;
          item.append(swatch, text);
          container.appendChild(item);
        }
        const roadEfficiency = new Intl.NumberFormat(undefined, {
          minimumFractionDigits: 0,
          maximumFractionDigits: 2
        }).format(data.stats.roadEfficiency);
        document.getElementById("legend-stats").textContent = [
          `${data.stats.buildingCount} buildings`,
          `${data.stats.roadTileCount} road tiles`,
          `${roadEfficiency}% road efficiency`,
          `${data.stats.freeTileCount} free tiles`
        ].join(" · ");
        document.getElementById("no-road-count").textContent =
          `(${data.stats.roadIndependentCount})`;
      }

      function setNoRoadHighlight(enabled) {
        state.highlightNoRoad = enabled;
        noRoadToggle.checked = enabled;
        svg.classList.toggle("highlight-no-road", enabled);
        refreshSelectedStroke();
      }

      function updateSearch(moveToMatch = false) {
        const query = searchInput.value.trim().toLocaleLowerCase();
        const nodes = [...document.querySelectorAll(".building")];
        if (!query) {
          nodes.forEach(node => node.classList.remove("is-dimmed"));
          state.searchMatches = [];
          state.searchPosition = -1;
          searchStatus.textContent = "";
          return;
        }
        state.searchMatches = [];
        nodes.forEach(node => {
          const isMatch = node.dataset.search.includes(query);
          node.classList.toggle("is-dimmed", !isMatch);
          if (isMatch) state.searchMatches.push(Number(node.dataset.index));
        });
        searchStatus.textContent = `${state.searchMatches.length} match${state.searchMatches.length === 1 ? "" : "es"}`;
        if (moveToMatch && state.searchMatches.length) {
          state.searchPosition = (state.searchPosition + 1) % state.searchMatches.length;
          const index = state.searchMatches[state.searchPosition];
          const building = data.buildings[index];
          showDetails(building, index, true);
          centerBuilding(building);
        }
      }

      renderUnlockedAreas();
      renderBuildings();
      renderLegend();
      document.getElementById("map-title").textContent = data.title;
      document.getElementById("map-subtitle").textContent =
        [data.subtitle, data.sourceFormat].filter(Boolean).join(" · ");
      document.getElementById("print-subtitle").textContent =
        [data.subtitle, "Generated 2026-07-25 14:09 EDT"].filter(Boolean).join(" · ");

      requestAnimationFrame(() => {
        setNoRoadHighlight(true);
        setRotation(45);
      });

      svg.addEventListener("wheel", event => {
        event.preventDefault();
        zoomAt(event.deltaY < 0 ? 1.16 : 1 / 1.16, event.clientX, event.clientY);
      }, { passive: false });

      svg.addEventListener("pointerdown", event => {
        if (event.button !== 0) return;
        state.panning = true;
        state.moved = false;
        state.pointerId = event.pointerId;
        const pressedBuilding = event.composedPath().find(
          node => node?.classList?.contains("building")
        );
        state.pressedBuildingIndex = pressedBuilding
          ? Number(pressedBuilding.dataset.index)
          : null;
        state.pointerStartX = event.clientX;
        state.pointerStartY = event.clientY;
        state.lastX = event.clientX;
        state.lastY = event.clientY;
        svg.setPointerCapture(event.pointerId);
        svg.classList.add("dragging");
      });

      svg.addEventListener("pointermove", event => {
        if (!state.panning || event.pointerId !== state.pointerId) return;
        const dx = event.clientX - state.lastX;
        const dy = event.clientY - state.lastY;
        if (
          Math.hypot(
            event.clientX - state.pointerStartX,
            event.clientY - state.pointerStartY
          ) > 4
        ) {
          state.moved = true;
        }
        const scaleX = state.viewBox.width / svg.clientWidth;
        const scaleY = state.viewBox.height / svg.clientHeight;
        setViewBox({
          ...state.viewBox,
          x: state.viewBox.x - dx * scaleX,
          y: state.viewBox.y - dy * scaleY
        });
        state.lastX = event.clientX;
        state.lastY = event.clientY;
      });

      function endPan(event, cancelled = false) {
        if (event.pointerId !== state.pointerId) return;
        const pressedBuildingIndex = state.pressedBuildingIndex;
        const shouldActivate = !cancelled && !state.moved;
        state.panning = false;
        svg.classList.remove("dragging");
        if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
        state.pointerId = null;
        state.pressedBuildingIndex = null;

        if (!shouldActivate) return;
        if (Number.isInteger(pressedBuildingIndex)) {
          toggleBuildingSelection(
            data.buildings[pressedBuildingIndex],
            pressedBuildingIndex
          );
        } else {
          clearSelection();
        }
      }

      svg.addEventListener("pointerup", endPan);
      svg.addEventListener("pointercancel", event => endPan(event, true));

      document.getElementById("zoom-in").addEventListener("click", () => zoomAt(1.25));
      document.getElementById("zoom-out").addEventListener("click", () => zoomAt(1 / 1.25));
      document.getElementById("fit-map").addEventListener("click", fitMap);
      document.getElementById("rotate-map").addEventListener("click", () => {
        setRotation(state.rotation === 0 ? 45 : 0);
      });
      noRoadToggle.addEventListener("change", () => {
        setNoRoadHighlight(noRoadToggle.checked);
      });
      document.getElementById("print-map").addEventListener("click", () => window.print());
      document.getElementById("search-button").addEventListener("click", () => updateSearch(true));
      searchInput.addEventListener("input", () => {
        state.searchPosition = -1;
        updateSearch(false);
      });
      searchInput.addEventListener("keydown", event => {
        if (event.key === "Enter") updateSearch(true);
        if (event.key === "Escape") {
          searchInput.value = "";
          updateSearch(false);
          searchInput.blur();
        }
      });

      window.addEventListener("resize", () => {
        window.clearTimeout(window.__cityMapResizeTimer);
        window.__cityMapResizeTimer = window.setTimeout(fitMap, 120);
      });

      window.addEventListener("beforeprint", () => {
        state.printViewBox = { ...state.viewBox };
        fitMap();
      });
      window.addEventListener("afterprint", () => {
        if (state.printViewBox) setViewBox(state.printViewBox);
        state.printViewBox = null;
      });

      document.addEventListener("keydown", event => {
        if (document.activeElement === searchInput) return;
        if (event.key === "+" || event.key === "=") zoomAt(1.25);
        if (event.key === "-") zoomAt(1 / 1.25);
        if (event.key === "0") fitMap();
        if (event.key.toLocaleLowerCase() === "r") setRotation(state.rotation === 0 ? 45 : 0);
        if (event.key.toLocaleLowerCase() === "p") window.print();
      });
    })();
