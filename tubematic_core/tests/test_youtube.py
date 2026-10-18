"""The one rule for a mining URL (tubematic_core.youtube).

A mining URL becomes Gemini's file_data.file_uri on a paid call, so a string
that is not a YouTube video must never pass — the refusals below are the
point of this file. Each is next to an accepted form, so a rule that refused
everything would fail too.
"""
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import youtube  # noqa: E402

ID = "dQw4w9WgXcQ"
CANON = f"https://www.youtube.com/watch?v={ID}"


@pytest.mark.parametrize("url", [
    f"https://www.youtube.com/watch?v={ID}",
    f"https://youtube.com/watch?v={ID}",
    f"http://www.youtube.com/watch?v={ID}",
    f"https://m.youtube.com/watch?v={ID}",
    f"https://www.youtube.com/watch?v={ID}&t=30",
    f"https://www.youtube.com/watch?v={ID}&list=PLx&index=2#t=1m",
    f"https://www.youtube.com/watch?feature=share&v={ID}",
    f"https://youtu.be/{ID}",
    f"https://youtu.be/{ID}?si=AbCdEf123_-",
    f"http://youtu.be/{ID}?t=42",
    f"https://www.youtube.com/shorts/{ID}",
    f"https://youtube.com/shorts/{ID}?feature=share",
    f"https://m.youtube.com/shorts/{ID}",
    f"https://www.youtube.com/live/{ID}",
    f"https://www.youtube.com/live/{ID}?si=x",
    f"  https://youtu.be/{ID}  ",
    f"HTTPS://WWW.YOUTUBE.COM/watch?v={ID}",
])
def test_an_accepted_form_becomes_the_canonical_watch_url(url):
    assert youtube.canonical_youtube_url(url) == CANON


@pytest.mark.parametrize("value", [
    "file:///etc/passwd",
    f"file:///watch?v={ID}",
    "http://127.0.0.1/",
    f"http://127.0.0.1/watch?v={ID}",
    f"http://169.254.169.254/latest/meta-data/?v={ID}",
    "http://[::1]/",
    f"https://youtube.com.evil.com/watch?v={ID}",
    f"https://evil.com/youtube.com/watch?v={ID}",
    f"https://youtube.com@evil.com/watch?v={ID}",
    f"https://user:pass@www.youtube.com/watch?v={ID}",
    f"https://www.youtube.com:8080/watch?v={ID}",
    f"https://evilyoutube.com/watch?v={ID}",
    f"https://music.youtube.com/watch?v={ID}",
    f"https://youtu.be.evil.com/{ID}",
    f"ftp://www.youtube.com/watch?v={ID}",
    f"//www.youtube.com/watch?v={ID}",
    f"www.youtube.com/watch?v={ID}",
    "https://youtu.be/dQw4w9WgXc",            # 10-character id
    "https://youtu.be/dQw4w9WgXcQQ",          # 12-character id
    "https://www.youtube.com/watch?v=dQw4w9WgXc",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQQ",
    "https://www.youtube.com/shorts/dQw4w9WgXcQQ",
    f"https://www.youtube.com/watch?xv={ID}",
    f"https://www.youtube.com/watch?v={ID}\nhttp://127.0.0.1/",
    f"https://youtu.be/{ID}\n#",
    f"https://youtu.be/{ID}?a=b c",
    f"https://youtu.be/{ID}?a=\tb",
    f"https://youtu.be/{ID}\x00",
    f"https://youtu.be/{ID}/extra",
    f"https://youtu.be/{ID}?é=1",
    f"https://www.youtube.com/embed/{ID}",
    "https://www.youtube.com/@channel",
    "https://www.youtube.com/playlist?list=PLx",
    "https://youtu.be/",
    "",
    "   ",
    "not a url",
    None,
    42,
    ["https://youtu.be/" + ID],
    {"url": "https://youtu.be/" + ID},
])
def test_anything_else_is_refused(value):
    assert youtube.canonical_youtube_url(value) is None


def test_a_list_is_canonicalised_and_deduplicated_in_order():
    other = "abcdefghijk"
    urls, bad = youtube.canonical_youtube_urls([
        f"https://youtu.be/{ID}", f"https://www.youtube.com/shorts/{other}",
        f"https://m.youtube.com/watch?v={ID}&t=3", "file:///x", 7,
    ])
    assert urls == [CANON, f"https://www.youtube.com/watch?v={other}"]
    assert bad == ["file:///x", 7]


def test_check_refuses_the_whole_list_and_names_every_bad_entry():
    urls, error = youtube.check_mining_sources(
        [f"https://youtu.be/{ID}", "http://127.0.0.1/", "https://youtu.be/short"])
    assert urls is None
    assert "'http://127.0.0.1/'" in error and "'https://youtu.be/short'" in error
    assert "youtu.be/<id>" in error


def test_check_quotes_a_long_entry_clipped():
    _, error = youtube.check_mining_sources(["x" * 5000])
    assert len(error) < 600


def test_check_accepts_an_empty_list_and_refuses_a_non_list():
    assert youtube.check_mining_sources([]) == ([], None)
    assert youtube.check_mining_sources("https://youtu.be/" + ID)[1] == \
        "youtube_urls must be a list"
    assert youtube.check_mining_sources(None)[0] is None


def _ids(n):
    return [f"https://youtu.be/{i:011d}" for i in range(n)]


def test_check_caps_the_number_of_distinct_sources():
    cap = youtube.MINING_MAX_SOURCES
    assert cap == 50
    assert youtube.check_mining_sources(_ids(cap))[0] == \
        [f"https://www.youtube.com/watch?v={i:011d}" for i in range(cap)]
    urls, error = youtube.check_mining_sources(_ids(cap + 1))
    assert urls is None and f"at most {cap}" in error


def test_the_cap_counts_distinct_videos_not_entries():
    urls, error = youtube.check_mining_sources(_ids(50) + _ids(50))
    assert error is None and len(urls) == 50
