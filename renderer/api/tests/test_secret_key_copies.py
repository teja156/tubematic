"""The secret-typed settings keys are spelled in three places (TMDEV-167).

pipeline.py's SETTINGS_SPEC is the source. mcp/server.py and
scripts/collect_diagnostics.py each keep a copy, because neither can import
pipeline.py: the MCP container has no renderer/api on its path, and the
diagnostics collector ships in the release tarball, which carries no renderer/.
A key missing from either copy is a credential redacted by pattern only, or not
at all — MCP's copy had already lost discord_webhook_url once.

The copies are read with ast rather than imported, so this test needs neither
the MCP server's dependencies nor the onboarding package.
"""
import ast
import pathlib

import pytest

import pipeline

REPO = pathlib.Path(__file__).resolve().parents[3]


def _tuple_named(path: pathlib.Path, name: str) -> tuple:
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in {path}")


@pytest.mark.parametrize("copy", ["mcp/server.py", "scripts/collect_diagnostics.py"])
def test_every_copy_names_exactly_the_secret_typed_settings(copy):
    spec = {k for k, (typ, _) in pipeline.SETTINGS_SPEC.items() if typ == "secret"}
    assert set(_tuple_named(REPO / copy, "SECRET_SETTING_KEYS")) == spec
