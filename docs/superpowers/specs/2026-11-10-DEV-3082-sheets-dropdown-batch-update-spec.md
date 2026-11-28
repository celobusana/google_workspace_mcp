# DEV-3082 — Google Sheets: dropdowns, merges, borders, tab style and `batch_update_spreadsheet`

Ticket: DEV-3082 (support SUP-236). Scope fixed by the ticket's scope comment (2026-11-10): no upgrade of the fork
to upstream 2.4.0; two changes only, restricted to `gsheets/` (plus the tool tier list, the bundled skill reference
and tests). Upstream: `taylorwilsdon/google_workspace_mcp`. The fork's `gsheets/` is byte-identical to upstream
`v1.27.1`.

## Changes

### 1. Port from upstream (text of tag `v2.4.0`)
- `gsheets/sheets_helpers.py`: `import math`; `MERGE_TYPES = ("MERGE_ALL", "MERGE_COLUMNS", "MERGE_ROWS")`;
  `_build_tab_style_properties`; `BORDER_SIDES`, `BORDER_SIDE_ALIASES`, `BORDER_SIDE_NAMES`, `BORDER_STYLES`;
  `_build_update_borders_request`; `_build_dropdown_request`; `_normalize_merge_type`; `_build_merge_request`.
- `gsheets/sheets_tools.py`:
  - `_format_sheet_range_impl` and `format_sheet_range` gain `merge_cells: Optional[bool]`,
    `merge_type: Optional[str]`, `borders: Optional[str]`, `border_style: Optional[str]`,
    `border_color: Optional[str]`, `dropdown_values: Optional[StringList]` (the impl takes `Optional[List[str]]`),
    `dropdown_strict: Optional[bool]`, `clear_dropdown: Optional[bool]`; one `batchUpdate` carries `repeatCell`,
    `mergeCells`/`unmergeCells`, `updateBorders` and `setDataValidation` (`ONE_OF_LIST`, `showCustomUi: true`).
  - `format_sheet_range` annotation `destructiveHint=True` (upstream `d36297fd`).
  - `manage_sheet_tab` gains action `style` with `tab_color: Optional[str]` (hex or `"none"`) and
    `show_gridlines: Optional[bool]`; `tab_color`/`show_gridlines` with any other action raise `UserInputError`;
    `show_gridlines` on a non-`GRID` sheet raises `UserInputError`.
  - Signature, defaults and behavior of every existing parameter stay as in `v1.27.1`.
  - Logging: the `format_sheet_range` wrapper's existing `logger.info` line also names the new options passed,
    as `Options: <names>` (e.g. `Options: dropdown_values, borders`), never their values (cell values may be
    customer data). This is what makes the ticket's dev check ("logs show `dropdown_values`") observable.

### 2. New tool `batch_update_spreadsheet`
- Signature: `batch_update_spreadsheet(service, user_google_email: str, spreadsheet_id: str, requests: DictList) -> str`
  (`DictList` from `core/utils.py`, so a JSON-encoded string is accepted too).
- Decorators: `@server.tool(title="Batch Update Spreadsheet", annotations=ToolAnnotations(readOnlyHint=False,
  destructiveHint=True, idempotentHint=False, openWorldHint=True))`,
  `@handle_http_errors("batch_update_spreadsheet", service_type="sheets")`,
  `@require_google_service("sheets", "sheets_write")`.
- Validation (pure helper `_validate_batch_update_requests(requests) -> list[str]` in `sheets_helpers.py`, before
  any API call; each failure raises `UserInputError`):
  - empty list → `"requests must contain at least one request."`;
  - more than `MAX_BATCH_UPDATE_REQUESTS = 100` items → message naming the limit;
  - an item that is not a dict, or a dict with zero or more than one key → message naming its index
    ("requests[2] must be an object with exactly one request type, e.g. {\"sortRange\": {...}}").
  - returns the request kinds (each item's single key) in order.
- One call `spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests})`, requests passed
  unchanged.
- Logging: one `logger.info` line `"[batch_update_spreadsheet] Invoked. Email: '%s', Spreadsheet: %s, Requests: %d, Kinds: %s"` with the comma-joined kinds (never the request bodies).
- Response text: `"Applied <N> request(s) to spreadsheet <id> for <email>: <kind1>, <kind2>, …."`; when the API
  reply holds any non-empty object in `replies`, append `"\nReplies: <json.dumps(replies)>"`, cut to
  `MAX_BATCH_UPDATE_REPLY_CHARS = 4000` characters followed by `" … (truncated)"` when longer.
- Docstring (the description the agent sees) says, in this order: it is a generic passthrough of Google Sheets
  `spreadsheets.batchUpdate`; prefer `format_sheet_range` (formats, merges, borders, dropdowns),
  `manage_conditional_formatting`, `manage_sheet_tab`, `resize_sheet_dimensions` and `move_sheet_rows` when they
  cover the change; use it for filters (`setBasicFilter`, `clearBasicFilter`, `addFilterView`), sorting
  (`sortRange`), checkboxes (`setDataValidation` with condition `BOOLEAN`), charts (`addChart`), protection
  (`addProtectedRange`), pivot tables (`updateCells` with `pivotTable`) and find/replace (`findReplace`);
  `sheetId` is the numeric tab id from `get_spreadsheet_info`, not the title; ranges are zero-based `GridRange`
  objects with exclusive end indexes; `deleteSheet`, `deleteRange` and `deleteDimension` delete data. It holds two
  literal examples:
  - `[{"setBasicFilter": {"filter": {"range": {"sheetId": 0, "startRowIndex": 0, "startColumnIndex": 0, "endColumnIndex": 5}}}}]`
  - `[{"sortRange": {"range": {"sheetId": 0, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 5}, "sortSpecs": [{"dimensionIndex": 2, "sortOrder": "DESCENDING"}]}}]`

### 3. Tier list and skill reference (outside `gsheets/`, justified)
- `core/tool_tiers.yaml`: `batch_update_spreadsheet` added under `sheets.complete` — every registered tool must be
  in a tier, or `--tool-tier complete` would hide it (`tests/test_main_permissions_tier.py`).
- `skills/managing-google-workspace/references/sheets.md`: the new `format_sheet_range` parameters, the `style`
  action of `manage_sheet_tab`, and a `batch_update_spreadsheet` section with the two examples above.

## Acceptance criteria
- [ ] `format_sheet_range(..., range_name="Sheet1!C2:C50", dropdown_values=["Aberto","Feito"])` sends exactly one
      `batchUpdate` whose only request is `setDataValidation` with `range` = the parsed GridRange and
      `rule = {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": "Aberto"}, {"userEnteredValue": "Feito"}]}, "strict": true, "showCustomUi": true}`.
- [ ] `dropdown_strict=False` sends `"strict": false`; `clear_dropdown=True` sends `{"setDataValidation": {"range": <GridRange>}}`
      with no `rule`; `dropdown_values` + `clear_dropdown` together, `dropdown_strict` without `dropdown_values`, and
      a `dropdown_values` with only blank strings each raise `UserInputError` before any API call.
- [ ] `merge_cells=True` sends `mergeCells` `MERGE_ALL`; `merge_type="merge_columns"` sends `MERGE_COLUMNS`;
      `merge_cells=False` sends `unmergeCells`; `merge_type` with `merge_cells=False`, an unknown `merge_type`, and a
      merge whose group is one cell (`A1`, `A1:A5` with `MERGE_COLUMNS`) raise `UserInputError`.
- [ ] `borders="outer"` sends `updateBorders` with `top/bottom/left/right` `SOLID` black; `"all"` adds the inner
      sides once each; `"none"` sets every side `NONE`; `inner_horizontal`, `inner-horizontal` and `innerHorizontal`
      are accepted; `border_style`/`border_color` without `borders`, `"none"` combined with a side, and an unknown
      side or style raise `UserInputError`.
- [ ] Borders, dropdown, merge and cell formats in one call produce one `batchUpdate` with all requests in the order
      `repeatCell`, merge, `updateBorders`, `setDataValidation`.
- [ ] The `format_sheet_range` tool wrapper forwards every new parameter to `_format_sheet_range_impl`, and its
      registered annotations have `destructiveHint=True`.
- [ ] `manage_sheet_tab(action="style", tab_color="#FF0000", show_gridlines=False)` sends `updateSheetProperties`
      with `tabColorStyle.rgbColor` and `gridProperties.hideGridlines=true` and fields
      `tabColorStyle,gridProperties.hideGridlines`; `tab_color="none"` sends an empty `tabColorStyle`;
      `style` with neither argument, `tab_color` with `action="rename"`, and `show_gridlines` on an `OBJECT` sheet
      raise `UserInputError`.
- [ ] `batch_update_spreadsheet` with `[{"setBasicFilter": …}, {"sortRange": …}]` calls `batchUpdate` once with
      `body == {"requests": <the same list>}` and returns text containing `Applied 2 request(s)` and
      `setBasicFilter, sortRange`.
- [ ] `batch_update_spreadsheet` accepts the same list as a JSON string (pydantic `DictList` coercion through the
      registered tool).
- [ ] Called on the tool function (`batch_update_spreadsheet.fn`) or on `_validate_batch_update_requests`: empty
      list, 101 items, a non-dict item and a dict with two keys each raise `UserInputError` and make no API call.
      Through the registered tool (pydantic), a non-dict item is refused by schema validation before the function
      runs — also no API call.
- [ ] A reply with `addChart` returns `Replies:` with its JSON; a reply longer than 4000 characters is cut and ends
      with `(truncated)`; all-empty replies add no `Replies:` line.
- [ ] `batch_update_spreadsheet` is registered with `destructiveHint=True`, `readOnlyHint=False` and requires the
      `sheets_write` scope (the registered tool's scope list, as `tests/test_scopes.py` checks other tools).
- [ ] `batch_update_spreadsheet` logs one INFO line containing `Kinds: setBasicFilter, sortRange` for the call above,
      and no request body; `format_sheet_range` with `dropdown_values` logs `Options: dropdown_values` and none of
      the dropdown values.
- [ ] Its description contains `setBasicFilter`, `sortRange`, `format_sheet_range` and `deleteSheet`.
- [ ] `core/tool_tiers.yaml` lists it under `sheets.complete`; `tests/test_main_permissions_tier.py` and
      `tests/test_permissions.py` pass.
- [ ] Tests: the upstream `v2.4.0` cases for merges, borders, dropdowns and the destructive annotation
      (`tests/gsheets/test_format_sheet_range.py` from `test_format_merge_cells_default_all` on) and for the `style`
      action (`tests/gsheets/test_manage_sheet_tab.py`) are ported and pass; new
      `tests/gsheets/test_batch_update_spreadsheet.py` covers the criteria above; every existing test in `tests/`
      passes; `ruff check` and `ruff format --check` clean.
- [ ] Must not change: any file outside `gsheets/`, `tests/gsheets/`, `core/tool_tiers.yaml` and
      `skills/managing-google-workspace/references/sheets.md` (in particular `auth/`, `core/server.py`, `main.py`,
      `pyproject.toml`, `uv.lock`); names and existing parameters of every other tool.
- [ ] A local boot (`uv run main.py --transport streamable-http`) lists `batch_update_spreadsheet` and the new
      `format_sheet_range` / `manage_sheet_tab` parameters in `tools/list`.

## Architecture
Tools live in the per-service package `gsheets/` (`sheets_tools.py` registers tools on `core.server.server` with
`@server.tool`, `@handle_http_errors`, `@require_google_service`; pure request builders live in
`sheets_helpers.py`). The port keeps that split: builders and validation in `sheets_helpers.py`, tools in
`sheets_tools.py`. Input errors are `core.utils.UserInputError`; list-typed MCP arguments use `StringList` /
`DictList` so JSON-string clients work. No change to the Quintus-specific auth passthrough in `auth/` and
`core/server.py`.

## UI impact
None (server side). Indirect effect: agents using the Google Sheets connector see the new parameters and, once the
catalog lists it (llm-chat-service migration), the new tool with a confirmation card.

## Decisions to confirm
- Limit of 100 requests per `batch_update_spreadsheet` call — alternative: no limit (Google accepts far more).
- Replies cut at 4000 characters in the tool response — alternative: return replies in full.
- Assumption: the bundled skill reference (`skills/managing-google-workspace/references/sheets.md`) is updated with
  the new parameters and tool — the repo ships it next to the tools and documents every Sheets tool there;
  alternative: leave it stale.
- `format_sheet_range` marked `destructiveHint=True` as upstream — alternative: keep `False` (the catalog
  permission, not the hint, decides the confirmation card).

## Inherited security debt
- `batch_update_spreadsheet` executes any Sheets `Request` the agent builds, including deletions, within the
  user's own OAuth grant; mitigated by `destructiveHint` and the catalog's confirmation (`accept_session`). Kept by
  design (ticket asks for the generic passthrough).

## Spec review
Fresh-subagent review on 2026-11-10: 10 findings (0 high, 6 med, 4 low), all verified against the code and applied, none rejected. Applied: (1) INFO logs of batch request kinds and of format_sheet_range option names (never values) so the ticket's log check is observable; (2) mcp-servers pre-merge proof = uv boot of the pinned fork sha with the Dockerfile ENV (no docker on host, no PR build), real image build moved to §8; (3) interim fork-head pin declared non-mergeable, merge gate re-pins to the celobusana main commit; (4) llm-chat migration number = next free on main and open PRs (0053 taken by PR #1136) + uniqueness criterion; (5) format_sheet_range catalog permission kept accept_always, listed in Decisions to confirm; (6) legacy ConnectorUser tools snapshot resolves the new tool as off — §8 check incl. the customer's connection; (7) 2 h llm-common tools cache — release order and §8 timing; (8) non-dict request item: helper-level UserInputError vs schema error through the tool; (9) tool_tiers.yaml justified, skill reference moved to Decisions to confirm; (10) migration logs matched/modified counts + prod §8 check.
