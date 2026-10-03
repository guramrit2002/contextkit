import pytest

from core.projects import MAX_PROJECT_ID_LENGTH, normalize_or_keep, normalize_project_id

CANONICAL_FORMS = [
    ("https://github.com/Owner/Repo.git", "https://github.com/owner/repo"),
    ("http://github.com/owner/repo/", "https://github.com/owner/repo"),
    ("https://user:token@github.com/owner/repo", "https://github.com/owner/repo"),
    ("git@github.com:owner/repo.git", "https://github.com/owner/repo"),
    ("ssh://git@github.com:22/owner/repo.git", "https://github.com/owner/repo"),
    ("git://github.com/owner/repo", "https://github.com/owner/repo"),
    ("github.com/owner/repo", "https://github.com/owner/repo"),
    ("https://GitLab.com/Group/Sub/Repo.git", "https://gitlab.com/Group/Sub/Repo"),
    ("  /Users/me/app/  ", "/Users/me/app"),
]

MORE_FORMS = [
    # scp-style remote with an absolute path.
    ("git@host.example:/srv/repo.git", "https://host.example/srv/repo"),
    # Not remotes: a Windows path, an unsupported scheme, a plain name, the root folder.
    (r"C:\Users\me\app", r"C:\Users\me\app"),
    ("file:///tmp/repo", "file:///tmp/repo"),
    ("local-proj", "local-proj"),
    ("/", "/"),
    # A host with no repository path is left as a trimmed URL.
    ("https://github.com/", "https://github.com"),
]


@pytest.mark.parametrize(("raw", "expected"), CANONICAL_FORMS + MORE_FORMS)
def test_normalizes_to_canonical_form(raw, expected):
    assert normalize_project_id(raw) == expected


@pytest.mark.parametrize("raw", [raw for raw, _ in CANONICAL_FORMS + MORE_FORMS])
def test_normalization_is_idempotent(raw):
    once = normalize_project_id(raw)

    assert normalize_project_id(once) == once


def test_repeated_git_suffixes_are_all_removed_so_it_stays_idempotent():
    assert normalize_project_id("https://gitlab.com/g/repo.git/.git") == "https://gitlab.com/g/repo"


@pytest.mark.parametrize("raw", ["", "   ", "\n\t"])
def test_empty_input_raises_value_error(raw):
    with pytest.raises(ValueError, match="cannot be empty"):
        normalize_project_id(raw)


def test_non_string_raises_value_error():
    with pytest.raises(ValueError):
        normalize_project_id(None)


def test_over_length_result_raises():
    # Normalizing adds "https://", which can push an in-limit input over the limit.
    raw = "github.com/" + "a" * (MAX_PROJECT_ID_LENGTH - len("github.com/"))

    with pytest.raises(ValueError, match="too long"):
        normalize_project_id(raw)


def test_normalize_or_keep_returns_canonical_or_original():
    assert normalize_or_keep("git@github.com:o/r.git") == "https://github.com/o/r"
    assert normalize_or_keep(None) is None
    assert normalize_or_keep("") == ""
    too_long = "github.com/" + "a" * MAX_PROJECT_ID_LENGTH
    assert normalize_or_keep(too_long) == too_long
