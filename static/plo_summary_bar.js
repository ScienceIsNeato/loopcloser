/**
 * _buildPloSummaryBar — PLO status distribution summary bar.
 *
 * Extracted from plo_dashboard.js to keep that file under the code-line limit.
 * Loaded as a plain script before plo_dashboard.js; exposes a single global
 * function used by PloDashboard._buildSummaryBar.
 *
 * @param {Array} plos - Array of PLO objects from the dashboard tree.
 * @returns {HTMLElement} A `.plo-summary-bar` div.
 */
function _buildPloSummaryBar(plos) {
  const bar = document.createElement("div");
  bar.className = "plo-summary-bar";
  if (!plos || plos.length === 0) return bar;

  const threshold = 70;
  const groups = { pass: [], fail: [], nodata: [] };
  plos.forEach((plo) => {
    const rate = plo.aggregate && plo.aggregate.pass_rate;
    if (rate === null || rate === undefined) groups.nodata.push(plo);
    else if (rate >= threshold) groups.pass.push(plo);
    else groups.fail.push(plo);
  });
  const total = plos.length;

  const addRow = (label, cls, ploList) => {
    if (ploList.length === 0) return;
    const row = document.createElement("div");
    row.className = "plo-summary-row " + cls;
    const stat = document.createElement("span");
    stat.className = "plo-summary-stat";
    const dot = document.createElement("span");
    dot.className = "plo-summary-dot";
    stat.appendChild(dot);
    stat.appendChild(document.createTextNode(ploList.length + " " + label));
    row.appendChild(stat);
    const sparkGroup = document.createElement("div");
    sparkGroup.className = "plo-summary-sparkline-group";
    ploList.forEach((plo) => {
      const slot = document.createElement("span");
      slot.className = "plo-summary-sparkline-slot";
      slot.dataset.ploId = plo.id;
      const slotLabel = document.createElement("span");
      slotLabel.className = "plo-summary-sparkline-label";
      slotLabel.textContent =
        plo.plo_number != null ? "(" + plo.plo_number + ")" : "";
      slot.appendChild(slotLabel);
      sparkGroup.appendChild(slot);
    });
    row.appendChild(sparkGroup);
    bar.appendChild(row);
  };
  addRow("satisfactory", "stat-pass", groups.pass);
  addRow("needs attention", "stat-fail", groups.fail);
  addRow("no data", "stat-nodata", groups.nodata);

  const progress = document.createElement("div");
  progress.className = "plo-summary-progress";
  const addSegment = (count, cls) => {
    if (count === 0) return;
    const seg = document.createElement("div");
    seg.className = "plo-summary-segment " + cls;
    seg.style.width = (count / total) * 100 + "%";
    progress.appendChild(seg);
  };
  addSegment(groups.pass.length, "seg-pass");
  addSegment(groups.fail.length, "seg-fail");
  addSegment(groups.nodata.length, "seg-nodata");
  bar.appendChild(progress);
  return bar;
}

// Export for Jest unit tests (plo_dashboard.test.js imports dashboard_utils
// which sets globals; this file is required separately in tests that need it).
if (typeof module !== "undefined" && module.exports) {
  module.exports = { _buildPloSummaryBar };
}
