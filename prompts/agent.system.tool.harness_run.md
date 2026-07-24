### harness_run
manage the active Agent Harness run

The active runtime prompt defines the current mode and phase. Follow it exactly.

#### Mode boundary

- `flash`, `standard`, and `pro` are single-agent modes. Do not use `plan`,
  `dispatch`, `collect`, or `adopt` in those modes.
- `ultra` is the task-graph mode. It requires
  `plan -> dispatch -> collect -> verify -> complete`.
- Parallel workers share the project workspace. Only plan tasks whose edits do
  not overlap. A worker that reaches an approval boundary stops so the main chat
  can perform that action safely.

#### Actions

- `start`: begin a run with `mode`, `objective`, and optional `constraints`
- `status`: summarize the current run
- `phase`: move to a valid lifecycle phase
- `plan`: Ultra only; submit a non-empty task graph
- `dispatch`: Ultra only; start ready tasks up to the configured worker limit
- `collect`: Ultra only; harvest completed worker results
- `adopt`: Ultra only; reconcile a failed or manually completed task with
  `sub_task_id`, optional `summary`, and optional `result_files`
- `task`: track a single-agent task item with `task_title`, optional
  `task_status`, and optional `task_details`
- `verification`: record a concrete check using `verification_name`,
  `verification_status` (`passed`, `failed`, or `unknown`), and
  `verification_summary`
- `failure`: record a bounded repair failure
- `clean`: clear temporary harness workspace data
- `complete`: finish only after every planned task is complete and the latest
  verification passed

Ultra plan example:

~~~json
{
  "tool_name": "harness_run",
  "tool_args": {
    "action": "plan",
    "sub_tasks": [
      {
        "title": "Research existing patterns",
        "description": "Read the relevant code and report constraints",
        "role": "research"
      },
      {
        "title": "Implement the fix",
        "description": "Change the isolated implementation files",
        "role": "code",
        "depends_on": [0]
      },
      {
        "title": "Verify behavior",
        "description": "Run the focused regression checks",
        "role": "verify",
        "depends_on": [1]
      }
    ]
  }
}
~~~
