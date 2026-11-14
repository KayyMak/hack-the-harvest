"""LangChain tool wrappers for the agent: `from harvest.tools import TOOLS`.

Each tool calls backend/app/tools.py through call_tool, so names and arguments match
TOOL_SPECS, failures come back as {"error": ...} instead of raising, and results are JSON
strings ready for a ToolMessage. Requires langchain-core (already a LangGraph dependency).
"""
import inspect
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / 'backend'
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app import tools as core  # noqa: E402
from app.tools import TOOL_SPECS, call_tool, log_step  # noqa: E402,F401

try:
    from langchain_core.tools import StructuredTool
    from pydantic import create_model
except ImportError as exc:  # pragma: no cover
    raise ImportError('harvest.tools needs langchain-core: pip install langchain-core') from exc


def _wrap(name: str, fn) -> StructuredTool:
    fields = {}
    for param in inspect.signature(fn).parameters.values():
        default = ... if param.default is inspect.Parameter.empty else param.default
        fields[param.name] = (param.annotation, default)
    schema = create_model(f'{name}_args', **fields)

    def run(**kwargs) -> str:
        args = {k: v for k, v in kwargs.items() if v is not None}
        return json.dumps(call_tool(name, args), default=str)

    return StructuredTool.from_function(func=run, name=name, args_schema=schema,
        description=inspect.getdoc(fn) or name)


TOOLS = [_wrap(name, fn) for name, fn in core.TOOLS.items()]
