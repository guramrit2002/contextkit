"""The pinned deploy files must stay in sync with pyproject.toml.

- requirements.txt:     the hosted MCP server's install on Render (runtime only).
- requirements-api.txt: the Django Docker image (runtime + the `backend` extra).
"""
import tomllib

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from core.config import REPO_ROOT

EXPORT = "uv export --format requirements-txt --no-emit-project --no-hashes"
REGENERATE = {
    "requirements.txt": f"{EXPORT} -o requirements.txt",
    "requirements-api.txt": f"{EXPORT} --extra backend -o requirements-api.txt",
}
# Extras of dependencies that pull in a separately named package.
EXTRA_PACKAGES = {("psycopg", "binary"): "psycopg-binary"}
DEV_TOOLS = {"pytest", "pytest-cov", "pytest-asyncio", "ruff", "mypy"}
BACKEND_ONLY = {"django", "djangorestframework", "dj-database-url", "gunicorn", "whitenoise"}


def pyproject() -> dict:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())


def expected_dependencies(filename: str) -> list[Requirement]:
    project = pyproject()["project"]
    deps = list(project["dependencies"])
    if filename == "requirements-api.txt":
        deps += project["optional-dependencies"]["backend"]
    return [Requirement(dep) for dep in deps]


def pinned_versions(filename: str) -> dict[str, str]:
    pins = {}
    for line in (REPO_ROOT / filename).read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        requirement = Requirement(line)
        [spec] = requirement.specifier
        assert spec.operator == "==", f"{filename}: {line!r} is not pinned to an exact version"
        pins[canonicalize_name(requirement.name)] = spec.version
    return pins


@pytest.mark.parametrize("filename", REGENERATE)
def test_every_dependency_is_pinned_within_its_range(filename):
    pins = pinned_versions(filename)
    hint = f"Regenerate it: {REGENERATE[filename]}"

    for dep in expected_dependencies(filename):
        name = canonicalize_name(dep.name)
        assert name in pins, f"{dep.name} is in pyproject.toml but not {filename}. {hint}"
        assert dep.specifier.contains(pins[name], prereleases=True), (
            f"{filename} pins {dep.name}=={pins[name]}, outside {dep.specifier}. {hint}"
        )
        for extra in dep.extras:
            package = EXTRA_PACKAGES.get((name, extra))
            if package:
                assert package in pins, f"{dep.name}[{extra}] needs {package}. {hint}"


@pytest.mark.parametrize("filename", REGENERATE)
def test_dev_tools_are_never_deployed(filename):
    assert not DEV_TOOLS & set(pinned_versions(filename)), (
        f"{filename} must not include dev tools. Regenerate it: {REGENERATE[filename]}"
    )


def test_mcp_image_has_no_django():
    assert not BACKEND_ONLY & set(pinned_versions("requirements.txt")), (
        "requirements.txt is the MCP server install only; export without extras. "
        f"Regenerate it: {REGENERATE['requirements.txt']}"
    )
