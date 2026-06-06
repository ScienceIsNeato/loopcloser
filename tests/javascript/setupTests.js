require("@testing-library/jest-dom");

// dashboard_utils globals — available in the browser via base_dashboard.html;
// exposed here so any test that imports a script using these doesn't error.
const {
  setLoadingState,
  setErrorState,
  setEmptyState,
  setSelectLoading,
  setSelectReady,
} = require("../../static/dashboard_utils");
global.setLoadingState = setLoadingState;
global.setErrorState = setErrorState;
global.setEmptyState = setEmptyState;
global.setSelectLoading = setSelectLoading;
global.setSelectReady = setSelectReady;

// plo_summary_bar.js is loaded before plo_dashboard.js in the browser;
// expose its global so plo_dashboard tests don't error.
const { _buildPloSummaryBar } = require("../../static/plo_summary_bar");
global._buildPloSummaryBar = _buildPloSummaryBar;

// Polyfill globalThis for older Node.js versions
if (typeof globalThis === "undefined") {
  global.globalThis = global;
}

// Ensure globalThis.location exists
if (!globalThis.location) {
  globalThis.location = { origin: "http://localhost:3000" };
}

const modalInstances = new WeakMap();

class BootstrapModalMock {
  constructor(element) {
    this.element = element;
    this.visible = false;
    modalInstances.set(element, this);
  }

  show() {
    this.visible = true;
    // Dispatch the shown.bs.modal event to match real Bootstrap behavior
    if (this.element) {
      this.element.dispatchEvent(new Event("shown.bs.modal"));
    }
  }

  hide() {
    this.visible = false;
  }

  static getInstance(element) {
    return modalInstances.get(element);
  }
}

Object.defineProperty(global, "bootstrap", {
  configurable: true,
  writable: true,
  value: { Modal: BootstrapModalMock },
});

// jsdom doesn't implement scrollTo; some dashboard code uses it.
try {
  Object.defineProperty(globalThis, "scrollTo", {
    configurable: true,
    writable: true,
    value: jest.fn(),
  });
} catch {
  // ignore
}

// jsdom navigation is limited; prevent hard failures when code calls location APIs.
try {
  Object.defineProperty(globalThis.location, "assign", {
    configurable: true,
    value: jest.fn(),
  });
  Object.defineProperty(globalThis.location, "replace", {
    configurable: true,
    value: jest.fn(),
  });
  Object.defineProperty(globalThis.location, "reload", {
    configurable: true,
    value: jest.fn(),
  });
} catch {
  // Ignore if jsdom marks these as non-configurable in this environment.
}

if (!HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = jest.fn();
}

Object.defineProperty(globalThis, "matchMedia", {
  writable: true,
  value: jest.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(),
    removeListener: jest.fn(),
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
});

beforeEach(() => {
  jest.clearAllMocks();
  document.body.innerHTML = "";
  document.head.innerHTML = "";
  global.fetch = jest.fn();
  global.confirm = jest.fn(() => true);
  global.alert = jest.fn();
});

afterEach(() => {
  jest.useRealTimers();
});
