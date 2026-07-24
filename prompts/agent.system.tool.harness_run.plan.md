### Ultra planning with harness_run

`harness_run action="plan"` is available only in Ultra mode.

Create at least one scoped sub-task. Use roles:

- `research`: read code or primary documentation and report evidence
- `code`: implement a non-overlapping change
- `verify`: run focused checks
- `synthesize`: combine completed dependency results

Dependencies are zero-based indexes into the submitted list. Parallel workers
share the same filesystem, so never dispatch code tasks that may edit the same
files. After the plan is accepted, use `dispatch`, then `collect`, until every
task is complete. Run a final integrated verification in the main chat before
completing the run.
