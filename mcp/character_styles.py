"""The code-drawn character styles, in pack order. The MCP server, the picture
checks and the text-layout audit loop over this list, so a new style of this
kind is one module here (character_kit says what each module exposes)."""
import midcentury_howto
import process_cast

STYLES = (midcentury_howto, process_cast)
BY_ID = {m.STYLE_ID: m for m in STYLES}


def for_scene(scene):
    """The style module whose scene this is, or None."""
    return next((m for m in STYLES if m.is_scene(scene)), None)
