# DEV-3082 Google Sheets dropdowns/merges/borders/tab style + batch_update_spreadsheet — Implementation Plan

**Execution:** inline — 7 tasks in 3 phases

**Goal:** Port upstream's dropdown, merge, border and tab-style features into the fork's `gsheets/` and add the
generic `batch_update_spreadsheet` tool, without touching auth or the server core.

**Architecture:** Pure request builders and validation in `gsheets/sheets_helpers.py`; tools in
`gsheets/sheets_tools.py` registered with `@server.tool` + `@handle_http_errors` + `@require_google_service`.
Feature code is the text of upstream tag `v2.4.0` (local tag `upstream-v2.4.0` in the main checkout
`/home/quintus-dev/quintus/mcp/google_workspace_mcp`; if missing:
`git fetch https://github.com/taylorwilsdon/google_workspace_mcp.git 'refs/tags/v2.4.0:refs/tags/upstream-v2.4.0'`).

**Tech Stack:** Python ≥3.10, FastMCP, google-api-python-client, pytest + pytest-asyncio, uv, ruff.

**Spec:** `docs/superpowers/specs/2026-11-10-DEV-3082-sheets-dropdown-batch-update-spec.md`

## Global Constraints
- Files allowed to change: `gsheets/`, `tests/gsheets/`, `core/tool_tiers.yaml`,
  `skills/managing-google-workspace/references/sheets.md`, and this repo's `docs/superpowers/`. Never `auth/`,
  `core/server.py`, `main.py`, `pyproject.toml`, `uv.lock`.
- Existing parameters, defaults and names of every tool stay as in `v1.27.1`.
- `MAX_BATCH_UPDATE_REQUESTS = 100`, `MAX_BATCH_UPDATE_REPLY_CHARS = 4000`.
- Logs name options and request kinds, never cell/dropdown values or request bodies.
- PR goes from `andreDevincenzi10/google_workspace_mcp` (this checkout's `origin`) to `celobusana/google_workspace_mcp` `main`.

## Review Focus
- `dropdown_values` arriving as a JSON string (`'["A","B"]'`) through the registered tool → coerced by `StringList`; test in Task 2.
- `requests` arriving as a JSON string through the registered tool → coerced by `DictList`; test in Task 5.
- A Google 400 from `batchUpdate` (bad `sheetId`) → surfaced as the `handle_http_errors` message, not a crash; test in Task 5.
- Whole-column range (`C:C`) with `merge_type="MERGE_ROWS"` → upstream guard treats open ends as unbounded and allows it; covered by the ported `test_format_merge_valid_spans`.
- `replies` containing only `{}` entries (typical for `setBasicFilter`/`sortRange`) → no `Replies:` line; test in Task 5.

---

## Phase 1: Environment

### Task 1: Install and baseline

**Files:** none

- [x] **Step 1:** `cd` into the worktree and run `timeout 300 uv sync --extra test --frozen` (the CI's command, `.github/workflows/pytest.yml`). Expected: exit 0.
- [x] **Step 2:** Baseline: `timeout 600 uv run pytest tests/gsheets -q`. Expected: all pass (record the count).
- [x] **Step 3:** `uv run ruff check gsheets tests/gsheets && uv run ruff format --check gsheets tests/gsheets` (ruff from the dev group; if absent, `uvx ruff@<version in .pre-commit-config.yaml or ruff.yml>`). Expected: clean.

## Phase 2: Port the upstream features

### Task 2: `format_sheet_range` — merges, borders, dropdowns, destructive hint, option logging

**Files:**
- Modify: `gsheets/sheets_helpers.py` (add `import math`, `MERGE_TYPES`, `BORDER_SIDES`, `BORDER_SIDE_ALIASES`, `BORDER_SIDE_NAMES`, `BORDER_STYLES`, `_build_update_borders_request`, `_build_dropdown_request`, `_normalize_merge_type`, `_build_merge_request` — copy from `git show upstream-v2.4.0:gsheets/sheets_helpers.py`, place after `_parse_hex_color`)
- Modify: `gsheets/sheets_tools.py` (`_format_sheet_range_impl` ~468-705, `format_sheet_range` ~707-792, import list from `gsheets.sheets_helpers`)
- Test: `tests/gsheets/test_format_sheet_range.py`

**Interfaces:**
- Produces: `_format_sheet_range_impl(service, spreadsheet_id, range_name, …, merge_cells=None, merge_type=None, borders=None, border_style=None, border_color=None, dropdown_values: Optional[List[str]] = None, dropdown_strict=None, clear_dropdown=None) -> dict` (keys `range_name`, `spreadsheet_id`, `summary`), exactly as upstream `v2.4.0`.

- [x] **Step 1: Port the tests.** Append to `tests/gsheets/test_format_sheet_range.py` every test of `upstream-v2.4.0:tests/gsheets/test_format_sheet_range.py` from `test_format_merge_cells_default_all` to the end of the file (merges, `test_format_sheet_range_is_destructive`, borders, dropdowns, wrapper forwarding), plus any helper/fixture those tests use that the fork file lacks. Do not change the existing fork tests.
- [x] **Step 2: Add the logging and coercion tests** in the same file:
  - `test_format_sheet_range_logs_option_names_not_values` — call the wrapper (`format_sheet_range.fn`, as the ported wrapper tests do) with `dropdown_values=["Segredo1","Segredo2"]`, `borders="outer"` under `caplog.at_level(logging.INFO)`; assert a record contains `Options: borders, dropdown_values` (names sorted in signature order: merge_cells, merge_type, borders, border_style, border_color, dropdown_values, dropdown_strict, clear_dropdown) and no record contains `Segredo1`.
  - `test_format_sheet_range_accepts_json_string_dropdown` — through the registered tool's argument validation (the way `tests/test_*` validate StringList elsewhere, or `pydantic.TypeAdapter(StringList).validate_python('["A","B"]') == ["A","B"]` if no tool-level harness exists) .
- [x] **Step 3:** Run `timeout 600 uv run pytest tests/gsheets/test_format_sheet_range.py -q`. Expected: the ported and new tests FAIL (missing parameters/helpers), the old ones pass.
- [x] **Step 4: Port the code.** Copy upstream `v2.4.0`'s helpers (list above) into `sheets_helpers.py`; replace `_format_sheet_range_impl` and `format_sheet_range` with their `v2.4.0` text (annotation `destructiveHint=True`); import the new helpers in `sheets_tools.py`. Then extend the wrapper's existing `logger.info` with `" Options: %s"` = the comma-joined names of the new options whose value is not `None` (omit the suffix when none).
- [x] **Step 5:** Run `timeout 600 uv run pytest tests/gsheets -q`. Expected: all pass.
- [x] **Step 6:** `git diff upstream-v2.4.0 -- gsheets/sheets_helpers.py | grep -c '^-.*_build_dropdown_request'` must be 0 (helper identical), then commit:
  `git add gsheets tests/gsheets && git commit -m "feat(sheets): dropdowns, merges and borders in format_sheet_range (DEV-3082)"`.

### Task 3: `manage_sheet_tab` — `style` action

**Files:**
- Modify: `gsheets/sheets_helpers.py` (add `_build_tab_style_properties` from `v2.4.0`)
- Modify: `gsheets/sheets_tools.py` (`manage_sheet_tab` ~2169-2290)
- Test: `tests/gsheets/test_manage_sheet_tab.py`

**Interfaces:**
- Produces: `_build_tab_style_properties(tab_color: Optional[str] = None, show_gridlines: Optional[bool] = None) -> tuple[dict, str, str]`; `manage_sheet_tab(..., tab_color: Optional[str] = None, show_gridlines: Optional[bool] = None)`.

- [x] **Step 1:** Port the `v2.4.0` tests of the `style` action from `upstream-v2.4.0:tests/gsheets/test_manage_sheet_tab.py` (the cases absent from the fork file: tab color, `"none"`, gridlines, non-GRID sheet, style args with another action, style with no args).
- [x] **Step 2:** Run `timeout 600 uv run pytest tests/gsheets/test_manage_sheet_tab.py -q`. Expected: new tests FAIL.
- [x] **Step 3:** Port `_build_tab_style_properties` and the `v2.4.0` text of `manage_sheet_tab` (docstring, `valid_actions` with `"style"`, the pre-check and the `style` branch). Keep the fork's decorators/annotations of `manage_sheet_tab` unchanged.
- [x] **Step 4:** Run `timeout 600 uv run pytest tests/gsheets -q`. Expected: all pass.
- [x] **Step 5:** Commit: `git commit -am "feat(sheets): style action in manage_sheet_tab (DEV-3082)"`.

## Phase 3: `batch_update_spreadsheet`, tiers, docs and validation

### Task 4: Request validation helper

**Files:**
- Modify: `gsheets/sheets_helpers.py`
- Test: `tests/gsheets/test_batch_update_spreadsheet.py` (create)

**Interfaces:**
- Produces: `MAX_BATCH_UPDATE_REQUESTS = 100`, `MAX_BATCH_UPDATE_REPLY_CHARS = 4000`, `_validate_batch_update_requests(requests: List[Any]) -> List[str]` (kinds in order; raises `UserInputError`).

- [x] **Step 1: Write the failing tests:**
  - `test_validate_returns_kinds_in_order` — `[{"setBasicFilter": {}}, {"sortRange": {}}]` → `["setBasicFilter", "sortRange"]`.
  - `test_validate_rejects_empty` — `[]` → `UserInputError` matching `at least one request`.
  - `test_validate_rejects_over_limit` — 101 items → `UserInputError` whose message contains `100`; 100 items pass.
  - `test_validate_rejects_non_dict_item` — `[{"sortRange": {}}, "x"]` → message contains `requests[1]`.
  - `test_validate_rejects_multi_key_item` — `[{"sortRange": {}, "addChart": {}}]` and `[{}]` → message contains `requests[0]` and `exactly one request type`.
- [x] **Step 2:** Run `uv run pytest tests/gsheets/test_batch_update_spreadsheet.py -q`. Expected: FAIL (import error).
- [x] **Step 3:** Implement the constants and `_validate_batch_update_requests` in `sheets_helpers.py` with the spec's messages.
- [x] **Step 4:** Run the file again. Expected: PASS.
- [x] **Step 5:** Commit: `git add gsheets tests/gsheets && git commit -m "feat(sheets): validate batchUpdate requests (DEV-3082)"`.

### Task 5: `batch_update_spreadsheet` tool

**Files:**
- Modify: `gsheets/sheets_tools.py` (new tool after `format_sheet_range`; import `DictList` from `core.utils`)
- Test: `tests/gsheets/test_batch_update_spreadsheet.py`

**Interfaces:**
- Consumes: `_validate_batch_update_requests`, `MAX_BATCH_UPDATE_REPLY_CHARS` (Task 4).
- Produces: `async def batch_update_spreadsheet(service, user_google_email: str, spreadsheet_id: str, requests: DictList) -> str`, decorators and annotations exactly as the spec's §2.

- [x] **Step 1: Write the failing tests** (mock `service` like `tests/gsheets/test_format_sheet_range.py`: `service.spreadsheets().batchUpdate(...).execute` returns the reply; call `batch_update_spreadsheet.fn` the way the ported wrapper tests call tools):
  - `test_batch_update_passes_requests_unchanged` — two requests (the spec's `setBasicFilter` and `sortRange` examples); assert `batchUpdate` called once with `spreadsheetId="sid"`, `body={"requests": <same list>}`; result contains `Applied 2 request(s)` and `setBasicFilter, sortRange`; reply `{"replies": [{}, {}]}` → no `Replies:` in result.
  - `test_batch_update_includes_non_empty_replies` — reply `{"replies": [{"addChart": {"chart": {"chartId": 7}}}]}` → result contains `Replies:` and `"chartId": 7`.
  - `test_batch_update_truncates_long_replies` — a reply whose JSON exceeds 4000 chars → the `Replies:` payload is 4000 chars followed by `… (truncated)`.
  - `test_batch_update_invalid_requests_make_no_call` — `[]` → `UserInputError` (or the error text `handle_http_errors` returns for it, matching existing tests' convention), `batchUpdate` not called.
  - `test_batch_update_http_error_is_reported` — `execute` raises `googleapiclient.errors.HttpError` 400 → behaves as other tools' HttpError tests in the repo (same assertion style).
  - `test_batch_update_logs_kinds_not_bodies` — with `caplog`, a record contains `Kinds: setBasicFilter, sortRange`, none contains `sortSpecs`.
  - `test_batch_update_is_destructive_write_tool` — registered tool annotations `destructiveHint is True`, `readOnlyHint is False` (same lookup as the ported `test_format_sheet_range_is_destructive`).
  - `test_batch_update_description_guides_the_agent` — the tool's description contains `setBasicFilter`, `sortRange`, `format_sheet_range`, `deleteSheet`, `get_spreadsheet_info`.
  - `test_batch_update_accepts_json_string_requests` — `pydantic.TypeAdapter(DictList).validate_python('[{"sortRange": {}}]') == [{"sortRange": {}}]`, or through the registered tool's argument validation if the repo has that harness.
- [x] **Step 2:** Run `uv run pytest tests/gsheets/test_batch_update_spreadsheet.py -q`. Expected: new tests FAIL.
- [x] **Step 3:** Implement the tool per spec §2 (docstring order and both literal examples from the spec; `logger.info("[batch_update_spreadsheet] Invoked. Email: '%s', Spreadsheet: %s, Requests: %d, Kinds: %s", …)`; one `asyncio.to_thread(service.spreadsheets().batchUpdate(spreadsheetId=..., body={"requests": requests}).execute)`).
- [x] **Step 4:** Run `timeout 600 uv run pytest tests/gsheets -q`. Expected: all pass.
- [x] **Step 5:** Commit: `git add gsheets tests/gsheets && git commit -m "feat(sheets): batch_update_spreadsheet passthrough tool (DEV-3082)"`.

### Task 6: Tier list, scope test and skill reference

**Files:**
- Modify: `core/tool_tiers.yaml` (`sheets.complete`: add `batch_update_spreadsheet`)
- Modify: `skills/managing-google-workspace/references/sheets.md` (new `format_sheet_range` parameters, `manage_sheet_tab` `style`, a `batch_update_spreadsheet` section with the two spec examples and the "prefer specific tools" rule)
- Test: `tests/test_scopes.py` or `tests/test_permissions.py` — whichever asserts per-tool scopes; extend it with `batch_update_spreadsheet` → `sheets_write` in the same style.

- [x] **Step 1:** Add the scope assertion; run `uv run pytest tests/test_scopes.py tests/test_permissions.py tests/test_main_permissions_tier.py -q`. Expected: the new assertion passes or fails only on the tier list (fix by Step 2).
- [x] **Step 2:** Edit `core/tool_tiers.yaml` and the skill reference.
- [x] **Step 3:** Run the three test files again. Expected: PASS.
- [x] **Step 4:** Commit: `git add core/tool_tiers.yaml skills tests && git commit -m "docs(sheets): tier and skill reference for the new Sheets tools (DEV-3082)"`.

### Task 7: Full check, local boot, push

**Files:** `docs/superpowers/reports/2026-11-10-DEV-3082-sheets-dropdown-batch-update-validation.md` (create)

- [x] **Step 1:** `git diff --name-only origin/main...HEAD` lists only the allowed paths (Global Constraints).
- [x] **Step 2:** The repo has `.github/workflows/pytest.yml`, so the whole suite runs in CI; locally run only `timeout 600 uv run pytest tests/gsheets tests/test_scopes.py tests/test_permissions.py tests/test_main_permissions_tier.py -q` and ruff check + format check on the changed files. Expected: clean.
- [x] **Step 3: Local boot** (no credentials needed for `tools/list`): `MCP_ENABLE_OAUTH21=true EXTERNAL_OAUTH21_PROVIDER=true MCP_TRUST_BEARER_TOKEN=true PORT=<free port> timeout 120 uv run main.py --transport streamable-http` in the background of one shell call with a script under `/home/quintus-dev/quintus/.runs/DEV-3082/` that waits for `/health` 200, sends MCP `initialize` + `notifications/initialized` + `tools/list` to `/mcp` (headers `Accept: application/json, text/event-stream`, `Mcp-Session-Id` from the initialize response), saves the JSON, and kills the server. Expected: `batch_update_spreadsheet` present with `requests` (array of objects) and `spreadsheet_id`; `format_sheet_range` schema has `dropdown_values`, `merge_type`, `borders`; `manage_sheet_tab` has `tab_color`, `show_gridlines`; Drive/Calendar tools still listed (e.g. `search_drive_files`, `list_calendars`). If `tools/list` needs a bearer under OAuth 2.1, send any non-empty `Authorization: Bearer x` (listing does not call Google) and record what was needed.
- [x] **Step 4:** Write the validation report (English): commands, counts, the `tools/list` excerpts, and §8 post-merge items: (a) agent in dev creates a sheet with a dropdown column and a header filter; (b) `mcp-google` dev logs show `Options: dropdown_values` and `Kinds: setBasicFilter`; (c) Drive and Calendar smoke through the Quintus connectors. Commit it.
- [x] **Step 5:** Push to `origin` (the bot fork) per `references/git-https.md`; the PR to `celobusana/google_workspace_mcp` `main` already exists (draft) — CI (`pytest.yml`, `ruff.yml`) runs there.

## Required resources
- uv — kind `tool`, probe `uv --version`, phases 1–3.
