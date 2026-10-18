"""Where a video's job files and render live, derived from its ids.

The videos table has four path columns (voice_file_path, timeline_path,
scene_config_path, video_path). They used to be the source of truth for every
reader, and PATCH /videos/<id> and MCP update_video let a caller write any
string into them (TMDEV-159/162): the worker then staged whatever file the
column named into the render, validate_job parsed it, and archive deleted
`<output>/<project>/<basename of video_path>`, so pointing one video's
video_path at "B.mp4" deleted video B's render.

The columns are now server-written only and serve as "this was written"
markers. Every reader derives the real location here from the ids, which a
row tampered with before the fix cannot influence.

The writers use the same names: mcp/server.py's generate_voice and
write_scene_config, and the worker's render output. A test pins that.

Ids are checked here with ids.is_component, not ids.check_segment: this is a
filesystem use, and a row created before the creation rule (`a.b`) must keep
working (ids.py states the contract).

Containment has two halves. ids.inside catches a `..` or a symlink that leads
out of the root. It cannot catch a symlink that stays inside: `<jobs>/vid_a ->
<jobs>/vid_b` resolves under the jobs root, and A would read B's audio (or
`<output>/proj_a -> <output>/proj_b` would render A into B's directory). So
every component below the root is lstat'ed, and a symlink anywhere on the way
is refused. Nothing Tubematic writes under these roots is a symlink. The root
itself may be one (dev and test setups point the data root through a link):
it is resolved once and only what lies below it is walked. A component that
does not exist yet ends the walk, because writers ask for paths they are about
to create.

Known residual: this is a check, then a later use by path. A process that can
write under the root could swap a checked directory for a symlink in between.
Closing that needs every read and write to go through a directory descriptor
opened beneath the root (openat2 with RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS),
which this layer does not do. Everything that writes under these roots is
Tubematic's own containers.
"""
import os
from pathlib import Path

from tubematic_core import ids

AUDIO = "audio.mp3"
TIMELINE = "timeline.json"
SCENE_CONFIG = "scene-config.json"
IMAGES = "images"
JOB_FILES = (AUDIO, TIMELINE, SCENE_CONFIG)


class UnsafePath(ValueError):
    """An id or file that must not be turned into a path. The message says why."""


def job_dir(jobs_dir, video_id) -> Path:
    """`<jobs_dir>/<video_id>`, refusing an unusable id or a symlink on the way."""
    _check_video_id(video_id)
    return join_below(jobs_dir, video_id)


def job_file(jobs_dir, video_id, name) -> Path:
    """The path of one of a video's fixed job files. It may not exist yet.

    Refuses a symlink anywhere below the root, the file included: nothing
    Tubematic writes is a symlink, and one is exactly how a file from
    elsewhere would be staged into a render.
    """
    if name not in JOB_FILES:
        raise UnsafePath(f"{name!r} is not a job file")
    _check_video_id(video_id)
    return join_below(jobs_dir, video_id, name)


def images_dir(jobs_dir, video_id) -> Path:
    """`<jobs_dir>/<video_id>/images`, refusing a symlink on the way."""
    _check_video_id(video_id)
    return join_below(jobs_dir, video_id, IMAGES)


def output_file(output_dir, project_id, video_id) -> Path:
    """`<output_dir>/<project>/<video_id>.mp4`, where the worker renders to.

    A blank project is "default_proj", where the worker has always written a
    project-less video. Both ids get the is_component check: agents chose
    project ids, and a legacy id of either kind with a dot must keep
    rendering. Containment is what makes that safe.
    """
    project = project_id or "default_proj"
    if not ids.is_component(project):
        raise UnsafePath(f"project id {project!r} cannot be used as a directory name")
    _check_video_id(video_id)
    return join_below(output_dir, project, f"{video_id}.mp4")


def image_file(jobs_dir, video_id, filename) -> Path:
    """`<jobs_dir>/<video_id>/images/<filename>`, refusing a symlink on the way."""
    if not ids.is_component(filename):
        raise UnsafePath(f"image file name {filename!r} cannot be used as a file name")
    _check_video_id(video_id)
    return join_below(jobs_dir, video_id, IMAGES, filename)


def scene_file(scenes_dir, video_id, scene_name) -> Path:
    """`<scenes_dir>/<video_id>/<scene_name>.tsx`, a video's generated scene.

    An empty video_id is the legacy flat `<scenes_dir>/<scene_name>.tsx`,
    written before scenes were namespaced per video, which stays readable
    and deletable. Either way a symlink on the way is refused: generated
    scenes are compiled into every render, and `vid_a -> vid_b` would let one
    video read or overwrite another's.
    """
    if not ids.is_component(scene_name):
        raise UnsafePath(f"scene name {scene_name!r} cannot be used as a file name")
    if video_id == "":
        return join_below(scenes_dir, f"{scene_name}.tsx")
    _check_video_id(video_id)
    return join_below(scenes_dir, video_id, f"{scene_name}.tsx")


def ignore_symlinks(directory, names):
    """A shutil.copytree `ignore=` that drops symlinks.

    copytree follows symlinks by default, so a link planted in images/ would
    copy whatever it points at into the render's public dir.
    """
    return [n for n in names if os.path.islink(os.path.join(directory, n))]


def _check_video_id(video_id) -> None:
    if not ids.is_component(video_id):
        raise UnsafePath(f"video id {video_id!r} cannot be used as a file or directory name")


def _check_name_length(part) -> None:
    """Refuse a component the filesystem cannot hold.

    ids.is_component bounds an id at MAX_COMPONENT_BYTES, but output_file and
    scene_file append ".mp4" / ".tsx" to it: a 252-byte id passes as a
    directory name and makes a 256-byte file name, whose write fails with
    ENAMETOOLONG mid-render or mid-tool. Checking every joined part here
    bounds the name actually used, suffix included.
    """
    try:
        size = len(part.encode("utf-8"))
    except UnicodeEncodeError:
        raise UnsafePath(f"{part!r} cannot be encoded as a file name") from None
    if size > ids.MAX_COMPONENT_BYTES:
        raise UnsafePath(f"file name {part[:40]!r}... is {size} bytes, longer than the "
                         f"{ids.MAX_COMPONENT_BYTES} a file name can be")


def join_below(root, *parts) -> Path:
    """`root/parts...`, refusing a symlink in any component below `root`.

    The parts are joined as given; only their length is checked here (so a
    suffix added to a checked id is counted). The helpers above check the ids
    first. Use it directly only for parts already checked, or
    with a containment check of your own afterwards.

    Walks from the resolved root, so a symlinked root is fine. The walk stops
    at the first component that does not exist: nothing below it can be a
    link. The returned path keeps the caller's spelling of `root`.
    """
    for part in parts:
        _check_name_length(part)
    current = Path(root).resolve()
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise UnsafePath(f"{Path(root).joinpath(*parts)}: {current} is a symlink, refused")
        if not current.exists():
            break
    path = Path(root).joinpath(*parts)
    if not ids.inside(root, path):
        raise UnsafePath(f"{path} resolves outside {root}")
    return path
