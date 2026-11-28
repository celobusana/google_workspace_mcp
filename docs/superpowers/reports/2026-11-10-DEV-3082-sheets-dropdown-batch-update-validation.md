# DEV-3082 — Validation report (celobusana/google_workspace_mcp)

## 1. Summary
- Level: **L2** — a package-like MCP server whose tool surface changes (new tool, new parameters on two tools); no
  auth, persistence or cross-service contract is touched (`auth/`, `core/server.py` unchanged).
- Scope: `gsheets/` only (+ `core/tool_tiers.yaml`, skill reference, tests, docs). Upstream `v2.4.0` text for dropdowns,
  merges, borders and tab style; new `batch_update_spreadsheet` passthrough.
- Reviews: one stage-5 review (general + simplification), 6 findings. Applied: plan Task 7 ticked in the branch
  (high, `partial-delivery`); JSON-string tests now check the registered tool's real signature types and schema; the
  scope test now reads the tool's `_required_google_scopes` like `tests/test_scopes.py`; the constants-only test
  deleted; test imports moved to the top. Rejected: the finding asking for `- [ ]` post-merge items in §8 — at L2 §8
  is "n/a" by the report format, and `- [ ]` lines would make the deploy look for a workflow that does not exist;
  the live checks are listed in the plan and the PR body instead.
- Scenarios: 5/5 passed (unit suite, lint, local boot with `tools/list`, mutation check, file-scope check).
- Verdict: **ready with caveats** — no real Google call was made (no Google credentials on the host); the live
  scenario is a post-merge criterion (§8).

## 2. Affected endpoints
- MCP tool `format_sheet_range` (direct): new optional parameters `merge_cells`, `merge_type`, `borders`,
  `border_style`, `border_color`, `dropdown_values`, `dropdown_strict`, `clear_dropdown`; `destructiveHint=True`.
- MCP tool `manage_sheet_tab` (direct): `style` action, new `tab_color`, `show_gridlines`.
- MCP tool `batch_update_spreadsheet` (new, direct).
- Drive, Calendar, Docs, Tasks, Gmail tools (indirect, same server image): unchanged files; smoke by `tools/list`.

## 3. Evidence per scenario
1. **Unit suite** — `uv run pytest tests/gsheets tests/test_scopes.py tests/test_permissions.py tests/test_main_permissions_tier.py -q`:
   all pass (baseline of `tests/gsheets` was 100; now 174 there). PASS.
2. **Lint** — `uv run ruff check .` clean; `uv run ruff format --check gsheets tests` clean. PASS.
3. **Local boot, `tools/list`** — server started with `MCP_ENABLE_OAUTH21=true EXTERNAL_OAUTH21_PROVIDER=true
   MCP_TRUST_BEARER_TOKEN=true` and dummy OAuth client values; MCP `initialize` + `tools/list` with
   `Authorization: Bearer x` (listing does not call Google). 124 tools listed:
   - `batch_update_spreadsheet`: properties `spreadsheet_id`, `requests` (array of objects); annotations
     `readOnlyHint=false`, `destructiveHint=true`, `idempotentHint=false`, `openWorldHint=true`.
   - `format_sheet_range`: has `dropdown_values`, `merge_type`, `borders`.
   - `manage_sheet_tab`: has `tab_color`, `show_gridlines`.
   - `search_drive_files` and `list_calendars` still listed. PASS. A bearer header was needed; any non-empty value worked.
4. **Mutation check** — `scripts/mutation-check.sh` over the three test files with the production files reverted to
   `origin/main`: `FAILS_WITHOUT_CHANGE` (the new tests fail without the change; for the new test module the failure is the
   import error of the new helpers). PASS.
5. **Scope** — `git diff --name-only origin/main...HEAD` lists only `gsheets/`, `tests/gsheets/`, `core/tool_tiers.yaml`,
   `skills/managing-google-workspace/references/sheets.md` and `docs/superpowers/`. `auth/`, `core/server.py`,
   `main.py`, `pyproject.toml`, `uv.lock` untouched. PASS.

Logging checked by tests: `format_sheet_range` logs `Options: <names>` (never dropdown values);
`batch_update_spreadsheet` logs `Kinds: <types>` (never request bodies).

## 4. Bugs fixed
- A ported upstream test read `annotations.destructive_hint`; the pinned `mcp` exposes `destructiveHint`. The test now
  accepts either spelling (test-only change, `tests/gsheets/test_format_sheet_range.py`).

## 5. Problems needing decision
None.

## 6. Pending
- No call against the real Google Sheets API (no Google credentials on this host): dropdown, filter and sort effects
  are proven at request-building level (unit tests) and by the tool schema, not by a live spreadsheet.
- Python 3.11 `FutureWarning` from `google.api_core` (pre-existing, unrelated).

## 7. Conclusion
The spec is met at the code level: the upstream features are ported without touching auth or the server core, the new
tool validates and passes requests through unchanged, and the other Google tools are unaffected in the tool listing.
The live behaviour is left to the post-merge criteria.

## 8. Post-merge criteria
n/a — L2. Manual checks after the release (listed in the plan, not a CI workflow):
the agent creates a sheet with a dropdown column and a header filter in dev; the `mcp-google` dev logs show
`Options: dropdown_values` and `Kinds: setBasicFilter`; Drive and Calendar smoke through the Quintus connectors.
