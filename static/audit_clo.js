/* global setSelectLoading, setSelectReady */
/**
 * Get status badge HTML with color-coded scheme:
 * Unassigned=grey, Assigned=black, In Progress=blue,
 * Needs Rework=orange, Awaiting Approval=yellow-green, Approved=green, NCI=red
 */
function resolveAuditCloActionsModule() {
  if (typeof globalThis !== "undefined" && globalThis.AuditCloActions) {
    return globalThis.AuditCloActions;
  }
  if (typeof module === "undefined" || !module.exports) {
    return null;
  }
  try {
    return require("./audit_clo_actions");
  } catch (_error) {
    try {
      return require(`${process.cwd()}/static/audit_clo_actions.js`);
    } catch (_fallbackError) {
      return null;
    }
  }
}

const auditCloActionsModule = resolveAuditCloActionsModule();
const auditCloListModule =
  typeof globalThis !== "undefined" && globalThis.AuditCloList
    ? globalThis.AuditCloList
    : typeof module !== "undefined" && module.exports
      ? require("./audit_clo_list")
      : null;

function getStatusBadge(status) {
  const span = document.createElement("span");
  span.className = "badge";

  const config = {
    unassigned: { bg: "#6c757d", text: "Unassigned" },
    assigned: { bg: "#212529", text: "Assigned" },
    in_progress: { bg: "#0d6efd", text: "In Progress" },
    awaiting_approval: { bg: "#9acd32", text: "Awaiting Approval" },
    approval_pending: { bg: "#fd7e14", text: "Needs Rework" },
    approved: { bg: "#198754", text: "✓ Approved" },
    never_coming_in: { bg: "#dc3545", text: "NCI" },
  };

  const setup = config[status] || { bg: "#6c757d", text: "Unknown" };
  span.style.backgroundColor = setup.bg;
  span.textContent = setup.text;
  return span;
}

/**
 * Format date string
 */
function formatDate(dateString) {
  if (!dateString) return "N/A";
  const date = new Date(dateString);
  return date.toLocaleString();
}

/**
 * Truncate text
 */
function truncateText(text, maxLength) {
  if (!text) return "";
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength) + "...";
}

/**
 * Escape HTML
 */
function escapeHtml(text) {
  if (!text) return "";
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Format status for CSV export (plain text)
 */
function formatStatusLabel(status) {
  const labels = {
    unassigned: "Unassigned",
    assigned: "Assigned",
    in_progress: "In Progress",
    awaiting_approval: "Awaiting Approval",
    approval_pending: "Needs Rework",
    approved: "Approved",
    never_coming_in: "Never Coming In",
  };
  return labels[status] || status || "";
}

/**
 * Format date for CSV export (ISO string)
 */
function formatDateForCsv(dateString) {
  if (!dateString) return "";
  const date = new Date(dateString);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toISOString();
}

/**
 * Escape CSV value
 */
function escapeForCsv(value) {
  if (value === null || value === undefined) {
    return '""';
  }
  const text = String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

/**
 * Calculate success rate based on students took/passed
 */
function calculateSuccessRate(clo) {
  const took = typeof clo.students_took === "number" ? clo.students_took : null;
  const passed =
    typeof clo.students_passed === "number" ? clo.students_passed : null;
  if (!took || took <= 0 || passed === null || passed === undefined) {
    return null;
  }
  return Math.round((passed / took) * 100);
}

/**
 * Format history for CSV export (plain text)
 */
function formatHistoryForCsv(clo) {
  if (!clo.history || clo.history.length === 0) {
    return "No history";
  }
  return clo.history
    .map((entry) => `${entry.event} - ${formatDateForCsv(entry.occurred_at)}`)
    .join("; ");
}

/**
 * Export current Outcome list to CSV
 */
function exportCurrentViewToCsv(cloList) {
  if (!Array.isArray(cloList) || cloList.length === 0) {
    alert("No Outcome records available to export for the selected filters.");
    return false;
  }

  const headers = [
    "Course",
    "Outcome Number",
    "Status",
    "Instructor",
    "History",
    "Students Took",
    "Students Passed",
    "Success Rate (%)",
    "Term",
    "Assessment Tool",
  ];

  const rows = cloList.map((clo) => [
    [clo.course_number || "", clo.course_title || ""]
      .filter(Boolean)
      .join(" - "),
    clo.clo_number || "",
    formatStatusLabel(clo.status),
    clo.instructor_name || "",
    formatHistoryForCsv(clo),
    clo.students_took ?? "",
    clo.students_passed ?? "",
    calculateSuccessRate(clo),
    clo.term_name || "",
    clo.assessment_tool || "",
  ]);

  const csvLines = [
    headers.map(escapeForCsv).join(","),
    ...rows.map((row) => row.map(escapeForCsv).join(",")),
  ];
  const csvContent = csvLines.join("\n");

  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `outcome_audit_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  return true;
}

/**
 * Approve CLO (extracted for testability)
 */
async function approveCLO() {
  return auditCloActionsModule.approveCLO({
    getStatusBadge,
    formatDate,
  });
}

/**
 * Mark CLO as Never Coming In (NCI) (extracted for testability)
 */
async function markAsNCI() {
  return auditCloActionsModule.markAsNCI({
    getStatusBadge,
    formatDate,
  });
}

/**
 * Render history cell content (extracted for testability)
 */
function renderHistoryCellContent(clo) {
  const historyContainer = document.createElement("div");
  historyContainer.className = "small text-muted";

  if (clo.history && clo.history.length > 0) {
    // Show first 2 events
    const eventsToShow = clo.history.slice(0, 2);
    eventsToShow.forEach((entry) => {
      const eventDiv = document.createElement("div");
      eventDiv.className = "history-event";
      eventDiv.textContent = `${entry.event} - ${formatDate(entry.occurred_at)}`;
      historyContainer.appendChild(eventDiv);
    });

    // Show "and X more" if there are additional events
    if (clo.history.length > 2) {
      const moreDiv = document.createElement("div");
      moreDiv.className = "text-primary";
      moreDiv.style.cursor = "pointer";
      moreDiv.textContent = `and ${clo.history.length - 2} more...`;
      moreDiv.title = "Click to view full history";
      historyContainer.appendChild(moreDiv);
    }
  } else {
    historyContainer.textContent = "No history";
  }

  return historyContainer;
}

/**
 * Render CLO details in modal (extracted for testability)
 */
function renderCLODetails(clo) {
  return auditCloActionsModule.renderCLODetails(clo, {
    formatDate,
    getStatusBadge,
  });
}

// Global variables
let allCLOs = [];
// Expose for testing
if (typeof globalThis !== "undefined") {
  globalThis._getAllCLOs = () => allCLOs;
}

// Assign to globalThis IMMEDIATELY for browser use (not inside DOMContentLoaded)
// This ensures functions are available even if DOM is already loaded
// Note: globalThis is preferred over window for ES2020 cross-environment compatibility
// Register global functions
globalThis.approveCLO = approveCLO;
globalThis.markAsNCI = markAsNCI;
globalThis.approveOutcome = approveOutcome;
globalThis.assignOutcome = assignOutcome;
globalThis.reopenOutcome = reopenOutcome;
globalThis.remindOutcome = remindOutcome;
globalThis.submitReminder = submitReminder;

/**
 * Direct Approve from Table
 */
async function approveOutcome(outcomeId) {
  return auditCloActionsModule.approveOutcome(outcomeId);
}

/**
 * Assign Instructor (Native Modal)
 */
async function assignOutcome(outcomeId) {
  return auditCloActionsModule.assignOutcome(
    outcomeId,
    allCLOs,
    loadInstructors,
    handleAssignSubmit,
  );
}

async function loadInstructors() {
  return auditCloActionsModule.loadInstructors();
}

async function handleAssignSubmit(e) {
  return auditCloActionsModule.handleAssignSubmit(e);
}

async function handleInviteInstructorSubmit(event) {
  return auditCloActionsModule.handleInviteInstructorSubmit(event);
}

/**
 * Reopen Outcome (Set status to in_progress)
 */
async function reopenOutcome(outcomeId) {
  if (
    !confirm(
      "Are you sure you want to reopen this outcome? Status will be set to 'In Progress'.",
    )
  ) {
    return;
  }
  try {
    const csrfToken = document.querySelector(
      'meta[name="csrf-token"]',
    )?.content;
    const res = await fetch(`/api/outcomes/${outcomeId}/reopen`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
    });
    if (res.ok) {
      const modalEl = document.getElementById("cloDetailModal");
      const modal = bootstrap.Modal.getInstance(modalEl);
      if (modal) {
        modal.hide();
      } else {
        // Fallback: force-close when Bootstrap loses the instance
        modalEl.classList.remove("show");
        modalEl.style.display = "none";
        modalEl.setAttribute("aria-hidden", "true");
        document.body.classList.remove("modal-open");
        document.querySelector(".modal-backdrop")?.remove();
      }

      await globalThis.loadCLOs();
    } else {
      const err = await res.json();
      alert("Failed to reopen: " + (err.error || "Unknown error"));
    }
  } catch (e) {
    alert("Error reopening outcome: " + e.message);
  }
}

function formatShortDate(dateString) {
  if (!dateString) return null;
  const date = new Date(dateString);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date.toLocaleDateString();
}

/**
 * Send Reminder (opens modal and populates message)
 */
async function remindOutcome(outcomeId, instructorId, courseId) {
  return auditCloActionsModule.remindOutcome(
    outcomeId,
    instructorId,
    courseId,
    allCLOs,
  );
}

/**
 * Submit reminder email
 */
async function submitReminder(event) {
  return auditCloActionsModule.submitReminder(event);
}

document.addEventListener("DOMContentLoaded", () => {
  // DOM elements
  const statusFilter = document.getElementById("statusFilter");
  const sortBy = document.getElementById("sortBy");
  const sortOrder = document.getElementById("sortOrder");
  const programFilter = document.getElementById("programFilter");
  const termFilter = document.getElementById("termFilter");
  const courseFilter = document.getElementById("courseFilter");
  const exportButton = document.getElementById("exportCsvBtn");
  const cloListContainer = document.getElementById("cloListContainer");
  const cloDetailModal = document.getElementById("cloDetailModal");
  const cloReworkSection = document.getElementById("cloReworkSection");
  const cloReworkForm = document.getElementById("cloReworkForm");
  const reworkFeedbackTextarea = document.getElementById(
    "reworkFeedbackComments",
  );
  const reworkSendEmailCheckbox = document.getElementById("reworkSendEmail");
  const reworkAlert = document.getElementById("reworkAlert");
  const sendReminderForm = document.getElementById("sendReminderForm");
  const inviteNewInstructorBtn = document.getElementById(
    "inviteNewInstructorBtn",
  );
  const inviteInstructorModal = document.getElementById(
    "inviteInstructorModal",
  );
  const inviteInstructorForm = document.getElementById("inviteInstructorForm");
  // Removed unused button assignments to fix ESLint no-unused-vars
  const cancelReworkBtn = document.getElementById("cancelReworkBtn");
  const cloDetailActionsStandard = document.getElementById(
    "cloDetailActionsStandard",
  );
  const cloDetailActionsRework = document.getElementById(
    "cloDetailActionsRework",
  );

  // State - use window for global access by extracted functions
  globalThis.currentCLO = null;
  allCLOs = [];

  // Expose functions on window for access by extracted functions (approveCLO, markAsNCI)
  globalThis.loadCLOs = loadCLOs;
  globalThis.updateStats = updateStats;
  globalThis.pendingReworkOutcomeId = null;

  // Initialize
  initialize();

  // Event listeners
  statusFilter.addEventListener("change", loadCLOs);
  sortBy.addEventListener("change", renderCLOList);
  sortOrder.addEventListener("change", renderCLOList);
  if (programFilter) {
    programFilter.addEventListener("change", loadCLOs);
  }
  if (termFilter) {
    termFilter.addEventListener("change", loadCLOs);
  }
  if (courseFilter) {
    courseFilter.addEventListener("change", loadCLOs);
  }
  if (exportButton) {
    exportButton.addEventListener("click", () => {
      exportCurrentViewToCsv(allCLOs);
    });
  }

  // Event delegation for CLO row clicks
  cloListContainer.addEventListener("click", (e) => {
    const row = e.target.closest("tr[data-outcome-id]");
    if (row && !e.target.closest(".clo-actions")) {
      const outcomeId = row.dataset.outcomeId;
      if (outcomeId) {
        globalThis.showCLODetails(outcomeId);
      }
      return;
    }

    // Handle View button clicks
    const viewBtn = e.target.closest("button[data-outcome-id]");
    if (viewBtn) {
      e.stopPropagation();
      const outcomeId = viewBtn.dataset.outcomeId;
      if (outcomeId) {
        globalThis.showCLODetails(outcomeId);
      }
    }
  });

  if (cloReworkForm) {
    cloReworkForm.addEventListener("submit", submitReworkRequest);
  }
  if (cancelReworkBtn) {
    cancelReworkBtn.addEventListener("click", () => {
      toggleReworkMode(false);
    });
  }
  if (sendReminderForm) {
    sendReminderForm.addEventListener("submit", submitReminder);
  }
  if (inviteNewInstructorBtn && inviteInstructorModal) {
    inviteNewInstructorBtn.addEventListener("click", (event) => {
      event.preventDefault();
      const assignModalEl = document.getElementById("assignInstructorModal");
      const assignModal = assignModalEl
        ? bootstrap.Modal.getInstance(assignModalEl)
        : null;
      if (assignModal) {
        assignModal.hide();
      }
      bootstrap.Modal.getOrCreateInstance(inviteInstructorModal).show();
    });
  }
  if (inviteInstructorForm) {
    inviteInstructorForm.addEventListener(
      "submit",
      handleInviteInstructorSubmit,
    );
  }
  toggleReworkMode(false);

  /**
   * Initialize filters (programs, terms, courses) with loading spinners.
   * All three fetches fire in parallel; each select re-enables once its own
   * response arrives (same pattern as plo_dashboard._loadFilters).
   */
  async function initialize() {
    setSelectLoading(programFilter, "Loading programs…");
    setSelectLoading(termFilter, "Loading terms…");
    setSelectLoading(courseFilter, "Loading courses…");

    async function loadPrograms() {
      try {
        const resp = await fetch("/api/programs");
        setSelectReady(programFilter);
        if (!resp.ok || !programFilter) return;
        const { programs = [] } = await resp.json();
        programs.forEach((prog) => {
          const option = document.createElement("option");
          option.value = prog.program_id || prog.id;
          option.textContent = prog.name;
          programFilter.appendChild(option);
        });
      } catch (_) {
        setSelectReady(programFilter);
      }
    }

    async function loadTerms() {
      try {
        const resp = await fetch("/api/terms?all=true");
        setSelectReady(termFilter);
        if (!resp.ok || !termFilter) return;
        const { terms = [] } = await resp.json();
        terms
          .sort((a, b) => new Date(b.start_date) - new Date(a.start_date))
          .forEach((term) => {
            const option = document.createElement("option");
            option.value = term.term_id || term.id || "";
            option.textContent = term.term_name || term.name || "Term";
            termFilter.appendChild(option);
          });
      } catch (_) {
        setSelectReady(termFilter);
      }
    }

    async function loadCourses() {
      try {
        const resp = await fetch("/api/courses");
        setSelectReady(courseFilter);
        if (!resp.ok || !courseFilter) return;
        const { courses = [] } = await resp.json();
        courses
          .sort((a, b) =>
            (a.course_number || "").localeCompare(b.course_number || ""),
          )
          .forEach((course) => {
            const option = document.createElement("option");
            option.value = course.course_id || course.id;
            option.textContent = `${course.course_number} - ${course.course_title}`;
            courseFilter.appendChild(option);
          });
      } catch (_) {
        setSelectReady(courseFilter);
      }
    }

    try {
      await Promise.all([loadPrograms(), loadTerms(), loadCourses()]);
      // Initial load of CLOs
      await loadCLOs();
    } catch (error) {
      // eslint-disable-next-line no-console
      console.error("Failed to initialize filters:", error);
      // Fallback to loading CLOs even if filters fail
      await loadCLOs();
    }
  }

  /**
   * Load CLOs from API
   */
  async function loadCLOs() {
    const previousScroll =
      window.scrollY || document.documentElement.scrollTop || 0;
    globalThis.loadCLOs = loadCLOs;
    try {
      const status = statusFilter.value;
      const programId = programFilter ? programFilter.value : "";
      const termId = termFilter ? termFilter.value : "";
      const courseId = courseFilter ? courseFilter.value : "";

      const params = new URLSearchParams();
      if (status !== "all") params.append("status", status);
      if (programId) params.append("program_id", programId);
      if (termId) params.append("term_id", termId);
      if (courseId) params.append("course_id", courseId);

      const queryString = params.toString();
      const url = queryString
        ? `/api/outcomes/audit?${queryString}`
        : "/api/outcomes/audit";

      const response = await globalThis.fetch(url);
      if (!response.ok) {
        throw new Error("Failed to load CLOs");
      }

      const data = await response.json();
      allCLOs = data.outcomes || [];

      // Update stats
      updateStats();

      // Render list
      renderCLOList();

      // Restore scroll position once the new DOM has painted
      window.requestAnimationFrame(() => {
        window.scrollTo({
          top: previousScroll,
          behavior: "auto",
        });
      });
    } catch (error) {
      // Log error to aid debugging
      // eslint-disable-next-line no-console
      console.error("Error loading CLOs:", error);
      const errorDiv = document.createElement("div");
      errorDiv.className = "alert alert-danger";
      const strong = document.createElement("strong");
      strong.textContent = "Error:";
      errorDiv.appendChild(strong);
      // Add a space and plain-text error message to avoid HTML injection
      errorDiv.appendChild(
        document.createTextNode(
          " Failed to load CLOs. " +
            (error && error.message ? error.message : ""),
        ),
      );
      cloListContainer.prepend(errorDiv);
    }
  }

  /**
   * Update summary statistics
   * Top stats are UNFILTERED source of truth for the institution (not affected by filter dropdowns)
   * PERFORMANCE: Uses single API request with include_stats=true (was 7 separate requests)
   */
  async function updateStats() {
    try {
      // Fetch all outcomes with stats (single request replaces 7 separate requests)
      const response = await fetch(
        "/api/outcomes/audit?status=all&include_stats=true",
      );
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      const stats = data.stats_by_status || {};

      // Extract counts from stats (default to 0 if not present)
      const unassigned = stats.unassigned || 0;
      const assigned = stats.assigned || 0;
      const inProgress = stats.in_progress || 0;
      const pending = stats.approval_pending || 0;
      const awaiting = stats.awaiting_approval || 0;
      const approved = stats.approved || 0;
      const nci = stats.never_coming_in || 0;

      if (document.getElementById("statUnassigned")) {
        document.getElementById("statUnassigned").textContent = unassigned;
      }
      if (document.getElementById("statAssigned")) {
        document.getElementById("statAssigned").textContent = assigned;
      }
      document.getElementById("statInProgress").textContent = inProgress;
      document.getElementById("statNeedsRework").textContent = pending;
      document.getElementById("statAwaitingApproval").textContent = awaiting;
      document.getElementById("statApproved").textContent = approved;
      if (document.getElementById("statNCI")) {
        document.getElementById("statNCI").textContent = nci;
      }
    } catch (error) {
      // Log error to aid debugging, but allow graceful degradation
      // Stats are nice-to-have, not critical functionality
      // eslint-disable-next-line no-console
      console.warn(
        "Error updating dashboard stats (non-critical):",
        error.message || error,
      );
    }
  }

  /**
   * Render CLO list
   */
  function renderCLOList() {
    return auditCloListModule.renderCLOList({
      allCLOs,
      cloListContainer,
      getStatusBadge,
      renderHistoryCellContent,
      sortCLOs,
      approveOutcome,
      assignOutcome,
      remindOutcome,
    });
  }

  /**
   * Sort CLOs based on current sort settings
   */
  function sortCLOs(clos) {
    const by = sortBy.value;
    const order = sortOrder.value;

    clos.sort((a, b) => {
      let aVal, bVal;

      switch (by) {
        case "submitted_at":
          aVal = a.submitted_at || "";
          bVal = b.submitted_at || "";
          break;
        case "course_number":
          aVal = a.course_number || "";
          bVal = b.course_number || "";
          break;
        case "instructor_name":
          aVal = a.instructor_name || "";
          bVal = b.instructor_name || "";
          break;
        default:
          return 0;
      }

      let comparison;
      if (aVal < bVal) {
        comparison = -1;
      } else if (aVal > bVal) {
        comparison = 1;
      } else {
        comparison = 0;
      }
      return order === "asc" ? comparison : -comparison;
    });

    return clos;
  }

  /**
   * Show CLO details in modal
   */
  globalThis.showCLODetails = async function (cloId) {
    try {
      const response = await fetch(`/api/outcomes/${cloId}/audit-details`);
      if (!response.ok) {
        throw new Error("Failed to load CLO details");
      }

      const data = await response.json();
      globalThis.currentCLO = data.outcome;
      const clo = globalThis.currentCLO;

      // Render HTML using extracted function
      // nosemgrep
      const cloDetailContainer = document.getElementById(
        "cloDetailContentMain",
      );
      cloDetailContainer.replaceChildren(renderCLODetails(clo));

      // Show/hide action buttons based on status
      // Only show approve/rework for outcomes that backend can process
      const canApprove = ["awaiting_approval", "approval_pending"].includes(
        clo.status,
      );
      const canMarkNCI = [
        "awaiting_approval",
        "approval_pending",
        "assigned",
        "in_progress",
      ].includes(clo.status);
      const canReopen = ["approved", "never_coming_in"].includes(clo.status);
      const reopenBtn = document.getElementById("reopenBtn");
      if (reopenBtn) {
        reopenBtn.style.display = canReopen ? "inline-block" : "none";
        reopenBtn.onclick = () => reopenOutcome(clo.id);
      }

      const approveBtn = document.getElementById("approveBtn");
      if (approveBtn) {
        approveBtn.style.display = canApprove ? "inline-block" : "none";
        approveBtn.onclick = async () => {
          if (await approveOutcome(clo.id)) {
            bootstrap.Modal.getInstance(
              document.getElementById("cloDetailModal"),
            ).hide();
          }
        };
      }

      const requestReworkBtn = document.getElementById("requestReworkBtn");
      if (requestReworkBtn) {
        requestReworkBtn.style.display = canApprove ? "inline-block" : "none";
        requestReworkBtn.onclick = () => {
          globalThis.pendingReworkOutcomeId = clo.id || clo.outcome_id || null;
          globalThis.openReworkModal();
        };
      }

      const markNCIBtn = document.getElementById("markNCIBtn");
      if (markNCIBtn) {
        markNCIBtn.style.display = canMarkNCI ? "inline-block" : "none";
        markNCIBtn.onclick = () => markAsNCI(clo.id);
      }

      const modal = new bootstrap.Modal(cloDetailModal);
      modal.show();

      toggleReworkMode(false);
      if (
        globalThis.pendingReworkOutcomeId &&
        (clo.id || clo.outcome_id) === globalThis.pendingReworkOutcomeId
      ) {
        globalThis.openReworkModal();
        globalThis.pendingReworkOutcomeId = null;
      }
    } catch (error) {
      alert("Failed to load Outcome details: " + error.message);
    }
  };

  /**
   * Activate rework mode inside the detail modal
   */
  globalThis.openReworkModal = function () {
    if (!globalThis.currentCLO) return;
    if (!cloReworkSection || !cloReworkForm) return;

    reworkFeedbackTextarea.value = "";
    reworkSendEmailCheckbox.checked = true;
    reworkAlert.classList.add("d-none");
    const descriptionEl = document.getElementById("reworkCloDescription");
    if (descriptionEl) {
      descriptionEl.textContent = `${globalThis.currentCLO.course_number} - Outcome ${globalThis.currentCLO.clo_number}: ${globalThis.currentCLO.description}`;
    }

    enterReworkMode();
  };

  function toggleReworkMode(show) {
    if (cloReworkSection) {
      cloReworkSection.style.display = show ? "block" : "none";
    }
    if (cloDetailActionsStandard) {
      cloDetailActionsStandard.style.display = show ? "none" : "flex";
    }
    if (cloDetailActionsRework) {
      cloDetailActionsRework.style.display = show ? "flex" : "none";
    }
    globalThis.reworkMode = show;
  }

  function enterReworkMode() {
    toggleReworkMode(true);
    if (reworkFeedbackTextarea) {
      reworkFeedbackTextarea.focus();
    }
  }

  /**
   * Submit rework request
   */
  async function submitReworkRequest(event) {
    if (event && typeof event.preventDefault === "function") {
      event.preventDefault();
    }

    if (!globalThis.currentCLO) return;
    if (!reworkFeedbackTextarea) return;

    const comments = reworkFeedbackTextarea.value.trim();
    const sendEmail = reworkSendEmailCheckbox?.checked ?? true;

    if (!comments) {
      showReworkAlert("Please provide feedback comments.", "danger");
      return;
    }

    const outcomeId = globalThis.currentCLO.id;
    if (!outcomeId) {
      showReworkAlert("Error: Outcome ID not found.", "danger");
      return;
    }

    try {
      const csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
      const csrfToken = csrfTokenMeta ? csrfTokenMeta.content : null;

      const response = await fetch(
        `/api/outcomes/${outcomeId}/request-rework`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": csrfToken,
          },
          body: JSON.stringify({
            comments,
            send_email: sendEmail,
          }),
        },
      );

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || "Failed to request rework");
      }

      const result = await response.json();
      console.log("[Rework Request] Response:", result);

      let message = "Rework request recorded successfully!";
      let alertType = "success";

      if (sendEmail) {
        if (result.email_sent) {
          message += " Email notification sent to instructor.";
        } else {
          message += " WARNING: Email notification failed to send.";
          alertType = "warning";
        }
      }

      showReworkAlert(message, alertType);

      toggleReworkMode(false);
      const modalInstance = bootstrap.Modal.getInstance(cloDetailModal);
      if (modalInstance) {
        modalInstance.hide();
      }

      await loadCLOs();
    } catch (error) {
      showReworkAlert("Failed to request rework: " + error.message, "danger");
    }
  }

  function showReworkAlert(message, variant = "info") {
    if (!reworkAlert) return;
    reworkAlert.textContent = message;
    reworkAlert.className = `alert alert-${variant}`;
    reworkAlert.classList.remove("d-none");
  }
});

// Export for testing (Node.js environment only)
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    getStatusBadge,
    formatDate,
    truncateText,
    escapeHtml,
    renderHistoryCellContent,
    renderCLODetails,
    approveCLO,
    markAsNCI,
    formatStatusLabel,
    formatDateForCsv,
    escapeForCsv,
    calculateSuccessRate,
    exportCurrentViewToCsv,
    // DOM interaction functions (for unit testing)
    approveOutcome,
    assignOutcome,
    loadInstructors,
    handleAssignSubmit,
    reopenOutcome,
    remindOutcome,
    submitReminder,
    // Note: sortCLOs and submitReworkRequest are inside DOMContentLoaded
    // and cannot be exported (they depend on DOM element references)
    // Expose internal state accessor for testing
    _getAllCLOs: () => allCLOs,
    _setAllCLOs: (clos) => {
      allCLOs = clos;
    },
  };
}
