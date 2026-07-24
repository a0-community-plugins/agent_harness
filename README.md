# Agent Harness

Agent Harness adds a coding workflow, safety checkpoints, per-chat workspaces,
and optional parallel task execution to Agent Zero without modifying Agent Zero
core code.

The design borrows useful harness ideas from
[ByteDance DeerFlow](https://github.com/bytedance/deer-flow), but this is an
Agent Zero plugin rather than a port of DeerFlow's LangGraph server, gateway,
channel integrations, sandbox providers, or frontend.

## Pro and Ultra are intentionally different

| Mode | Execution model | Planning | Background workers | Use it for |
| --- | --- | --- | --- | --- |
| `flash` | single agent | minimal | none | small, low-risk changes |
| `standard` | single agent | optional | none | ordinary implementation work |
| `pro` | structured single agent | explicit for multi-step or risky work | none | most serious coding tasks |
| `ultra` | task graph plus main agent | mandatory | 1-4 | independent, decomposable work |

`pro` is the recommended default. It keeps inspect, plan, implement, verify,
and completion discipline without paying the coordination cost of worker
agents.

Use `ultra` only when the task can be separated into non-overlapping units.
Ultra requires a task graph before implementation and is the only mode allowed
to call `plan`, `dispatch`, `collect`, or `adopt`. Workers have isolated Agent
Zero contexts and harness runs, but they share the same filesystem. A worker
that reaches an approval boundary stops and reports the exact action to the main
chat instead of bypassing the checkpoint.

Legacy saved mode names are normalized automatically:

- `assist` becomes `flash`
- `build` becomes `pro`
- `surge` becomes `ultra`

## What the plugin adds

- Full workflow instructions injected into Agent Zero's runtime prompt
- Explicit run mode, phase, objective, risk, task, verification, and failure
  state
- Action-bound, single-use approval checkpoints
- An Ultra-only task graph with bounded concurrent workers
- Reviewable project, agent, or global harness rules
- Per-chat scratch, upload, and output directories
- A theme-native right-side observability canvas and compact status control
  with no runtime CDN dependency
- Approximate completion-token tracking and an optional one-time budget pause

Ambient Assist supplies lightweight inspect-and-verify guidance even when a
formal run has not been started. It can be disabled in plugin settings.

## Installation and updates

Install the plugin through Agent Zero's plugin manager, then enable it globally
or for the desired project or agent.

There is no separate Execute step. Agent Zero calls `hooks.py` during install,
update, and removal. Those hooks stop background workers and clear plugin module
and bytecode caches so an update does not leave stale worker threads or Python
modules behind.

The plugin has no additional Python package installation step.

If Agent Zero reports `Need to specify how to reconcile divergent branches`,
the installed plugin checkout contains Git history that no longer fast-forwards
to the repository's `main`. Back up any local plugin changes, then reinstall the
plugin or explicitly return that checkout to the repository's `main`. The
plugin cannot safely reset that checkout from `hooks.py` because Agent Zero's
Git update fails before the new hook code is loaded.

## Recommended workflow

For most work:

1. Enter a concrete objective in the Harness canvas and choose `Start Pro`.
2. Send the next chat message to begin the guided workflow.
3. Inspect the relevant repository and constraints.
4. Move through plan and implementation in the main agent.
5. Run a concrete verification command.
6. Record the verification result and complete the run.

For safely decomposable work:

1. Enter a concrete objective in the Harness canvas and choose `Start Ultra`.
2. Send the next chat message to begin the guided workflow.
3. Submit a task graph with explicit dependencies.
4. Dispatch only tasks that can edit without overlap.
5. Collect worker results until the graph is complete.
6. Repair or manually adopt any failed task in the main chat.
7. Run and record a passing integration verification.
8. Complete the run.

Completion fails closed when the latest verification is not passing. Ultra also
requires every task in its graph to be completed successfully.

## Safety checkpoints

The default policy requires approval before:

- dependency installs such as `pip`, `uv`, `npm`, `brew`, or `apt`
- destructive filesystem or Git commands
- Git mutations such as commit, push, merge, rebase, branch, tag, or stash
- edits to a configured protected path
- exceeding the automatic distinct-file edit limit

Default protected paths are:

- `agent.py`
- `initialize.py`
- `usr/plugins/`

Read-only file access and read-only Git commands do not consume an edit
checkpoint. An approval is tied to the exact tool name and arguments and is
consumed by one execution attempt; changed arguments or retries require a new
approval.

The dashboard can approve or reject a pending checkpoint. While one is pending,
unrelated tool execution remains blocked so an agent cannot route around it.

## Tools

### `harness_run`

The run controller supports:

- `start`: create a run with `mode`, `objective`, and optional `constraints`
- `status`: report the current mode, phase, and state
- `phase`: advance to a valid lifecycle phase
- `task`: track a single-agent work item
- `plan`: Ultra only; submit a non-empty task graph
- `dispatch`: Ultra only; start ready tasks up to the worker limit
- `collect`: Ultra only; harvest worker results
- `adopt`: Ultra only; reconcile work completed in the main chat
- `verification`: record a passed, failed, or unknown check
- `failure`: record a bounded repair failure
- `clean`: clear the per-chat scratch workspace
- `complete`: finish only after the completion gates pass

### `harness_checkpoint`

Creates a manual checkpoint for an exact proposed tool action. Dependency,
destructive, Git-mutation, and protected-path guardrails also create
checkpoints automatically.

### `harness_memory_propose`

Proposes a durable harness rule for `project`, `agent`, or `global` scope.
Curated mode queues it for review. If curation is disabled, the rule is written
directly to the selected harness configuration scope.

Harness rules are not mirrored into Agent Zero's separate memory plugin.

## Per-chat data

Harness data stays under Agent Zero's chat storage. It does not create a
`.harness` directory in the attached project and does not edit the project's
`.gitignore`.

```text
<chat storage>/
  .harness/
    threads/
      <context_id>/
        user-data/
          workspace/
          uploads/
          outputs/
```

- `workspace/` is disposable scratch space.
- `uploads/` contains files uploaded for this chat.
- `outputs/` contains downloadable artifacts.

Upload paths and artifact paths are confined to their per-chat directories.
The API rejects traversal and symlink escapes, limits each upload to 25 MiB,
limits a request batch to 100 MiB, and lists at most 1,000 files.

## Settings

Workflow:

- Ambient Assist
- Default Mode
- Ultra Workers, clamped to 1-4
- Per-mode bounded repair limits

Safety:

- Dependency Install checkpoints
- Destructive Action checkpoints
- Git Mutation checkpoints
- Automatic Edit Limit
- Protected Paths

Data and status:

- Thread Workspace
- Curated Memory
- Status Chip
- Usage Tracking
- Approximate Output Budget

The plugin supports global, per-project, and per-agent configuration. Runtime
`config.json` is user state and is intentionally not included in the plugin
repository.

## Observability canvas

The compact Harness control beside the chat input opens a right-side canvas,
keeping observability visible beside the conversation without covering it. The
sidebar shortcut opens the same surface. On phone-sized layouts, where Agent
Zero disables its right canvas, the control falls back to the floating
dashboard.

The responsive canvas shows:

- an inline objective field and explicit Pro or Ultra start controls
- current objective, mode, phase, state, and risk
- Ultra task-graph progress and worker results
- pending approval checkpoints with approve and reject actions
- pending memory proposals
- latest verification, failures, and approximate token usage

The full floating dashboard remains available through the canvas undock action
and includes recent accepted rules plus per-chat upload/output management. The
task graph is rendered locally; the plugin does not load Mermaid or another
visualization package from a CDN.

## Development

The standalone regression suite can run outside Agent Zero with its included
host compatibility stubs:

```bash
python -m unittest discover -s tests -v
node --check webui/harness-store.js
python -m compileall -q .
```

The same tests can exercise a real Agent Zero checkout by setting:

```bash
A0_TEST_USE_REAL_CORE=1
A0_TEST_PROJECT_ROOT=/path/to/agent-zero
PYTHONPATH=/path/to/agent-zero
```

CI runs the standalone suite on Python 3.11, 3.12, and 3.13.

## License

MIT. See [LICENSE](LICENSE).
