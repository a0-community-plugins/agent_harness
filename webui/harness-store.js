import { createStore } from "/js/AlpineStore.js";
import { callJsonApi } from "/js/api.js";
import {
  toastFrontendError,
  toastFrontendInfo,
  toastFrontendSuccess,
} from "/components/notifications/notification-store.js";

const STATE_ENDPOINT = "/plugins/agent_harness/state";
const RUN_ENDPOINT = "/plugins/agent_harness/run";
const MEMORY_QUEUE_ENDPOINT = "/plugins/agent_harness/memory_queue";
const TITLE = "Agent Harness";
const POLL_MS = 3000;

function currentContextId() {
  return globalThis.getContext?.() || "";
}

function dashboardDefaults() {
  return {
    show_status_ui: true,
    default_deep_mode: "pro",
    memory_curation_enabled: true,
  };
}

function errorMessage(error) {
  return error instanceof Error ? error.message : String(error);
}

export const store = createStore("agentHarness", {
  _mounted: 0,
  _loaded: false,
  _timer: null,
  _inflight: null,
  _inflightContext: "",
  _contextId: "",
  _requestSequence: 0,

  isLoading: false,
  isActing: false,
  error: "",

  dashboard: dashboardDefaults(),
  currentRun: null,
  pendingCheckpoints: [],
  memoryQueue: [],
  recentRules: [],
  latestVerification: null,

  phaseLabel(phase) {
    return (
      {
        idle: "Idle",
        inspect: "Inspect",
        plan: "Plan",
        implement: "Implement",
        verify: "Verify",
        repair: "Repair",
        blocked: "Blocked",
        summarize: "Summarize",
        complete: "Complete",
      }[phase] || phase || "Idle"
    );
  },

  statusButtonLabel() {
    if (!this.currentRun) return "";
    return `${String(this.currentRun.mode || "").toUpperCase()} · ${this.phaseLabel(this.currentRun.phase)}`;
  },

  get completedGraphTasks() {
    return (this.currentRun?.task_graph?.sub_tasks || []).filter(
      (task) => task.status === "completed",
    ).length;
  },

  get totalGraphTasks() {
    return (this.currentRun?.task_graph?.sub_tasks || []).length;
  },

  get hasAttention() {
    return Boolean(
      this.error
      || this.pendingCheckpoints.length
      || this.currentRun?.status === "blocked"
      || (this.currentRun?.failures || []).length,
    );
  },

  _resetContextState(contextId = "") {
    this._contextId = contextId;
    this.dashboard = dashboardDefaults();
    this.currentRun = null;
    this.pendingCheckpoints = [];
    this.memoryQueue = [];
    this.recentRules = [];
    this.latestVerification = null;
    this.error = "";
    this.isLoading = false;
    this._loaded = false;
  },

  async openObservability() {
    const canvas = globalThis.Alpine?.store("rightCanvas");
    if (canvas?.open) {
      const opened = await canvas.open("agent-harness");
      if (opened) return true;
    }
    if (typeof globalThis.openModal === "function") {
      globalThis.openModal("/plugins/agent_harness/webui/main.html");
      return true;
    }
    return false;
  },

  async onMount() {
    this._mounted += 1;
    await this.loadState();
    this._ensurePolling();
  },

  cleanup() {
    this._mounted = Math.max(0, this._mounted - 1);
    if (this._mounted === 0 && this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  },

  _ensurePolling() {
    if (this._timer) return;
    this._timer = setInterval(() => {
      void this.loadState({ silent: true });
    }, POLL_MS);
  },

  async loadState({ silent = false } = {}) {
    const contextId = currentContextId();
    if (!contextId) {
      if (this._contextId) this._resetContextState("");
      return null;
    }

    if (contextId !== this._contextId) {
      this._requestSequence += 1;
      this._resetContextState(contextId);
    }

    if (this._inflight && this._inflightContext === contextId) {
      return await this._inflight;
    }

    const requestSequence = ++this._requestSequence;
    let request;
    request = (async () => {
      if (!silent) this.isLoading = true;
      this.error = "";
      try {
        const response = await callJsonApi(STATE_ENDPOINT, { context_id: contextId });
        if (
          currentContextId() !== contextId
          || this._contextId !== contextId
          || this._requestSequence !== requestSequence
        ) {
          return null;
        }
        this.dashboard = { ...dashboardDefaults(), ...(response?.dashboard || {}) };
        this.currentRun = response?.run || null;
        this.pendingCheckpoints = Array.isArray(response?.pending_checkpoints)
          ? response.pending_checkpoints
          : [];
        this.memoryQueue = Array.isArray(response?.pending_memory_candidates)
          ? response.pending_memory_candidates
          : [];
        this.recentRules = Array.isArray(response?.recent_rules) ? response.recent_rules : [];
        this.latestVerification = response?.latest_verification || null;
        this._loaded = true;
        return response;
      } catch (error) {
        if (
          currentContextId() !== contextId
          || this._contextId !== contextId
          || this._requestSequence !== requestSequence
        ) {
          return null;
        }
        this.error = errorMessage(error);
        if (!silent) {
          void toastFrontendError(`Failed to load harness state: ${this.error}`, TITLE);
        }
        return null;
      } finally {
        if (this._requestSequence === requestSequence && !silent) {
          this.isLoading = false;
        }
        if (this._inflight === request) {
          this._inflight = null;
          this._inflightContext = "";
        }
      }
    })();

    this._inflight = request;
    this._inflightContext = contextId;
    return await request;
  },

  async refresh() {
    await this.loadState();
    toastFrontendInfo("Harness state refreshed.", TITLE);
  },

  async _runAction(endpoint, payload, successMessage = "") {
    const contextId = currentContextId();
    if (!contextId) {
      void toastFrontendError("No active chat context is selected.", TITLE);
      return null;
    }

    this.isActing = true;
    try {
      const result = await callJsonApi(endpoint, { context_id: contextId, ...payload });
      if (successMessage) {
        toastFrontendSuccess(successMessage, TITLE);
      }
      await this.loadState({ silent: true });
      return result;
    } catch (error) {
      void toastFrontendError(errorMessage(error), TITLE);
      return null;
    } finally {
      this.isActing = false;
    }
  },

  async startRun(mode) {
    const defaultObjective = this.currentRun?.objective || "Active coding task";
    const objective = window.prompt("Harness objective", defaultObjective);
    if (objective === null) return;

    const trimmedObjective = objective.trim() || defaultObjective;
    await this._runAction(
      RUN_ENDPOINT,
      {
        action: "start",
        mode: mode || this.dashboard.default_deep_mode || "pro",
        objective: trimmedObjective,
      },
      `Started ${String(mode || this.dashboard.default_deep_mode || "pro").toUpperCase()} mode.`,
    );
  },

  async stopRun() {
    if (!window.confirm("Stop the current harness run?")) return;
    await this._runAction(RUN_ENDPOINT, { action: "stop" }, "Harness run stopped.");
  },

  async decideCheckpoint(checkpointId, decision) {
    const actionLabel = decision === "approved" ? "approved" : "rejected";
    await this._runAction(
      RUN_ENDPOINT,
      {
        action: "checkpoint_decide",
        checkpoint_id: checkpointId,
        decision,
      },
      `Checkpoint ${actionLabel}.`,
    );
  },

  async acceptCandidate(candidateId, scope) {
    await this._runAction(
      MEMORY_QUEUE_ENDPOINT,
      {
        action: "accept",
        candidate_id: candidateId,
        scope: scope || "project",
      },
      "Harness memory accepted.",
    );
  },

  async rejectCandidate(candidateId) {
    await this._runAction(
      MEMORY_QUEUE_ENDPOINT,
      {
        action: "reject",
        candidate_id: candidateId,
      },
      "Harness memory rejected.",
    );
  },
});
