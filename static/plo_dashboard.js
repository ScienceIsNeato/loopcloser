/* global setLoadingState, setErrorState, setEmptyState, setSelectLoading, setSelectReady */
/**
 * PLO Dashboard — Program → PLO → CLO → section drilldown.
 *
 * Fetches the hierarchical tree from /api/programs/<id>/plo-dashboard and
 * renders it as a collapsible list.  Assessment badges honour the
 * per-program `assessment_display_mode` setting ("binary" | "percentage" |
 * "both"), which the user can change from the filter bar (persisted via
 * PUT /api/programs/<id>).
 *
 * Exports `PloDashboard` on globalThis for integration tests / other pages
 * and via module.exports for Jest unit tests.
 */

(function () {
  "use strict";

  const STORAGE_KEY_PROGRAM = "ploDashboard.lastProgramId";
  const DEFAULT_PASS_THRESHOLD = 70; // % at/above which a node is "S"

  /**
   * Render an assessment result as a short badge string.
   *
   * Display rule (see DESIGN_APPROACH.md):
   *  - mode "binary"     → "S" or "U"
   *  - mode "percentage" → "78%"
   *  - mode "both"       → "S (78%)" or "U (54%)"
   * When *passRate* is null (no data) returns "—" regardless of mode.
   */
  function formatAssessment(passRate, mode, threshold) {
    const t =
      typeof threshold === "number" ? threshold : DEFAULT_PASS_THRESHOLD;
    if (passRate === null || passRate === undefined) {
      return { text: "—", cssClass: "nodata" };
    }
    const isPass = passRate >= t;
    const binary = isPass ? "S" : "U";
    const pct = `${Math.round(passRate)}%`;

    let text;
    if (mode === "binary") {
      text = binary;
    } else if (mode === "percentage") {
      text = pct;
    } else {
      text = `${binary} (${pct})`;
    }
    return { text, cssClass: isPass ? "pass" : "fail" };
  }

  /** Pick a sensible default term: first active, else most-recent by start_date. */
  function pickDefaultTerm(terms) {
    if (!Array.isArray(terms) || terms.length === 0) return "";
    const active = terms.find(
      (t) =>
        t.term_status === "ACTIVE" ||
        t.status === "ACTIVE" ||
        t.is_active === true ||
        t.active === true,
    );
    if (active) return active.term_id || active.id || "";
    const sorted = [...terms].sort(
      (a, b) => new Date(b.start_date || 0) - new Date(a.start_date || 0),
    );
    return sorted[0].term_id || sorted[0].id || "";
  }

  const PloDashboard = {
    // ---- state ---------------------------------------------------------
    programs: [],
    terms: [],
    tree: null,
    currentProgramId: null,
    currentTermId: null,
    displayMode: "both",
    draftMappingId: null,

    // ---- cached DOM refs ----------------------------------------------
    _el: {},

    // ===================================================================
    // Bootstrap
    // ===================================================================
    init() {
      this._cacheSelectors();
      this._bindEvents();
      this._loadFilters().then(() => this.loadTree());
    },

    _cacheSelectors() {
      this._el = {
        programFilter: document.getElementById("ploProgramFilter"),
        termFilter: document.getElementById("ploTermFilter"),
        displayMode: document.getElementById("ploDisplayMode"),
        treeContainer: document.getElementById("ploTreeContainer"),
        programName: document.getElementById("ploTreeProgramName"),
        versionBadge: document.getElementById("ploTreeVersionBadge"),
        expandAllBtn: document.getElementById("expandAllBtn"),
        collapseAllBtn: document.getElementById("collapseAllBtn"),
        createPloBtn: document.getElementById("createPloBtn"),
        mapCloBtn: document.getElementById("mapCloBtn"),
        // modals
        ploModal: document.getElementById("ploModal"),
        ploForm: document.getElementById("ploForm"),
        ploModalId: document.getElementById("ploModalId"),
        ploModalNumber: document.getElementById("ploModalNumber"),
        ploModalNumberGroup: document.getElementById("ploModalNumberGroup"),
        ploModalDescription: document.getElementById("ploModalDescription"),
        ploModalLabel: document.getElementById("ploModalLabel"),
        ploModalAlert: document.getElementById("ploModalAlert"),
        mapCloModal: document.getElementById("mapCloModal"),
        mapCloForm: document.getElementById("mapCloForm"),
        mapCloModalPlo: document.getElementById("mapCloModalPlo"),
        mapCloModalClo: document.getElementById("mapCloModalClo"),
        mapCloModalAlert: document.getElementById("mapCloModalAlert"),
        mapCloPublishBtn: document.getElementById("mapCloPublishBtn"),
      };
    },

    _bindEvents() {
      const el = this._el;
      if (el.programFilter) {
        el.programFilter.addEventListener("change", () => {
          this.currentProgramId = el.programFilter.value;
          this._updateProgramActions();
          try {
            localStorage.setItem(STORAGE_KEY_PROGRAM, this.currentProgramId);
          } catch (_) {
            /* ignore storage quota / private-mode errors */
          }
          this.loadTree();
        });
      }
      if (el.termFilter) {
        el.termFilter.addEventListener("change", () => {
          this.currentTermId = el.termFilter.value;
          this.loadTree();
        });
      }
      if (el.displayMode) {
        el.displayMode.addEventListener("change", () => {
          this.displayMode = el.displayMode.value;
          this._persistDisplayMode();
          this._refreshBadges();
        });
      }
      if (el.expandAllBtn) {
        el.expandAllBtn.addEventListener("click", () => this._toggleAll(true));
      }
      if (el.collapseAllBtn) {
        el.collapseAllBtn.addEventListener("click", () =>
          this._toggleAll(false),
        );
      }
      if (el.createPloBtn) {
        el.createPloBtn.addEventListener("click", () => this._openPloModal());
      }
      if (el.mapCloBtn) {
        el.mapCloBtn.addEventListener("click", () => this._openMapCloModal());
      }
      if (el.ploForm) {
        el.ploForm.addEventListener("submit", (e) => this._submitPloForm(e));
      }
      if (el.mapCloForm) {
        el.mapCloForm.addEventListener("submit", (e) =>
          this._submitMapCloForm(e),
        );
      }
      if (el.mapCloPublishBtn) {
        el.mapCloPublishBtn.addEventListener("click", () =>
          this._publishDraft(),
        );
      }
    },

    // ===================================================================
    // Filter population
    // ===================================================================
    async _loadFilters() {
      // Show spinners on both dropdowns while fetching
      setSelectLoading(this._el.programFilter, "Loading programs…");
      setSelectLoading(this._el.termFilter, "Loading terms…");
      await Promise.all([this._loadPrograms(), this._loadTerms()]);
    },

    async _loadPrograms() {
      const sel = this._el.programFilter;
      try {
        const resp = await fetch("/api/programs", { credentials: "include" });
        if (!resp.ok) {
          setSelectReady(sel);
          return;
        }
        const data = await resp.json();
        this.programs = data.programs || [];
        setSelectReady(sel);
        sel.innerHTML = "";

        if (this.programs.length === 0) {
          const opt = document.createElement("option");
          opt.value = "";
          opt.textContent = "No programs found";
          sel.appendChild(opt);
          return;
        }

        // "All Programs" option for institution admins
        const allOpt = document.createElement("option");
        allOpt.value = "";
        allOpt.textContent = "All Programs";
        sel.appendChild(allOpt);

        this.programs.forEach((p) => {
          const opt = document.createElement("option");
          opt.value = p.program_id || p.id;
          opt.textContent = p.name;
          sel.appendChild(opt);
        });

        // Default program: last selected (localStorage) → "All Programs"
        let initial = null;
        try {
          initial = localStorage.getItem(STORAGE_KEY_PROGRAM);
        } catch (_storageErr) {
          /* ignore quota / private-mode errors */
        }
        const validIds = this.programs.map((p) => p.program_id || p.id);
        if (!initial || !validIds.includes(initial)) {
          initial = ""; // default to All Programs
        }
        sel.value = initial;
        this.currentProgramId = initial;
        this._updateProgramActions();
      } catch (_fetchErr) {
        setSelectReady(sel);
      }
    },

    async _loadTerms() {
      const sel = this._el.termFilter;
      try {
        const resp = await fetch("/api/terms?all=true", {
          credentials: "include",
        });
        setSelectReady(sel);
        if (!resp.ok || !sel) return;
        const data = await resp.json();
        this.terms = data.terms || [];

        // keep the "All Terms" option, append the rest
        sel.innerHTML = '<option value="">All Terms</option>';
        this.terms
          .slice()
          .sort(
            (a, b) => new Date(b.start_date || 0) - new Date(a.start_date || 0),
          )
          .forEach((t) => {
            const opt = document.createElement("option");
            opt.value = t.term_id || t.id || "";
            opt.textContent = t.term_name || t.name || "Term";
            sel.appendChild(opt);
          });

        const defaultTerm = pickDefaultTerm(this.terms);
        sel.value = defaultTerm;
        this.currentTermId = defaultTerm;
      } catch (_) {
        setSelectReady(sel);
      }
    },

    /**
     * Show / hide program-specific action buttons ("New PLO", "Map CLO to PLO")
     * based on whether a specific program is selected vs "All Programs".
     */
    _updateProgramActions() {
      const el = this._el;
      const hasProgram = !!this.currentProgramId;
      if (el.createPloBtn) {
        el.createPloBtn.style.display = hasProgram ? "" : "none";
      }
      if (el.mapCloBtn) {
        el.mapCloBtn.style.display = hasProgram ? "" : "none";
      }
    },

    // ===================================================================
    // Tree fetch + render
    // ===================================================================
    async loadTree() {
      // Cancel any in-progress all-programs trend loading
      this._allTrendGen = (this._allTrendGen || 0) + 1;

      const pid = this.currentProgramId;
      this._updateProgramActions();

      // "All Programs" mode — load each program's tree
      if (!pid) {
        if (this.programs.length === 0) {
          setEmptyState("ploTreeContainer", "No programs available.");
          return;
        }
        setLoadingState("ploTreeContainer", "Loading all programs…");
        await this._loadAllPrograms();
        return;
      }

      setLoadingState("ploTreeContainer", "Loading PLO tree…");

      const qs = new URLSearchParams();
      if (this.currentTermId) qs.set("term_id", this.currentTermId);
      const url = `/api/programs/${encodeURIComponent(pid)}/plo-dashboard?${qs}`;

      try {
        const resp = await fetch(url, {
          credentials: "include",
          headers: { Accept: "application/json" },
        });
        if (!resp.ok) {
          setErrorState(
            "ploTreeContainer",
            `Failed to load PLO dashboard (HTTP ${resp.status}).`,
          );
          return;
        }
        const data = await resp.json();
        this.tree = data;
        this.displayMode = data.assessment_display_mode || "both";
        if (this._el.displayMode) this._el.displayMode.value = this.displayMode;
        this.draftMappingId = null; // reset; re-fetched when modal opens
        this._renderTree();
        this._loadTrendData();
      } catch (err) {
        setErrorState("ploTreeContainer", `Error: ${err.message}`);
      }
    },

    /**
     * Load and render PLO trees for every program (bird's-eye view).
     * Uses parallel fetches with a generation counter to prevent stale results.
     */
    async _loadAllPrograms() {
      const container = this._el.treeContainer;
      if (!container) return;
      container.innerHTML = "";

      // Generation counter prevents stale results from overwriting a newer load
      this._allProgramsGen = (this._allProgramsGen || 0) + 1;
      const gen = this._allProgramsGen;

      const qs = new URLSearchParams();
      if (this.currentTermId) qs.set("term_id", this.currentTermId);

      // Fetch all programs in parallel
      const fetches = this.programs.map((prog) => {
        const progId = prog.program_id || prog.id;
        const url = `/api/programs/${encodeURIComponent(progId)}/plo-dashboard?${qs}`;
        return fetch(url, {
          credentials: "include",
          headers: { Accept: "application/json" },
        })
          .then((resp) => (resp.ok ? resp.json() : null))
          .then((data) => ({ prog, data }))
          .catch(() => ({ prog, data: null }));
      });

      const results = await Promise.allSettled(fetches);

      // Abort if a newer load has started
      if (gen !== this._allProgramsGen) return;

      for (const result of results) {
        const { prog, data } =
          result.status === "fulfilled" ? result.value : {};
        if (!data) continue;

        // Program section heading
        const heading = document.createElement("h5");
        heading.className = "mt-3 mb-2 plo-all-programs-heading";
        heading.textContent = prog.name;
        if (data.mapping && data.mapping.version) {
          const badge = document.createElement("span");
          badge.className = "badge bg-secondary ms-2";
          badge.textContent = `v${data.mapping.version}`;
          heading.appendChild(badge);
        }
        // Collapsible program section
        const section = document.createElement("div");
        section.className = "plo-program-section";

        // Add toggle chevron to heading
        const toggle = document.createElement("span");
        toggle.className = "plo-program-toggle";
        toggle.innerHTML = '<i class="fas fa-chevron-down"></i>';
        heading.insertBefore(toggle, heading.firstChild);
        heading.style.cursor = "pointer";
        section.appendChild(heading);

        // Content container (collapsible)
        const content = document.createElement("div");
        content.className = "plo-program-content";

        // Render tree for this program
        if (data.plos && data.plos.length > 0) {
          content.appendChild(this._buildSummaryBar(data.plos));
          const ul = document.createElement("ul");
          ul.className = "plo-tree";
          const savedTree = this.tree;
          const savedDisplayMode = this.displayMode;
          this.tree = data;
          this.displayMode = data.assessment_display_mode || "both";
          data.plos.forEach((plo) => ul.appendChild(this._buildPloNode(plo)));
          this.tree = savedTree;
          this.displayMode = savedDisplayMode;
          content.appendChild(ul);
        } else {
          const empty = document.createElement("p");
          empty.className = "text-muted small fst-italic ms-3 mb-3";
          empty.textContent = "No PLOs defined.";
          content.appendChild(empty);
        }

        section.appendChild(content);
        container.appendChild(section);

        // Wire toggle
        heading.addEventListener("click", () => {
          section.classList.toggle("collapsed");
        });
      }

      // Load trend sparklines for each program
      this._loadAllTrendData();

      if (this._el.programName) {
        this._el.programName.textContent = "All Programs";
      }
      if (this._el.versionBadge) {
        this._el.versionBadge.style.display = "none";
      }
    },

    /**
     * Load trend data for all programs (used in All Programs mode).
     * Fetches each program's trend data in parallel, then injects
     * sparklines sequentially to avoid the singleton race guard
     * in PloTrend.loadTrend().
     */
    async _loadAllTrendData() {
      if (typeof globalThis === "undefined" || !globalThis.PloTrend) return;

      const gen = (this._allTrendGen = (this._allTrendGen || 0) + 1);
      const termId = this.currentTermId;

      const fetches = this.programs.map(async (prog) => {
        const progId = prog.program_id || prog.id;
        const url = `/api/programs/${encodeURIComponent(progId)}/plo-dashboard/trend`;
        try {
          const resp = await fetch(url, {
            credentials: "include",
            headers: { Accept: "application/json" },
          });
          if (!resp.ok) return null;
          const data = await resp.json();
          return data.success ? data : null;
        } catch {
          return null;
        }
      });

      const results = await Promise.all(fetches);
      if (gen !== this._allTrendGen) return; // stale — user navigated away

      const pt = globalThis.PloTrend;
      if (!pt) return;
      if (termId) pt.selectedTermId = termId;
      for (const data of results) {
        if (!data) continue;
        pt.programId = data.program_id || null;
        pt.trendData = data;
        pt.injectSparklines({ restoreFromHash: false });
      }

      if (typeof pt._restoreAllProgramsFromHash === "function") {
        pt._restoreAllProgramsFromHash(results.filter(Boolean));
      } else if (typeof pt._restoreFromHash === "function") {
        pt._restoreFromHash();
      }
    },

    /**
     * Load trend sparklines after the tree has been rendered.
     * Delegates to PloTrend (plo_trend.js) if available.
     */
    _loadTrendData() {
      if (
        typeof globalThis !== "undefined" &&
        globalThis.PloTrend &&
        this.currentProgramId
      ) {
        globalThis.PloTrend.loadTrend(
          this.currentProgramId,
          this.currentTermId,
        );
      }
    },

    /**
     * Update all assessment badges in-place for the current displayMode
     * without rebuilding the DOM tree (preserves expanded/collapsed state).
     */
    _refreshBadges() {
      const container = this._el.treeContainer;
      if (!container) return;
      container.querySelectorAll(".plo-assessment-badge").forEach((badge) => {
        const raw = badge.dataset.passRate;
        const passRate = raw === "" || raw == null ? null : Number(raw);
        const { text, cssClass } = formatAssessment(passRate, this.displayMode);
        badge.className = "plo-assessment-badge " + cssClass;
        badge.textContent = text;
      });
    },

    _renderTree() {
      const container = this._el.treeContainer;
      if (!container) return;
      const data = this.tree;

      // Header: program name + mapping version badge
      const prog = this.programs.find(
        (p) => (p.program_id || p.id) === this.currentProgramId,
      );
      if (this._el.programName) {
        this._el.programName.textContent = prog ? prog.name : "Program";
      }
      if (this._el.versionBadge) {
        if (data && data.mapping && data.mapping.version) {
          this._el.versionBadge.textContent = `Mapping v${data.mapping.version}`;
          this._el.versionBadge.style.display = "";
        } else {
          this._el.versionBadge.style.display = "none";
        }
      }

      // Empty states
      if (!data || !Array.isArray(data.plos) || data.plos.length === 0) {
        setEmptyState(
          "ploTreeContainer",
          "No Program Learning Outcomes defined yet. Use “New PLO” to create one.",
        );
        return;
      }

      const ul = document.createElement("ul");
      ul.className = "plo-tree";
      data.plos.forEach((plo) => ul.appendChild(this._buildPloNode(plo)));

      container.innerHTML = "";
      container.appendChild(this._buildSummaryBar(data.plos));
      container.appendChild(ul);
    },

    /**
     * Build a compact summary bar showing PLO status distribution.
     * Displays counts of satisfactory / needs-attention / no-data PLOs
     * with a proportional progress bar.
     */
    _buildSummaryBar(plos) {
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

      // Category rows with sparkline slots
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

        // Sparkline slots (populated after trend data loads)
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

      // Progress bar
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
    },

    // ===================================================================
    // Node builders (PLO → CLO → Section)
    // ===================================================================
    _buildPloNode(plo) {
      const li = document.createElement("li");
      li.className = "plo-tree-node";
      li.dataset.ploId = plo.id;
      li.dataset.ploNumber = plo.plo_number;

      const header = this._buildHeader(
        `PLO-${plo.plo_number}`,
        plo.description,
        plo.aggregate,
        { level: "plo", plo },
      );
      li.appendChild(header);

      /* narrative progress indicator */
      var pillFn =
        typeof globalThis !== "undefined" && globalThis.narrativeProgressPill;
      var pill = pillFn ? pillFn(plo) : null;
      if (pill) {
        var meta = header.querySelector(".plo-tree-meta");
        if (meta) meta.insertBefore(pill, meta.firstChild);
      }

      const children = document.createElement("ul");
      children.className = "plo-tree-children";
      if (!plo.clos || plo.clos.length === 0) {
        children.appendChild(
          this._buildLeafMessage("No CLOs mapped to this PLO yet."),
        );
      } else {
        plo.clos.forEach((clo) =>
          children.appendChild(this._buildCloNode(clo)),
        );
      }
      li.appendChild(children);

      this._wireToggle(li, header, plo.clos && plo.clos.length > 0);
      return li;
    },

    _buildCloNode(clo) {
      const li = document.createElement("li");
      li.className = "plo-tree-node";
      li.dataset.cloId = clo.outcome_id;

      const title = `${clo.course_number || ""} — CLO ${clo.clo_number || "?"}`;
      const header = this._buildHeader(title, clo.description, clo.aggregate, {
        level: "clo",
      });
      li.appendChild(header);

      const children = document.createElement("ul");
      children.className = "plo-tree-children";
      if (!clo.sections || clo.sections.length === 0) {
        children.appendChild(
          this._buildLeafMessage(
            "No section assessments in the selected term.",
          ),
        );
      } else {
        clo.sections.forEach((s) =>
          children.appendChild(this._buildSectionNode(s)),
        );
      }
      li.appendChild(children);

      this._wireToggle(li, header, clo.sections && clo.sections.length > 0);
      return li;
    },

    _buildSectionNode(section) {
      const li = document.createElement("li");
      li.className = "plo-tree-node leaf";

      const s = section._section || {};
      const offering = section._offering || {};
      const instructor = section._instructor || {};
      const term = section._term || {};
      const took = section.students_took;
      const passed = section.students_passed;
      let rate = null;
      if (typeof took === "number" && took > 0 && typeof passed === "number") {
        rate = (passed / took) * 100;
      }

      const title =
        `Section ${s.section_number || "?"}` +
        (term.name ? ` — ${term.name}` : "");
      const detailParts = [];
      if (instructor.last_name || instructor.first_name) {
        detailParts.push(
          `${instructor.first_name || ""} ${instructor.last_name || ""}`.trim(),
        );
      }
      if (section.assessment_tool) {
        detailParts.push(section.assessment_tool);
      }
      if (typeof took === "number" && typeof passed === "number") {
        detailParts.push(`${passed}/${took} passed`);
      }

      const header = this._buildHeader(
        title,
        detailParts.join(" · "),
        { pass_rate: rate, section_count: 1 },
        { level: "section" },
      );
      // reference offering for potential future navigation without lint warnings
      li.dataset.offeringId = offering.offering_id || offering.id || "";
      li.appendChild(header);
      return li;
    },

    _buildHeader(number, desc, aggregate, opts) {
      const header = document.createElement("div");
      header.className = "plo-tree-header";

      const toggle = document.createElement("span");
      toggle.className = "plo-tree-toggle";
      toggle.innerHTML = '<i class="fas fa-chevron-right"></i>';
      header.appendChild(toggle);

      const label = document.createElement("div");
      label.className = "plo-tree-label";
      const numEl = document.createElement("div");
      numEl.className = "plo-tree-number";
      numEl.textContent = number;
      if (opts && opts.level === "plo" && opts.plo) {
        const pill = document.createElement("span");
        pill.className = "plo-clo-count-pill ms-2";
        pill.textContent = `${opts.plo.clo_count || 0} CLO${(opts.plo.clo_count || 0) === 1 ? "" : "s"}`;
        numEl.appendChild(pill);
      }
      label.appendChild(numEl);
      if (desc) {
        const descEl = document.createElement("div");
        descEl.className = "plo-tree-desc";
        descEl.textContent = desc;
        label.appendChild(descEl);
      }
      header.appendChild(label);

      const meta = document.createElement("div");
      meta.className = "plo-tree-meta";

      const badge = document.createElement("span");
      badge.className = "plo-assessment-badge";
      const passRate =
        aggregate && aggregate.pass_rate != null ? aggregate.pass_rate : null;
      badge.dataset.passRate = passRate === null ? "" : String(passRate);
      const { text, cssClass } = formatAssessment(passRate, this.displayMode);
      badge.classList.add(cssClass);
      badge.textContent = text;
      meta.appendChild(badge);

      if (opts && opts.level === "plo" && opts.plo) {
        const actions = document.createElement("span");
        actions.className = "plo-tree-actions ms-2";
        const editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "btn btn-outline-secondary";
        editBtn.innerHTML = '<i class="fas fa-pencil"></i>';
        editBtn.title = "Edit PLO";
        editBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          this._openPloModal(opts.plo);
        });
        actions.appendChild(editBtn);
        meta.appendChild(actions);
      }

      header.appendChild(meta);
      return header;
    },

    _buildLeafMessage(text) {
      const li = document.createElement("li");
      li.className = "plo-tree-node leaf";
      const div = document.createElement("div");
      div.className = "plo-tree-header text-muted small fst-italic";
      div.textContent = text;
      li.appendChild(div);
      return li;
    },

    _wireToggle(li, header, hasChildren) {
      if (!hasChildren) {
        li.classList.add("expanded"); // so empty-message is visible
        return;
      }
      header.addEventListener("click", () => li.classList.toggle("expanded"));
    },

    _toggleAll(expand) {
      const nodes = this._el.treeContainer
        ? this._el.treeContainer.querySelectorAll(".plo-tree-node")
        : [];
      nodes.forEach((n) => {
        if (expand) n.classList.add("expanded");
        else n.classList.remove("expanded");
      });
    },

    // ===================================================================
    // Display-mode persistence (PUT to program extras)
    // ===================================================================
    async _persistDisplayMode() {
      if (!this.currentProgramId) return;
      try {
        await fetch(
          `/api/programs/${encodeURIComponent(this.currentProgramId)}`,
          {
            method: "PUT",
            credentials: "include",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": this._csrf(),
            },
            body: JSON.stringify({ assessment_display_mode: this.displayMode }),
          },
        );
      } catch (_) {
        /* non-fatal; badge re-renders locally anyway */
      }
    },

    _csrf() {
      const meta = document.querySelector('meta[name="csrf-token"]');
      return meta ? meta.content : "";
    },

    // ===================================================================
    // PLO create / edit modal
    // ===================================================================
    _openPloModal(plo) {
      const el = this._el;
      if (!el.ploModal) return;
      el.ploModalAlert.className = "alert d-none";
      if (plo) {
        el.ploModalLabel.textContent = "Edit Program Outcome";
        el.ploModalId.value = plo.id;
        el.ploModalNumber.value = plo.plo_number || "";
        el.ploModalDescription.value = plo.description || "";
        // Show PLO number (read-only) when editing
        if (el.ploModalNumberGroup) {
          el.ploModalNumberGroup.classList.remove("d-none");
        }
      } else {
        el.ploModalLabel.textContent = "New Program Outcome";
        el.ploModalId.value = "";
        el.ploModalNumber.value = "";
        el.ploModalDescription.value = "";
        // Hide PLO number on create — auto-assigned by server
        if (el.ploModalNumberGroup) {
          el.ploModalNumberGroup.classList.add("d-none");
        }
      }
      this._showModal(el.ploModal);
    },

    async _submitPloForm(e) {
      e.preventDefault();
      const el = this._el;
      const pid = this.currentProgramId;
      if (!pid) {
        this._modalAlert(
          el.ploModalAlert,
          "Please select a specific program first.",
          "danger",
        );
        return;
      }
      const ploId = el.ploModalId.value;
      const body = {
        description: el.ploModalDescription.value.trim(),
      };
      // On edit, include the (read-only) plo_number; on create, omit it
      // so the server auto-assigns the next available number.
      if (ploId) {
        const rawNum = el.ploModalNumber.value.trim();
        const parsed = parseInt(rawNum, 10);
        body.plo_number = Number.isFinite(parsed) ? parsed : rawNum;
      }

      const method = ploId ? "PUT" : "POST";
      const url = ploId
        ? `/api/programs/${encodeURIComponent(pid)}/plos/${encodeURIComponent(ploId)}`
        : `/api/programs/${encodeURIComponent(pid)}/plos`;

      try {
        const resp = await fetch(url, {
          method,
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": this._csrf(),
          },
          body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (!resp.ok || !data.success) {
          this._modalAlert(
            el.ploModalAlert,
            data.error || "Save failed",
            "danger",
          );
          return;
        }
        this._hideModal(el.ploModal);
        this.loadTree();
      } catch (err) {
        this._modalAlert(el.ploModalAlert, err.message, "danger");
      }
    },

    // ===================================================================
    // Map CLO modal
    // ===================================================================
    async _openMapCloModal(prefillPloId) {
      const el = this._el;
      if (!el.mapCloModal) return;
      el.mapCloModalAlert.className = "alert d-none";

      // populate PLO select from current tree
      el.mapCloModalPlo.innerHTML = '<option value="">Select a PLO…</option>';
      (this.tree && this.tree.plos ? this.tree.plos : []).forEach((p) => {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.textContent = `PLO-${p.plo_number} — ${p.description}`;
        el.mapCloModalPlo.appendChild(opt);
      });
      if (prefillPloId) el.mapCloModalPlo.value = prefillPloId;

      // ensure a draft exists & populate unmapped CLOs
      const pid = this.currentProgramId;
      el.mapCloModalClo.innerHTML = '<option value="">Loading…</option>';
      try {
        const draftResp = await fetch(
          `/api/programs/${encodeURIComponent(pid)}/plo-mappings/draft`,
          {
            method: "POST",
            credentials: "include",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": this._csrf(),
            },
            body: JSON.stringify({}),
          },
        );
        const draftData = await draftResp.json();
        this.draftMappingId =
          draftData.mapping && draftData.mapping.id
            ? draftData.mapping.id
            : null;

        const cloResp = await fetch(
          `/api/programs/${encodeURIComponent(pid)}/plo-mappings/unmapped-clos`,
          { credentials: "include" },
        );
        const cloData = await cloResp.json();
        const clos = cloData.unmapped_clos || [];

        el.mapCloModalClo.innerHTML = '<option value="">Select a CLO…</option>';
        clos.forEach((c) => {
          const opt = document.createElement("option");
          opt.value = c.outcome_id;
          const course = c.course || {};
          opt.textContent =
            `${course.course_number || ""} CLO ${c.clo_number || "?"} — ` +
            `${c.description || ""}`.slice(0, 80);
          el.mapCloModalClo.appendChild(opt);
        });
        if (clos.length === 0) {
          el.mapCloModalClo.innerHTML =
            '<option value="">All CLOs are already mapped</option>';
        }
      } catch (err) {
        this._modalAlert(el.mapCloModalAlert, err.message, "danger");
      }

      this._showModal(el.mapCloModal);
    },

    async _submitMapCloForm(e) {
      e.preventDefault();
      const el = this._el;
      const pid = this.currentProgramId;
      const ploId = el.mapCloModalPlo.value;
      const cloId = el.mapCloModalClo.value;
      if (!this.draftMappingId || !ploId || !cloId) {
        this._modalAlert(
          el.mapCloModalAlert,
          "Select both a PLO and a CLO.",
          "warning",
        );
        return;
      }
      try {
        const resp = await fetch(
          `/api/programs/${encodeURIComponent(pid)}/plo-mappings/${encodeURIComponent(this.draftMappingId)}/entries`,
          {
            method: "POST",
            credentials: "include",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": this._csrf(),
            },
            body: JSON.stringify({
              program_outcome_id: ploId,
              course_outcome_id: cloId,
            }),
          },
        );
        const data = await resp.json();
        if (!resp.ok || !data.success) {
          this._modalAlert(
            el.mapCloModalAlert,
            data.error || "Failed to add mapping",
            "danger",
          );
          return;
        }
        this._modalAlert(
          el.mapCloModalAlert,
          "Mapping added to draft. Publish when ready.",
          "success",
        );
        // refresh unmapped CLO list so user can add another
        this._openMapCloModal(ploId);
      } catch (err) {
        this._modalAlert(el.mapCloModalAlert, err.message, "danger");
      }
    },

    async _publishDraft() {
      if (!this.draftMappingId || !this.currentProgramId) return;
      const el = this._el;
      try {
        const resp = await fetch(
          `/api/programs/${encodeURIComponent(this.currentProgramId)}/plo-mappings/${encodeURIComponent(this.draftMappingId)}/publish`,
          {
            method: "POST",
            credentials: "include",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": this._csrf(),
            },
            body: JSON.stringify({}),
          },
        );
        const data = await resp.json();
        if (!resp.ok || !data.success) {
          this._modalAlert(
            el.mapCloModalAlert,
            data.error || "Publish failed",
            "danger",
          );
          return;
        }
        this._hideModal(el.mapCloModal);
        this.loadTree();
      } catch (err) {
        this._modalAlert(el.mapCloModalAlert, err.message, "danger");
      }
    },

    // ===================================================================
    // Modal helpers (Bootstrap 5 — fall back to class toggle for tests)
    // ===================================================================
    _showModal(el) {
      if (
        typeof globalThis.bootstrap !== "undefined" &&
        globalThis.bootstrap.Modal
      ) {
        globalThis.bootstrap.Modal.getOrCreateInstance(el).show();
      } else {
        el.classList.add("show");
        el.style.display = "block";
      }
    },
    _hideModal(el) {
      if (
        typeof globalThis.bootstrap !== "undefined" &&
        globalThis.bootstrap.Modal
      ) {
        const inst = globalThis.bootstrap.Modal.getInstance(el);
        if (inst) inst.hide();
      } else {
        el.classList.remove("show");
        el.style.display = "none";
      }
    },
    _modalAlert(el, msg, level) {
      if (!el) return;
      el.className = `alert alert-${level || "info"}`;
      el.textContent = msg;
    },
  };

  // -------------------------------------------------------------------
  // Boot + exports
  // -------------------------------------------------------------------
  if (typeof document !== "undefined") {
    document.addEventListener("DOMContentLoaded", () => PloDashboard.init());
  }
  if (typeof globalThis !== "undefined") {
    globalThis.PloDashboard = PloDashboard;
  }
  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      PloDashboard,
      formatAssessment,
      pickDefaultTerm,
      DEFAULT_PASS_THRESHOLD,
    };
  }
})();
