# Google Sheets Tools Reference

MCP tools for reading, writing, formatting, and managing Google Sheets. All tools require `user_google_email` (string, required). The `spreadsheet_id` parameter accepts a spreadsheet ID or a full Google Sheets URL.

## Contents
- Search & Info: list_spreadsheets, get_spreadsheet_info
- Read & Write: read_sheet_values, modify_sheet_values
- Create: create_spreadsheet, create_sheet, move_sheet_rows
- Formatting: format_sheet_range, manage_conditional_formatting
- Tabs & advanced: manage_sheet_tab, batch_update_spreadsheet
- Comments: list_spreadsheet_comments, manage_spreadsheet_comment
- Tips

---

## Search & Info

### list_spreadsheets
List spreadsheets the user has access to (via Drive).

| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|-------|
| user_google_email | string | yes | | |
| max_results | integer | no | 25 | |

### get_spreadsheet_info
Get spreadsheet metadata: title, locale, and list of sheets.

| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|-------|
| user_google_email | string | yes | | |
| spreadsheet_id | string | yes | | |

---

## Read & Write

### read_sheet_values
Read values from a range in a spreadsheet.

Open-ended or oversized A1 ranges are clamped to at most **1000 rows** before
the Sheets API request (same budget as the default `A1:Z1000`). When clamped,
the response includes a note with the rewritten range so you can request the
next window (e.g. `A1001:A2000`). Quoted whole-sheet references such as
`'My Sheet'` are clamped as well. Bare identifiers are left unchanged because
Google Sheets can resolve them as named ranges.

| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|-------|
| user_google_email | string | yes | | |
| spreadsheet_id | string | yes | | |
| range_name | string | no | A1:Z1000 | A1 notation, e.g. `Sheet1!A1:D10`. Caps at 1000 rows |
| include_hyperlinks | boolean | no | false | Fetch hyperlink metadata (slower) |
| include_notes | boolean | no | false | Fetch cell notes (slower) |

### modify_sheet_values
Write, update, or clear values in a range.

| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|-------|
| user_google_email | string | yes | | |
| spreadsheet_id | string | yes | | |
| range_name | string | yes | | A1 notation |
| values | array or string | conditional | | 2D array of values. Required unless `clear_values=true`. Accepts a JSON string or a list |
| value_input_option | string | no | USER_ENTERED | `RAW` or `USER_ENTERED` |
| clear_values | boolean | no | false | Clear the range instead of writing |

---

## Create

### create_spreadsheet
Create a new Google Spreadsheet.

| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|-------|
| user_google_email | string | yes | | |
| title | string | yes | | Spreadsheet title |
| sheet_names | array of strings | no | | Sheet names to create. Defaults to one sheet with the default name |

### create_sheet
Add a new sheet (tab) to an existing spreadsheet.

| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|-------|
| user_google_email | string | yes | | |
| spreadsheet_id | string | yes | | |
| sheet_name | string | yes | | |

### move_sheet_rows
Move rows from one sheet to another within the same spreadsheet. Preserves formulas, data types, and formatting.

| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|-------|
| user_google_email | string | yes | | |
| spreadsheet_id | string | yes | | |
| source_sheet | string | yes | | Name of the sheet to move rows from |
| start_row | integer | yes | | First row to move (1-based, inclusive) |
| end_row | integer | yes | | Last row to move (1-based, inclusive) |
| destination_sheet | string | yes | | Name of the sheet to move rows to |

---

## Formatting

### format_sheet_range
Apply visual formatting to a range: colors, number formats, text wrapping, alignment, text styling, merged cells, borders, and dropdown lists.

| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|-------|
| user_google_email | string | yes | | |
| spreadsheet_id | string | yes | | |
| range_name | string | yes | | A1 notation (with optional sheet name) |
| background_color | string | no | | Hex `#RRGGBB` |
| text_color | string | no | | Hex `#RRGGBB` |
| number_format_type | string | no | | `NUMBER`, `CURRENCY`, `DATE`, `PERCENT`, etc. |
| number_format_pattern | string | no | | Custom pattern for the number format |
| wrap_strategy | string | no | | `WRAP`, `CLIP`, or `OVERFLOW_CELL` |
| horizontal_alignment | string | no | | `LEFT`, `CENTER`, or `RIGHT` |
| vertical_alignment | string | no | | `TOP`, `MIDDLE`, or `BOTTOM` |
| bold | boolean | no | | |
| italic | boolean | no | | |
| font_size | integer | no | | Size in points |
| merge_cells | boolean | no | | `true` merges the range, `false` unmerges it. Merging keeps only the top-left value of each merged group |
| merge_type | string | no | `MERGE_ALL` | `MERGE_ALL`, `MERGE_COLUMNS`, or `MERGE_ROWS`. Implies `merge_cells=true` |
| borders | string | no | | Comma-separated sides: `all`, `outer`, `inner`, `top`, `bottom`, `left`, `right`, `inner_horizontal`, `inner_vertical`. `none` removes every border |
| border_style | string | no | `SOLID` | `SOLID`, `SOLID_MEDIUM`, `SOLID_THICK`, `DASHED`, `DOTTED`, or `DOUBLE`. Requires `borders` |
| border_color | string | no | black | Hex `#RRGGBB`. Requires `borders` |
| dropdown_values | array or string | no | | Turns every cell in the range into a dropdown with these values, e.g. `["open", "done"]` |
| dropdown_strict | boolean | no | `true` | With `dropdown_values`: `true` rejects other input, `false` only warns |
| clear_dropdown | boolean | no | | Removes all data validation from the range (dropdowns, but also checkboxes and other rules) |

### manage_conditional_formatting
Add, update, or delete conditional formatting rules.

| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|-------|
| user_google_email | string | yes | | |
| spreadsheet_id | string | yes | | |
| action | string | yes | | `add`, `update`, or `delete` |
| range_name | string | for add | | A1 notation. Optional for update (preserves existing ranges if omitted) |
| condition_type | string | for add | | e.g. `NUMBER_GREATER`, `TEXT_CONTAINS`, `DATE_BEFORE`, `CUSTOM_FORMULA` |
| condition_values | array or string | conditional | | Values for the condition. Depends on `condition_type` |
| background_color | string | no | | Hex `#RRGGBB` applied when condition matches |
| text_color | string | no | | Hex `#RRGGBB` applied when condition matches |
| rule_index | integer | for update/delete | | 0-based index of the rule |
| gradient_points | array or string | no | | List of gradient point dicts for color-scale rules. Overrides boolean rule parameters |
| sheet_name | string | no | first sheet | Sheet name for locating the rule (used by update/delete) |

---

## Tabs & advanced requests

### manage_sheet_tab
Rename, delete, hide, unhide, reorder, or style an existing sheet tab.

| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|-------|
| user_google_email | string | yes | | |
| spreadsheet_id | string | yes | | |
| sheet_name | string | yes | | Name of the tab |
| action | string | yes | | `rename`, `delete`, `hide`, `unhide`, `reorder`, or `style` |
| new_name | string | for rename | | |
| new_index | integer | for reorder | | Zero-based target position |
| tab_color | string | for style | | Hex `#RRGGBB`, or `none` to remove the color |
| show_gridlines | boolean | for style | | `true` shows, `false` hides the gridlines |

### batch_update_spreadsheet
Generic passthrough of the Sheets `spreadsheets.batchUpdate` API: 1 to 100 requests, applied in order in one atomic call. **Prefer the specific tools** (`format_sheet_range`, `manage_conditional_formatting`, `manage_sheet_tab`, `resize_sheet_dimensions`, `move_sheet_rows`) whenever they cover the change; use this one for filters (`setBasicFilter`, `clearBasicFilter`, `addFilterView`), sorting (`sortRange`), checkboxes (`setDataValidation` with condition `BOOLEAN`), charts (`addChart`), protection (`addProtectedRange`), pivot tables (`updateCells` with `pivotTable`) and find/replace (`findReplace`). It can also delete data (`deleteSheet`, `deleteRange`, `deleteDimension`), so the user confirms it.

| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|-------|
| user_google_email | string | yes | | |
| spreadsheet_id | string | yes | | |
| requests | array or string | yes | | Each item has exactly one request type as its key |

`sheetId` is the numeric tab id from `get_spreadsheet_info`, not the title. Ranges are zero-based `GridRange` objects with exclusive end indexes.

Filter on the header of the first 5 columns:
```json
[{"setBasicFilter": {"filter": {"range": {"sheetId": 0, "startRowIndex": 0, "startColumnIndex": 0, "endColumnIndex": 5}}}}]
```

Sort the rows below the header by the third column, descending:
```json
[{"sortRange": {"range": {"sheetId": 0, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 5}, "sortSpecs": [{"dimensionIndex": 2, "sortOrder": "DESCENDING"}]}}]
```

---

## Comments

### list_spreadsheet_comments
List all comments on a spreadsheet.

| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|-------|
| user_google_email | string | yes | | |
| spreadsheet_id | string | yes | | |

### manage_spreadsheet_comment
Create, reply to, or resolve a comment.

| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|-------|
| user_google_email | string | yes | | |
| spreadsheet_id | string | yes | | |
| action | string | yes | | `create`, `reply`, or `resolve` |
| comment_content | string | for create/reply | | Comment text |
| comment_id | string | for reply/resolve | | Target comment ID |

---

## Tips

**Range notation**: Use A1 notation throughout. Include the sheet name for multi-sheet spreadsheets (e.g. `Sheet2!A1:C10`). If no sheet name is given, the first sheet is used.

**USER_ENTERED vs RAW**: `USER_ENTERED` (default) parses values as if typed into the Sheets UI -- formulas are evaluated, dates parsed, numbers formatted. `RAW` stores exact strings without interpretation.

**Conditional formatting condition types**: Common values include `NUMBER_GREATER`, `NUMBER_LESS`, `NUMBER_BETWEEN`, `TEXT_CONTAINS`, `TEXT_NOT_CONTAINS`, `DATE_BEFORE`, `DATE_AFTER`, `CUSTOM_FORMULA`, `BLANK`, `NOT_BLANK`.

**Gradient rules**: Provide `gradient_points` as a list of dicts, each with `type` (`MIN`, `MAX`, `NUMBER`, `PERCENT`, `PERCENTILE`), `value` (string, optional for `MIN`/`MAX`), and `color` (hex `#RRGGBB`). When gradient points are set, boolean formatting parameters are ignored.
