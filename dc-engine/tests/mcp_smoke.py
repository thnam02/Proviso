"""End-to-end check: start the MCP server over stdio and call its tools
like an agent would.  Usage:  python tests/mcp_smoke.py <repo-root>"""

from __future__ import annotations

import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "src")


def _text(result) -> str:
    return "\n".join(getattr(c, "text", "") for c in result.content)


async def run(root: str) -> int:
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "dc_engine.server", "--root", root],
        env={"PYTHONPATH": SRC, "DC_TYPECHECK": "off"},
    )
    async with stdio_client(params) as streams:
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = sorted(t.name for t in (await session.list_tools()).tools)
            print("tools:", ", ".join(tools))
            expected = {"dc_repo_map", "dc_find_symbol", "dc_get_symbol", "dc_get_slice",
                        "dc_find_references", "dc_file_outline", "dc_replace_symbol",
                        "dc_insert_symbol", "dc_index_status", "dc_create_contract",
                        "dc_check_contract", "dc_get_contract", "dc_list_contracts",
                        "dc_close_contract"}
            missing = expected - set(tools)
            if missing:
                print("MISSING:", missing)
                return 1
            created = _text(await session.call_tool("dc_create_contract", {
                "task": "charge zero should raise ValueError",
                "targets": ["billing.validate_amount"],
                "must_change": [{
                    "id": "zero",
                    "setup": ("from decimal import Decimal\n"
                              "from shop.models import User\n"
                              "from shop.billing import charge\n"
                              "user = User('a', 'AU')\n"),
                    "call": "charge(user, Decimal(0))",
                    "expect_new": {"raises": "ValueError"},
                }],
                "must_preserve": [],
            }))
            print(created)
            assert created.startswith("✓ contract created:"), created
            cid = created.split(":", 1)[1].strip().split()[0]
            checked = _text(await session.call_tool("dc_check_contract", {"contract_id": cid}))
            print(checked)
            assert "not changed" in checked, checked
            out = _text(await session.call_tool("dc_get_slice", {"targets": ["billing.charge"]}))
            print(out)
            assert "== TARGET shop.billing.charge" in out, "slice missing target"
            assert "shop.api.checkout" in out, "slice missing caller"
            out = _text(await session.call_tool(
                "dc_replace_symbol",
                {"name": "Service.helper", "new_code": "def helper(self) -> int:\n    return 42\n"}))
            print(out)
            assert out.startswith("✓ replaced"), "edit failed"
            print("MCP smoke test passed")
            return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run(os.path.abspath(sys.argv[1]))))
