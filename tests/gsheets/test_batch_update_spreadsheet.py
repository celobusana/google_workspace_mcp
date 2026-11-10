"""
Unit tests for the generic Google Sheets batch_update_spreadsheet tool and its
request validation helper.
"""

import json
import logging
import typing
import os
import sys
from unittest.mock import Mock


import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from googleapiclient.errors import HttpError
from pydantic import TypeAdapter

from auth.service_decorator import has_required_scopes
from auth.scopes import SHEETS_WRITE_SCOPE
from core.server import server
from core.tool_tier_loader import resolve_tools_from_tier
from core.utils import DictList, UserInputError, handle_http_errors
from gsheets import sheets_tools
from gsheets.sheets_helpers import (
    MAX_BATCH_UPDATE_REPLY_CHARS,
    _validate_batch_update_requests,
)


def _unwrap(fn):
    """Unwrap decorated function to access the underlying coroutine."""
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


def test_validate_returns_kinds_in_order():
    kinds = _validate_batch_update_requests([{"setBasicFilter": {}}, {"sortRange": {}}])
    assert kinds == ["setBasicFilter", "sortRange"]


def test_validate_rejects_empty():
    with pytest.raises(UserInputError, match="at least one request"):
        _validate_batch_update_requests([])


def test_validate_rejects_over_limit():
    with pytest.raises(UserInputError, match="100"):
        _validate_batch_update_requests([{"sortRange": {}}] * 101)
    assert len(_validate_batch_update_requests([{"sortRange": {}}] * 100)) == 100


def test_validate_rejects_non_dict_item():
    with pytest.raises(UserInputError, match=r"requests\[1\]"):
        _validate_batch_update_requests([{"sortRange": {}}, "x"])


@pytest.mark.parametrize(
    "requests",
    [[{"sortRange": {}, "addChart": {}}], [{}]],
)
def test_validate_rejects_multi_key_item(requests):
    with pytest.raises(UserInputError) as exc_info:
        _validate_batch_update_requests(requests)
    message = str(exc_info.value)
    assert "requests[0]" in message
    assert "exactly one request type" in message


FILTER_REQUEST = {
    "setBasicFilter": {
        "filter": {
            "range": {
                "sheetId": 0,
                "startRowIndex": 0,
                "startColumnIndex": 0,
                "endColumnIndex": 5,
            }
        }
    }
}
SORT_REQUEST = {
    "sortRange": {
        "range": {
            "sheetId": 0,
            "startRowIndex": 1,
            "startColumnIndex": 0,
            "endColumnIndex": 5,
        },
        "sortSpecs": [{"dimensionIndex": 2, "sortOrder": "DESCENDING"}],
    }
}


def _service(reply):
    service = Mock()
    service.spreadsheets.return_value.batchUpdate.return_value.execute = Mock(
        return_value=reply
    )
    return service


async def _call(service, requests):
    return await _unwrap(sheets_tools.batch_update_spreadsheet)(
        service=service,
        user_google_email="user@example.com",
        spreadsheet_id="sid",
        requests=requests,
    )


@pytest.mark.asyncio
async def test_batch_update_passes_requests_unchanged():
    service = _service({"replies": [{}, {}]})
    requests = [FILTER_REQUEST, SORT_REQUEST]

    result = await _call(service, requests)

    batch_update = service.spreadsheets.return_value.batchUpdate
    batch_update.assert_called_once_with(
        spreadsheetId="sid", body={"requests": requests}
    )
    assert "Applied 2 request(s)" in result
    assert "setBasicFilter, sortRange" in result
    assert "Replies:" not in result


@pytest.mark.asyncio
async def test_batch_update_includes_non_empty_replies():
    service = _service({"replies": [{"addChart": {"chart": {"chartId": 7}}}]})

    result = await _call(service, [{"addChart": {"chart": {}}}])

    assert "Replies:" in result
    assert '"chartId": 7' in result


@pytest.mark.asyncio
async def test_batch_update_truncates_long_replies():
    reply = {"replies": [{"addChart": {"chart": {"title": "x" * 6000}}}]}
    service = _service(reply)

    result = await _call(service, [{"addChart": {"chart": {}}}])

    payload = json.dumps(reply["replies"])
    assert f"Replies: {payload[:MAX_BATCH_UPDATE_REPLY_CHARS]} … (truncated)" in result
    assert payload not in result


@pytest.mark.asyncio
async def test_batch_update_invalid_requests_make_no_call():
    service = _service({})

    with pytest.raises(UserInputError, match="at least one request"):
        await _call(service, [])

    service.spreadsheets.return_value.batchUpdate.assert_not_called()


@pytest.mark.asyncio
async def test_batch_update_http_error_is_reported():
    service = _service({})
    resp = Mock()
    resp.status = 400
    resp.reason = "Bad Request"
    service.spreadsheets.return_value.batchUpdate.return_value.execute = Mock(
        side_effect=HttpError(resp=resp, content=b"Invalid sheetId")
    )
    wrapped = handle_http_errors("batch_update_spreadsheet", service_type="sheets")(
        _unwrap(sheets_tools.batch_update_spreadsheet)
    )

    with pytest.raises(Exception, match="API error in batch_update_spreadsheet"):
        await wrapped(
            service=service,
            user_google_email="user@example.com",
            spreadsheet_id="sid",
            requests=[SORT_REQUEST],
        )


@pytest.mark.asyncio
async def test_batch_update_logs_kinds_not_bodies(caplog):
    service = _service({"replies": [{}, {}]})

    with caplog.at_level(logging.INFO):
        await _call(service, [FILTER_REQUEST, SORT_REQUEST])

    messages = [record.getMessage() for record in caplog.records]
    assert any("Kinds: setBasicFilter, sortRange" in m for m in messages)
    assert not any("sortSpecs" in m for m in messages)


@pytest.mark.asyncio
async def test_batch_update_is_destructive_write_tool():
    tool = await server.get_tool("batch_update_spreadsheet")
    annotations = tool.annotations

    def hint(camel, snake):
        value = getattr(annotations, camel, None)
        return value if value is not None else getattr(annotations, snake, None)

    assert hint("destructiveHint", "destructive_hint") is True
    assert hint("readOnlyHint", "read_only_hint") is False


@pytest.mark.asyncio
async def test_batch_update_description_guides_the_agent():
    tool = await server.get_tool("batch_update_spreadsheet")

    for expected in (
        "setBasicFilter",
        "sortRange",
        "format_sheet_range",
        "deleteSheet",
        "get_spreadsheet_info",
    ):
        assert expected in tool.description


def test_batch_update_accepts_json_string_requests():
    hints = typing.get_type_hints(
        _unwrap(sheets_tools.batch_update_spreadsheet), include_extras=True
    )

    assert hints["requests"] == DictList
    assert TypeAdapter(hints["requests"]).validate_python('[{"sortRange": {}}]') == [
        {"sortRange": {}}
    ]


@pytest.mark.asyncio
async def test_batch_update_schema_requires_a_list_of_objects():
    tool = await server.get_tool("batch_update_spreadsheet")
    requests_schema = tool.parameters["properties"]["requests"]

    assert requests_schema["type"] == "array"
    assert requests_schema["items"]["type"] == "object"
    assert "requests" in tool.parameters["required"]


def test_batch_update_is_in_the_complete_tier_of_sheets():
    core_tools, _ = resolve_tools_from_tier("core", ["sheets"])
    complete_tools, services = resolve_tools_from_tier("complete", ["sheets"])

    assert "batch_update_spreadsheet" in complete_tools
    assert "batch_update_spreadsheet" not in core_tools
    assert services == ["sheets"]


def test_batch_update_requires_the_sheets_write_scope():
    required = sheets_tools.batch_update_spreadsheet._required_google_scopes

    assert SHEETS_WRITE_SCOPE in required
    assert has_required_scopes({SHEETS_WRITE_SCOPE}, required)
