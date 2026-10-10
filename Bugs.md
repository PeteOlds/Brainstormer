
# Bug log — all items below are CLOSED (verified 2026-10-08, v0.49.0 working tree).

### Run dialog crash (reported 2026-10-08)
- [CLOSED] "Failed to run action: Cannot set properties of null (setting 'actions')" after Recreate + Guide select. Three stacked causes, all fixed in `app/templates/ideas/dashboard.html`: (1) the run/confirm dialogs sit OUTSIDE the detail modal element, so any click inside them fired the detail modal's `@click.outside` and nulled `selectedIdea` mid-flow — the detail modal now ignores outside clicks while a child modal is open; (2) the action poll matched STALE results from previous runs (instant "completion" with old data) — it now waits for a result id unseen before submit; (3) the poll wrote straight onto a possibly-null `selectedIdea` — it now updates the detail or the list item, whichever exists. Verified by A/B in headless Chromium: old code reproduces the exact alert, fixed code submits silently with the guideline in the POST body and the detail modal staying open. (Your DESIGN_DOC run itself was unaffected — it was RUNNING server-side throughout.)

### Secondary Actions
#### Scope
- [CLOSED] "Generate PRD" should be "Product Requirements Doc" (or "PRD") → registry label is now "PRD" (menu buttons, run dialog title and confirm modal read "Run PRD").
- [CLOSED] After a PRD has been rerun, it sometimes looses existing answers → two causes fixed: (1) answers were stored per-version so each rerun displayed only its own submission — versions now accumulate all answers to date (`_accumulate_answers`, newest text wins on repeats); (2) the answer draft was cleared even when the submit failed — the draft is now kept unless the run is accepted. Regression test: `test_prd_rerun_accumulates_answers`.

#### Map
- [CLOSED] "Generate Design" should be "Design" → registry label is now "Design".
- [CLOSED] User should be able to select multiple Skills → verified end-to-end in headless Chromium: checking two skills posts `"skills": ["find-skills", "frontend-design"]`, backend accepts lists (≤20) and the task injects every selected skill. Also removed the status gate that hid the Skills section except on SCOPE/MAP/SHIP/SCALE/FREEZE, so skills are selectable for any action.
- [CLOSED] AI Model drop down should show speed icons (as per the Model selection drop down under Prompt Configurations) → the run dialog now keeps model objects and renders the same badges (`🚀` < 3GB, `🐇` 3–7GB, `🐢` above), verified live (e.g. `llama3:8b 🐇`).




### Backup
- [CLOSED] `flask backup-site` crashed with `UndefinedColumn: column instance_ai_configs.opencode_workspace does not exist` → the `fc0b1c2d3e4f` migration had not been applied on prod after the 0.48.0 deploy. Ran `docker exec brainstormer-web flask db upgrade` on 2026-10-08; `backup-site` verified working afterwards (3922 rows exported). Original traceback kept below for the record.
pete@brian:/mnt/General/OpenCode$ docker exec brainstormer-web flask backup-site \
  --output /app/backups/pre-manual-test-$(date +%F-%H%M).json
Traceback (most recent call last):
  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1969, in _exec_single_context
    self.dialect.do_execute(
  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/engine/default.py", line 952, in do_execute
    cursor.execute(statement, parameters)
psycopg2.errors.UndefinedColumn: column instance_ai_configs.opencode_workspace does not exist
LINE 1: ...chat_enabled AS instance_ai_configs_chat_enabled, instance_a...
                                                             ^


The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/usr/local/bin/flask", line 8, in <module>
    sys.exit(main())
             ^^^^^^
  File "/usr/local/lib/python3.12/site-packages/flask/cli.py", line 1131, in main
    cli.main()
  File "/usr/local/lib/python3.12/site-packages/click/core.py", line 1552, in main
    rv = self.invoke(ctx)
         ^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/click/core.py", line 2032, in invoke
    return _process_result(sub_ctx.command.invoke(sub_ctx))
                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/click/core.py", line 1415, in invoke
    return ctx.invoke(self.callback, **ctx.params)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/click/core.py", line 910, in invoke
    return callback(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/click/decorators.py", line 34, in new_func
    return f(get_current_context(), *args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/flask/cli.py", line 400, in decorator
    return ctx.invoke(f, *args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/click/core.py", line 910, in invoke
    return callback(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/app/app/cli.py", line 118, in backup_site
    bundle = backup_svc.export_site()
             ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/app/app/services/backup.py", line 172, in export_site
    data = {model.__tablename__: _export_rows(model) for model in EXPORT_TABLES}
                                 ^^^^^^^^^^^^^^^^^^^
  File "/app/app/services/backup.py", line 152, in _export_rows
    for obj in query.all():
               ^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/orm/query.py", line 2711, in all
    return self._iter().all()  # type: ignore
           ^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/orm/query.py", line 2864, in _iter
    result: Union[ScalarResult[_T], Result[_T]] = self.session.execute(
                                                  ^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/orm/session.py", line 2373, in execute
    return self._execute_internal(
           ^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/orm/session.py", line 2271, in _execute_internal
    result: Result[Any] = compile_state_cls.orm_execute_statement(
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/orm/context.py", line 306, in orm_execute_statement
    result = conn.execute(
             ^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1421, in execute
    return meth(
           ^^^^^
  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/sql/elements.py", line 526, in _execute_on_connection
    return connection._execute_clauseelement(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1643, in _execute_clauseelement
    ret = self._execute_context(
          ^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1848, in _execute_context
    return self._exec_single_context(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1988, in _exec_single_context
    self._handle_dbapi_exception(
  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 2365, in _handle_dbapi_exception
    raise sqlalchemy_exception.with_traceback(exc_info[2]) from e
  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1969, in _exec_single_context
    self.dialect.do_execute(
  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/engine/default.py", line 952, in do_execute
    cursor.execute(statement, parameters)
sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedColumn) column instance_ai_configs.opencode_workspace does not exist
LINE 1: ...chat_enabled AS instance_ai_configs_chat_enabled, instance_a...
                                                             ^

[SQL: SELECT instance_ai_configs.id AS instance_ai_configs_id, instance_ai_configs.instance_id AS instance_ai_configs_instance_id, instance_ai_configs.provider AS instance_ai_configs_provider, instance_ai_configs.api_key AS instance_ai_configs_api_key, instance_ai_configs.virtual_key AS instance_ai_configs_virtual_key, instance_ai_configs.use_proxy AS instance_ai_configs_use_proxy, instance_ai_configs.endpoint AS instance_ai_configs_endpoint, instance_ai_configs.model_allowlist AS instance_ai_configs_model_allowlist, instance_ai_configs.embedding_model AS instance_ai_configs_embedding_model, instance_ai_configs.budget_cents AS instance_ai_configs_budget_cents, instance_ai_configs.cutoff_behaviour AS instance_ai_configs_cutoff_behaviour, instance_ai_configs.degrade_model AS instance_ai_configs_degrade_model, instance_ai_configs.chat_enabled AS instance_ai_configs_chat_enabled, instance_ai_configs.opencode_workspace AS instance_ai_configs_opencode_workspace, instance_ai_configs.created_at AS instance_ai_configs_created_at, instance_ai_configs.updated_at AS instance_ai_configs_updated_at 
FROM instance_ai_configs ORDER BY instance_ai_configs.created_at ASC, instance_ai_configs.id ASC]
(Background on this error at: https://sqlalche.me/e/20/f405)


