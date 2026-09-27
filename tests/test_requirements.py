"""requirements.txt (the hosted install) must stay in sync with pyproject.toml."""
import tomllib

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from core.config import REPO_ROOT

REGENERATE = (
    "Regenerate it: uv export --format requirements-txt --no-emit-project --no-hashes "
    "-o requirements.txt"
)
# Extras of runtime dependencies that pull in a separately named package.
EXTRA_PACKAGES = {("psycopg", "binary"): "psycopg-binary"}
# Horizon only runs the MCP server; these belong to the Django backend or local tooling.
NOT_DEPLOYED = {"django", "djangorestframework", "dj-database-url", "pytest", "ruff", "mypy"}


def runtime_dependencies() -> list[Requirement]:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    return [Requirement(dep) for dep in pyproject["project"]["dependencies"]]


def pinned_versions() -> dict[str, str]:
    pins = {}
    for line in (REPO_ROOT / "requirements.txt").read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        requirement = Requirement(line)
        [spec] = requirement.specifier
        assert spec.operator == "==", f"{line!r} is not pinned to an exact version"
        pins[canonicalize_name(requirement.name)] = spec.version
    return pins


def test_every_runtime_dependency_is_pinned_within_its_range():
    pins = pinned_versions()

    for dep in runtime_dependencies():
        name = canonicalize_name(dep.name)
        assert name in pins, (
            f"{dep.name} is in pyproject.toml but not requirements.txt. {REGENERATE}"
        )
        assert dep.specifier.contains(pins[name], prereleases=True), (
            f"requirements.txt pins {dep.name}=={pins[name]}, outside {dep.specifier}. "
            f"{REGENERATE}"
        )
        for extra in dep.extras:
            package = EXTRA_PACKAGES.get((name, extra))
            if package:
                assert package in pins, f"{dep.name}[{extra}] needs {package}. {REGENERATE}"


def test_backend_and_dev_tools_are_not_deployed():
    assert not NOT_DEPLOYED & set(pinned_versions()), (
        "requirements.txt is for the hosted MCP server only; export without extras. "
        + REGENERATE
    )


def test_every_line_is_pinned():
    assert pinned_versions()
