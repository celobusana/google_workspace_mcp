import inspect

import gcalendar.calendar_tools  # noqa: F401
import gdocs.docs_tools  # noqa: F401
import pytest
from pydantic import TypeAdapter

from core.server import server
from core.tool_registry import get_tool_components


def _listed_values(field_schema):
    options = field_schema.get("anyOf", [field_schema])
    return [value for option in options for value in option.get("enum", [])]


# Clients that turn an unlisted "none" string into null rely on the schema listing it.
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "field_name", "values"),
    [
        ("manage_event", "send_updates", ["all", "externalOnly", "none"]),
        ("get_doc_as_markdown", "comment_mode", ["inline", "appendix", "none"]),
        (
            "update_paragraph_style",
            "list_type",
            ["UNORDERED", "ORDERED", "CHECKBOX", "NONE"],
        ),
        ("modify_doc_text", "baseline_offset", ["NONE", "SUPERSCRIPT", "SUBSCRIPT"]),
    ],
)
async def test_values_including_none_are_listed_in_the_schema(
    tool_name, field_name, values
):
    tools = {tool.name: tool for tool in await server.list_tools()}

    assert _listed_values(tools[tool_name].parameters["properties"][field_name]) == (
        values
    )


@pytest.mark.parametrize(
    ("tool_name", "field_name"),
    [("update_paragraph_style", "list_type"), ("modify_doc_text", "baseline_offset")],
)
def test_upper_case_values_still_accept_any_case(tool_name, field_name):
    tool = get_tool_components(server)[tool_name]
    annotation = inspect.signature(tool.fn).parameters[field_name].annotation

    assert TypeAdapter(annotation).validate_python("none") == "NONE"
