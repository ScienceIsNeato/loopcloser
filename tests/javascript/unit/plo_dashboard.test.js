/**
 * Unit tests for static/plo_dashboard.js.
 *
 * Two tiers:
 *  - Pure helpers (formatAssessment, pickDefaultTerm): table-driven
 *    coverage of the display-mode render rules and term-default logic.
 *  - PloDashboard DOM flow: mocked-fetch + jsdom coverage of
 *    loadTree → renderTree → node builders → stats aggregation, plus
 *    the modal plumbing. These are fast (no network, no real fetch)
 *    but exercise the same code paths the browser hits.
 */

// dashboard_utils globals (setLoadingState, setSelectLoading, etc.) are
// exposed globally via tests/javascript/setupTests.js — no per-file setup needed.

const {
  PloDashboard,
  formatAssessment,
  pickDefaultTerm,
  DEFAULT_PASS_THRESHOLD,
} = require("../../../static/plo_dashboard");
const { setBody } = require("../helpers/dom");
const {
  resetDashboardState,
  routeFetch,
  SAMPLE_TREE,
  SKELETON,
} = require("./helpers/plo_dashboard_fixtures");

describe("plo_dashboard.js — formatAssessment", () => {
  describe("no-data sentinel", () => {
    test("null → em dash, nodata class (regardless of mode)", () => {
      for (const mode of ["binary", "percentage", "both"]) {
        const r = formatAssessment(null, mode);
        expect(r).toEqual({ text: "—", cssClass: "nodata" });
      }
    });

    test("undefined → em dash, nodata class", () => {
      expect(formatAssessment(undefined, "both")).toEqual({
        text: "—",
        cssClass: "nodata",
      });
    });

    test("0 is real data (0% passed), not the no-data sentinel", () => {
      // 0 !== null — a section where everyone failed is still a data point.
      const r = formatAssessment(0, "percentage");
      expect(r.text).toBe("0%");
      expect(r.cssClass).toBe("fail");
    });
  });

  describe("mode: binary", () => {
    test("at threshold → S", () => {
      // >= is inclusive: exactly hitting the bar is a pass.
      const r = formatAssessment(DEFAULT_PASS_THRESHOLD, "binary");
      expect(r).toEqual({ text: "S", cssClass: "pass" });
    });

    test("above threshold → S", () => {
      expect(formatAssessment(95, "binary")).toEqual({
        text: "S",
        cssClass: "pass",
      });
    });

    test("just below threshold → U", () => {
      const r = formatAssessment(DEFAULT_PASS_THRESHOLD - 0.1, "binary");
      expect(r).toEqual({ text: "U", cssClass: "fail" });
    });
  });

  describe("mode: percentage", () => {
    test("rounds to nearest whole percent", () => {
      expect(formatAssessment(71.7, "percentage").text).toBe("72%");
      expect(formatAssessment(71.4, "percentage").text).toBe("71%");
    });

    test("cssClass still respects pass/fail threshold", () => {
      expect(formatAssessment(90, "percentage").cssClass).toBe("pass");
      expect(formatAssessment(40, "percentage").cssClass).toBe("fail");
    });
  });

  describe("mode: both (default)", () => {
    test('formats as "S (NN%)"', () => {
      expect(formatAssessment(78.3, "both").text).toBe("S (78%)");
    });

    test("failing grade shows U + percent", () => {
      expect(formatAssessment(54.6, "both").text).toBe("U (55%)");
    });

    test('unknown mode string falls through to "both" behaviour', () => {
      // Any mode other than binary/percentage hits the else branch.
      const r = formatAssessment(80, "garbage");
      expect(r.text).toBe("S (80%)");
      expect(r.cssClass).toBe("pass");
    });
  });

  describe("custom threshold", () => {
    test("explicit threshold overrides default", () => {
      // With threshold=85, an 80% pass rate is a fail.
      const r = formatAssessment(80, "binary", 85);
      expect(r).toEqual({ text: "U", cssClass: "fail" });
    });

    test("non-numeric threshold falls back to DEFAULT_PASS_THRESHOLD", () => {
      // A caller passing nonsense shouldn't break the render — just
      // use the constant. 71 passes against default 70.
      const r = formatAssessment(71, "binary", "not-a-number");
      expect(r.text).toBe("S");
    });

    test("threshold=0 means everything passes", () => {
      expect(formatAssessment(0, "binary", 0).text).toBe("S");
    });
  });

  test("DEFAULT_PASS_THRESHOLD is exported and reasonable", () => {
    expect(typeof DEFAULT_PASS_THRESHOLD).toBe("number");
    expect(DEFAULT_PASS_THRESHOLD).toBe(70);
  });
});

describe("plo_dashboard.js — pickDefaultTerm", () => {
  describe("empty / degenerate inputs", () => {
    test("empty array → empty string", () => {
      expect(pickDefaultTerm([])).toBe("");
    });

    test("null → empty string", () => {
      expect(pickDefaultTerm(null)).toBe("");
    });

    test("not-an-array → empty string", () => {
      expect(pickDefaultTerm({ term_id: "t1" })).toBe("");
    });
  });

  describe("active-term preference", () => {
    test('prefers term_status === "ACTIVE"', () => {
      const terms = [
        { term_id: "t-old", term_status: "CLOSED", start_date: "2025-01-01" },
        {
          term_id: "t-active",
          term_status: "ACTIVE",
          start_date: "2024-09-01",
        },
        {
          term_id: "t-future",
          term_status: "PLANNED",
          start_date: "2026-01-01",
        },
      ];
      // Active wins even though t-future has the latest start_date.
      expect(pickDefaultTerm(terms)).toBe("t-active");
    });

    test('accepts status alias (status === "ACTIVE")', () => {
      const terms = [{ id: "t1", status: "ACTIVE" }];
      expect(pickDefaultTerm(terms)).toBe("t1");
    });

    test("accepts is_active boolean alias", () => {
      const terms = [
        { term_id: "t-off", is_active: false },
        { term_id: "t-on", is_active: true },
      ];
      expect(pickDefaultTerm(terms)).toBe("t-on");
    });

    test("accepts active boolean alias", () => {
      const terms = [{ term_id: "t1", active: true }];
      expect(pickDefaultTerm(terms)).toBe("t1");
    });

    test("first active wins when multiple are active", () => {
      const terms = [
        { term_id: "t-a", term_status: "ACTIVE" },
        { term_id: "t-b", term_status: "ACTIVE" },
      ];
      // Array.find returns first match — t-a wins. No tie-breaking
      // logic beyond that (intentionally simple).
      expect(pickDefaultTerm(terms)).toBe("t-a");
    });
  });

  describe("start_date fallback (no active term)", () => {
    test("picks most-recent by start_date", () => {
      const terms = [
        { term_id: "t-2024s", start_date: "2024-01-10" },
        { term_id: "t-2025s", start_date: "2025-01-10" },
        { term_id: "t-2023f", start_date: "2023-09-01" },
      ];
      expect(pickDefaultTerm(terms)).toBe("t-2025s");
    });

    test("does not mutate the input array", () => {
      const terms = [
        { term_id: "t-a", start_date: "2024-01-01" },
        { term_id: "t-b", start_date: "2025-01-01" },
      ];
      const snapshot = terms.map((t) => t.term_id);
      pickDefaultTerm(terms);
      // The internal sort uses [...terms] — original order preserved.
      expect(terms.map((t) => t.term_id)).toEqual(snapshot);
    });

    test("missing start_date treated as epoch (0)", () => {
      const terms = [
        { term_id: "t-no-date" }, // no start_date → Date(0)
        { term_id: "t-dated", start_date: "2025-01-01" },
      ];
      expect(pickDefaultTerm(terms)).toBe("t-dated");
    });
  });

  describe("id-field aliases", () => {
    test("falls through term_id → id", () => {
      // The "All Terms" option and some API payloads use `id` not `term_id`.
      expect(pickDefaultTerm([{ id: "x", term_status: "ACTIVE" }])).toBe("x");
    });

    test("prefers term_id over id when both present", () => {
      const terms = [
        { term_id: "prefer-me", id: "not-me", term_status: "ACTIVE" },
      ];
      expect(pickDefaultTerm(terms)).toBe("prefer-me");
    });

    test("term with neither id key → empty string (not crash)", () => {
      const terms = [{ term_status: "ACTIVE", name: "Spring 2025" }];
      expect(pickDefaultTerm(terms)).toBe("");
    });
  });
});

// ===========================================================================
// PloDashboard — DOM + fetch-mocked integration-style tests
// ===========================================================================

describe("PloDashboard — filter loading", () => {
  beforeEach(() => {
    setBody(SKELETON);
    resetDashboardState();
    PloDashboard._cacheSelectors();
  });

  afterEach(() => {
    delete global.fetch;
    localStorage.clear();
  });

  test("_loadPrograms populates dropdown and picks first program", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        programs: [
          { program_id: "prog-1", name: "Biology BS" },
          { program_id: "prog-2", name: "Zoology BS" },
        ],
      }),
    });

    await PloDashboard._loadPrograms();

    const sel = document.getElementById("ploProgramFilter");
    expect(sel.options.length).toBe(3); // All Programs + 2 programs
    expect(sel.options[0].textContent).toBe("All Programs");
    expect(sel.options[1].textContent).toBe("Biology BS");
    // No localStorage entry → defaults to All Programs
    expect(PloDashboard.currentProgramId).toBe("");
    expect(sel.value).toBe("");
  });

  test("_loadPrograms honours localStorage when the stored id is still valid", async () => {
    localStorage.setItem("ploDashboard.lastProgramId", "prog-2");
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        programs: [
          { program_id: "prog-1", name: "Biology" },
          { program_id: "prog-2", name: "Zoology" },
        ],
      }),
    });
    await PloDashboard._loadPrograms();
    expect(PloDashboard.currentProgramId).toBe("prog-2");
  });

  test("_loadPrograms ignores stale localStorage id not in the list", async () => {
    localStorage.setItem("ploDashboard.lastProgramId", "deleted-prog");
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ programs: [{ id: "prog-1", name: "Only One" }] }),
    });
    await PloDashboard._loadPrograms();
    // Falls back to All Programs (empty string)
    expect(PloDashboard.currentProgramId).toBe("");
  });

  test("_loadPrograms handles empty list gracefully", async () => {
    global.fetch = jest
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ programs: [] }) });
    await PloDashboard._loadPrograms();
    const sel = document.getElementById("ploProgramFilter");
    expect(sel.options[0].textContent).toMatch(/no programs/i);
    expect(PloDashboard.currentProgramId).toBeNull();
  });

  test("_loadPrograms bails silently on non-OK response", async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 500 });
    await PloDashboard._loadPrograms();
    // State untouched, no throw
    expect(PloDashboard.programs).toEqual([]);
  });

  test('_loadTerms appends sorted terms after the "All Terms" option', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        terms: [
          {
            term_id: "t-2024",
            term_name: "Spring 2024",
            start_date: "2024-01-10",
          },
          {
            term_id: "t-2025",
            term_name: "Spring 2025",
            start_date: "2025-01-10",
          },
        ],
      }),
    });
    await PloDashboard._loadTerms();
    const sel = document.getElementById("ploTermFilter");
    // 1 existing "All Terms" + 2 appended
    expect(sel.options.length).toBe(3);
    // most-recent first (2025 before 2024)
    expect(sel.options[1].textContent).toBe("Spring 2025");
    // No active term → pickDefaultTerm falls back to most-recent start_date
    expect(PloDashboard.currentTermId).toBe("t-2025");
  });

  test("_loadTerms selects active term when present", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        terms: [
          { term_id: "t-old", term_status: "CLOSED", start_date: "2024-01-01" },
          { term_id: "t-now", term_status: "ACTIVE", start_date: "2024-09-01" },
        ],
      }),
    });
    await PloDashboard._loadTerms();
    expect(PloDashboard.currentTermId).toBe("t-now");
  });
});

describe("PloDashboard — loadTree + render", () => {
  beforeEach(() => {
    setBody(SKELETON);
    resetDashboardState();
    PloDashboard._cacheSelectors();
    PloDashboard.programs = [{ program_id: "prog-1", name: "Biology BS" }];
    PloDashboard.currentProgramId = "prog-1";
    PloDashboard.currentTermId = "t-active";
  });

  afterEach(() => {
    delete global.fetch;
  });

  test("no program selected with no programs → empty-state message, no fetch", async () => {
    PloDashboard.currentProgramId = null;
    PloDashboard.programs = [];
    global.fetch = jest.fn();
    await PloDashboard.loadTree();
    expect(global.fetch).not.toHaveBeenCalled();
    expect(document.getElementById("ploTreeContainer").textContent).toMatch(
      /no programs available/i,
    );
  });

  test("successful load renders tree + populates stats", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => SAMPLE_TREE,
    });

    await PloDashboard.loadTree();

    // Fetch URL includes program + term filter
    expect(global.fetch.mock.calls[0][0]).toMatch(
      /\/api\/programs\/prog-1\/plo-dashboard\?term_id=t-active/,
    );

    // Tree rendered
    const tree = document.querySelector("ul.plo-tree");
    expect(tree).toBeTruthy();
    const ploNodes = tree.querySelectorAll(":scope > li.plo-tree-node");
    expect(ploNodes.length).toBe(2);

    // PLO-1 header carries the number + CLO count pill
    const plo1Num = ploNodes[0].querySelector(".plo-tree-number");
    expect(plo1Num.textContent).toContain("PLO-1");
    expect(plo1Num.textContent).toContain("1 CLO");

    // PLO-2 has empty clos → leaf message + auto-expanded
    expect(ploNodes[1].classList.contains("expanded")).toBe(true);
    expect(ploNodes[1].textContent).toMatch(/no clos mapped/i);

    // Section leaves under PLO-1: 2 sections
    const sectionLeaves = ploNodes[0].querySelectorAll("li.plo-tree-node.leaf");
    expect(sectionLeaves.length).toBe(2);
    // First section shows instructor name + pass count detail
    expect(sectionLeaves[0].textContent).toContain("Ada Lovelace");
    expect(sectionLeaves[0].textContent).toContain("27/30 passed");

    // Version badge shows v2
    expect(document.getElementById("ploTreeVersionBadge").textContent).toMatch(
      /v2/,
    );

    // Display mode picked up from API response
    expect(PloDashboard.displayMode).toBe("both");
    expect(document.getElementById("ploDisplayMode").value).toBe("both");
  });

  test("assessment badges honour display mode", async () => {
    // Same tree, but program says "binary"
    const binaryTree = { ...SAMPLE_TREE, assessment_display_mode: "binary" };
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => binaryTree,
    });
    await PloDashboard.loadTree();

    const badges = document.querySelectorAll(".plo-assessment-badge");
    // PLO-1 (80% → S), CLO-A (80% → S), Section 001 (90% → S),
    // Section 002 (65% → U), PLO-2 (null → —)
    const texts = Array.from(badges).map((b) => b.textContent);
    expect(texts).toContain("S");
    expect(texts).toContain("U");
    expect(texts).toContain("—");
    // In binary mode no percent sign anywhere
    expect(texts.join("")).not.toContain("%");
  });

  test('CLO with zero sections → "no section assessments" leaf message', async () => {
    const treeNoSections = {
      ...SAMPLE_TREE,
      plos: [
        {
          id: "plo-x",
          plo_number: 1,
          description: "x",
          clo_count: 1,
          aggregate: { pass_rate: null },
          clos: [
            {
              outcome_id: "clo-x",
              clo_number: "1",
              course_number: "X-100",
              description: "x",
              aggregate: { pass_rate: null },
              sections: [], // <-- the empty state under test
            },
          ],
        },
      ],
    };
    global.fetch = jest
      .fn()
      .mockResolvedValue({ ok: true, json: async () => treeNoSections });
    await PloDashboard.loadTree();
    expect(document.getElementById("ploTreeContainer").textContent).toMatch(
      /no section assessments/i,
    );
  });

  test('empty plos array → "no PLOs defined" empty state', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ...SAMPLE_TREE,
        plos: [],
        mapping: null,
        mapping_status: "none",
      }),
    });
    await PloDashboard.loadTree();
    expect(document.getElementById("ploTreeContainer").textContent).toMatch(
      /no program learning outcomes/i,
    );
    // version badge hidden when no mapping version
    expect(document.getElementById("ploTreeVersionBadge").style.display).toBe(
      "none",
    );
  });

  test("HTTP error → setErrorState message with status code", async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 500 });
    await PloDashboard.loadTree();
    expect(document.getElementById("ploTreeContainer").textContent).toMatch(
      /500/,
    );
  });

  test("fetch throws → error state with exception message", async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error("network down"));
    await PloDashboard.loadTree();
    expect(document.getElementById("ploTreeContainer").textContent).toMatch(
      /network down/,
    );
  });

  test("All Programs mode loads each program tree", async () => {
    PloDashboard.currentProgramId = "";
    PloDashboard.programs = [
      { program_id: "prog-1", name: "Biology BS" },
      { program_id: "prog-2", name: "Chemistry BS" },
    ];
    // Mock PloTrend to avoid unrelated errors
    global.PloTrend = { loadTrend: jest.fn() };

    global.fetch = jest.fn().mockImplementation((url) => {
      if (url.includes("prog-1")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            ...SAMPLE_TREE,
            program_id: "prog-1",
          }),
        });
      }
      if (url.includes("prog-2")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            ...SAMPLE_TREE,
            program_id: "prog-2",
            mapping: { id: "m-2", version: 1, status: "published" },
            plos: [],
          }),
        });
      }
      return Promise.reject(new Error("unexpected URL"));
    });

    await PloDashboard.loadTree();

    // Both program headings rendered (now inside collapsible sections)
    const sections = document.querySelectorAll(".plo-program-section");
    expect(sections.length).toBe(2);
    const headings = document.querySelectorAll(".plo-all-programs-heading");
    expect(headings.length).toBe(2);
    expect(headings[0].textContent).toContain("Biology BS");
    expect(headings[1].textContent).toContain("Chemistry BS");

    // First program has PLO tree, second shows "No PLOs defined."
    const trees = document.querySelectorAll("ul.plo-tree");
    expect(trees.length).toBe(1);
    const emptyMsg = document.querySelector("p.text-muted");
    expect(emptyMsg.textContent).toContain("No PLOs defined.");

    // Programs are collapsible
    const firstSection = sections[0];
    expect(firstSection.querySelector(".plo-program-content")).not.toBeNull();
    expect(firstSection.querySelector(".plo-program-toggle")).not.toBeNull();

    // Clicking heading toggles collapsed state
    headings[0].click();
    expect(firstSection.classList.contains("collapsed")).toBe(true);
    headings[0].click();
    expect(firstSection.classList.contains("collapsed")).toBe(false);

    // Program name label shows "All Programs"
    expect(document.getElementById("ploTreeProgramName").textContent).toBe(
      "All Programs",
    );

    // Version badge hidden in All Programs mode
    expect(document.getElementById("ploTreeVersionBadge").style.display).toBe(
      "none",
    );

    delete global.PloTrend;
  });

  test("All Programs mode skips programs that fail to load", async () => {
    PloDashboard.currentProgramId = "";
    PloDashboard.programs = [
      { program_id: "prog-bad", name: "Failing Program" },
      { program_id: "prog-ok", name: "Good Program" },
    ];
    global.PloTrend = { loadTrend: jest.fn() };

    global.fetch = jest.fn().mockImplementation((url) => {
      if (url.includes("prog-bad")) {
        return Promise.resolve({ ok: false, status: 500 });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({
          ...SAMPLE_TREE,
          program_id: "prog-ok",
        }),
      });
    });

    await PloDashboard.loadTree();

    // Only the successful program renders a heading
    const headings = document.querySelectorAll(".plo-all-programs-heading");
    expect(headings.length).toBe(1);
    expect(headings[0].textContent).toContain("Good Program");

    delete global.PloTrend;
  });
});
