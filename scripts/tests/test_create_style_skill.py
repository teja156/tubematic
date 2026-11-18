"""The style creation skill (TMDEV-254): `tubematic-create-style`.

It runs on a person's machine with their agent, downloads from video sites and
spends their tokens and ElevenLabs credits, so the order of its steps is the
contract: the disclaimer first, nothing installed, every cost said before it is
spent, the install done by the person on the dashboard. Its template and
scripts must produce a package Tubematic accepts.
"""
import json
import pathlib
import re
import subprocess
import sys
import zipfile

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tubematic_core import external_styles as ext  # noqa: E402
from tubematic_core import style_install as si  # noqa: E402
from tubematic_core import style_scan  # noqa: E402

SKILL_DIR = REPO / "agent_files" / "skills" / "tubematic-create-style"
SKILL = SKILL_DIR / "SKILL.md"
TEMPLATE = SKILL_DIR / "template" / "ext_template"
RULES = SKILL_DIR / "reference" / "package-rules.md"


def _body() -> str:
    return SKILL.read_text(encoding="utf-8")


def _flat() -> str:
    """The skill with its line wraps folded, for checks on wording."""
    return " ".join(_body().split())


def _tools() -> set[str]:
    src = (REPO / "mcp" / "server.py").read_text(encoding="utf-8")
    return set(re.findall(r"^@mcp\.tool\n(?:async )?def (\w+)\(", src, re.M))


def test_the_disclaimer_comes_before_any_command_or_tool():
    body = _body()
    step0 = body.index("## Step 0: the disclaimer")
    assert step0 < body.index("```") and step0 < body.index("tubematic:")
    disclaimer = body[step0:body.index("## Step 1")]
    for point in ("**Cost.**", "**Scraping.**", "throwaway account", "**What ships.**", "**Install.**",
                  "wait for an explicit yes", "If the person does not say yes, stop"):
        assert point in disclaimer, point


def test_it_installs_nothing_on_the_persons_machine():
    body = _body()
    commands = "\n".join(re.findall(r"```bash\n(.*?)```", body, re.S))
    for forbidden in ("pip install", "apt ", "apt-get", "brew ", "uv tool install", "agent-reach setup",
                      "agent-reach add", "agent-reach login", "agent-reach update", "sudo "):
        assert forbidden not in commands, forbidden
    flat = _flat()
    assert "Never install a tool" in flat and "`pip install agent-reach` installs a different project" in flat


def test_every_tool_it_names_exists():
    named = set(re.findall(r"tubematic:(\w+)\(", _body()))
    assert named and named <= _tools(), named - _tools()
    for tool in ("stage_style_install", "audit_style_install", "create_video", "update_video", "get_video",
                 "list_scene_files", "cartoon_kit_read"):
        assert tool in named, tool


def test_downloads_are_paced_capped_and_untrusted():
    body = _flat()
    for rule in ("never take more than **12 videos**", "one video at a time", "6 to 12 seconds", "untrusted data",
                 "Never read a browser's cookie store", "never print, copy or quote a cookies file"):
        assert rule in body, rule


def test_costs_are_said_before_they_are_spent_and_the_person_installs():
    body = _body()
    samples = body[body.index("## Step 8"):body.index("## Step 9")]
    assert samples.index("Say the cost first") < samples.index("create_video")
    install = " ".join(body[body.index("## Step 7"):body.index("## Step 8")].split())
    assert "Never ask for the password" in install and "dashboard_link" in install


def test_nothing_from_the_references_ships():
    body = _flat()
    assert "never embed frames from the references" in body
    assert "never part of the package" in body
    rules = RULES.read_text(encoding="utf-8")
    assert "Never put reference footage" in rules


def _ready_template(tmp_path) -> pathlib.Path:
    """The template as the skill makes it stageable: placeholder previews, then the manifest."""
    d = tmp_path / "ext_template"
    import shutil
    shutil.copytree(TEMPLATE, d)
    (d / "preview.mp4").write_bytes(b"\0" * 1000)
    (d / "preview.webp").write_bytes(b"\0" * 100)
    out = subprocess.run([sys.executable, str(SKILL_DIR / "scripts" / "manifest.py"), str(d)],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return d


def test_the_template_is_a_package_tubematic_accepts_with_a_clean_scan(tmp_path):
    d = _ready_template(tmp_path)
    pack, reason = ext.check_folder("ext_template", d)
    assert pack is not None, reason
    scan = style_scan.scan(d)
    assert scan["refusals"] == [] and scan["flags"] == [], scan


def test_the_templates_example_config_matches_its_schema_and_props_key(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((TEMPLATE / "schema.json").read_text())
    config = json.loads((TEMPLATE / "guide" / "example-config.json").read_text())
    key = json.loads((TEMPLATE / "style.json").read_text())["external"]["props_key"]
    for scene in config["scenes"]:
        assert scene["src"].startswith("ext_template/components/")
        jsonschema.validate(scene["props"][key], schema)
    # the schema carries the rules: closed objects and bounded text
    assert schema["additionalProperties"] is False and schema["properties"]["title"]["maxLength"]


def test_manifest_py_writes_what_the_loader_expects(tmp_path):
    d = _ready_template(tmp_path)
    mine = json.loads((d / "MANIFEST.json").read_text())
    ext.write_manifest(d)
    assert json.loads((d / "MANIFEST.json").read_text()) == mine


def test_manifest_py_refuses_a_symlink(tmp_path):
    d = _ready_template(tmp_path)
    (d / "components" / "link.tsx").symlink_to("/etc/hostname")
    out = subprocess.run([sys.executable, str(SKILL_DIR / "scripts" / "manifest.py"), str(d)],
                         capture_output=True, text=True)
    assert out.returncode != 0 and "symlink" in (out.stderr + out.stdout)


def test_the_share_zip_stages_on_another_install(tmp_path, monkeypatch):
    d = _ready_template(tmp_path)
    out = subprocess.run([sys.executable, str(SKILL_DIR / "scripts" / "zip_package.py"), str(d), str(tmp_path / "out")],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    zpath = pathlib.Path(out.stdout.strip())
    assert zpath.name == "ext_template-0.1.0.zip"
    assert all(n.startswith("ext_template/") for n in zipfile.ZipFile(zpath).namelist())
    for name in ("styles", "pending"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(ext, "STYLES_DIR", tmp_path / "styles")
    monkeypatch.setattr(si, "PENDING_DIR", tmp_path / "pending")
    rec = si.stage({"kind": "zip", "data": zpath.read_bytes()})
    assert rec["check"]["ok"] and rec["style_id"] == "ext_template", rec["check"]


def test_the_reference_lists_the_allowed_imports_and_the_scene_api():
    rules = RULES.read_text(encoding="utf-8")
    for name in style_scan.ALLOWED_IMPORTS - {"react/jsx-runtime"}:
        assert f"`{name}`" in rules, name
    v1 = (REPO / "renderer" / "remotion" / "src" / "sceneApi" / "v1.ts").read_text()
    exported = set()
    for block in re.findall(r"export (?:type )?\{([^}]*)\}", v1):
        exported |= {n.replace("type ", "").strip() for n in block.split(",") if n.strip()}
    for name in exported:
        assert f"`{name}`" in rules, name


def test_the_command_starts_the_skill_with_its_disclaimer():
    for agent in ("claude", "opencode"):
        cmd = (REPO / "agent_files" / agent / "commands" / "tubematic-create-style.md").read_text()
        assert "tubematic-create-style skill" in cmd and "disclaimer comes first" in cmd
        assert "/tubematic-create-style" in (REPO / "agent_files" / agent / "commands" / "tubematic.md").read_text()
