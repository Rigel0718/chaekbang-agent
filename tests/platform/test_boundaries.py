"""도메인 컨텍스트 import 경계 검사 (design.md 1번 경계 규칙 2·3).

- catalog는 다른 컨텍스트를 import하지 않는다.
- storefront, owner_ops, supply는 서로의 모듈을 import하지 않는다.
- 다른 컨텍스트의 models는 catalog 것도 import하지 않는다 (catalog는 service·schema로만 쓴다).
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"
CONTEXTS = ("catalog", "storefront", "owner_ops", "supply")
LAYERS = ("models", "services", "schemas", "api", "seed")


def _target_of_module(module: str) -> tuple[str, str] | None:
    """`app.<layer>.<context>...` 형태면 (layer, context)를 돌려준다."""
    parts = module.split(".")
    if len(parts) >= 3 and parts[0] == "app" and parts[1] in LAYERS and parts[2] in CONTEXTS:
        return parts[1], parts[2]
    return None


def _violation(ctx: str, module: str) -> str | None:
    target = _target_of_module(module)
    if target is None or target[1] == ctx:
        return None
    layer, target_ctx = target
    if ctx == "catalog":
        return "catalog는 다른 컨텍스트를 알면 안 된다"
    if target_ctx != "catalog":
        return "A·B·C 컨텍스트끼리는 서로 import하지 않는다"
    if layer == "models":
        return "다른 컨텍스트의 models는 import하지 않는다 (catalog service를 쓴다)"
    return None


def _context_files() -> list[tuple[str, Path]]:
    files = []
    for layer in LAYERS:
        for ctx in CONTEXTS:
            files += [(ctx, p) for p in (APP / layer).glob(f"{ctx}.py")]
            files += [(ctx, p) for p in (APP / layer / ctx).rglob("*.py")]
    return files


def _imported_modules(path: Path) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            modules |= {f"{node.module}.{alias.name}" for alias in node.names}
    return modules


def test_context_modules_exist() -> None:
    assert _context_files(), "컨텍스트 모듈을 찾지 못했다"


@pytest.mark.parametrize(
    ("ctx", "path"),
    _context_files(),
    ids=lambda v: str(v.relative_to(APP)) if isinstance(v, Path) else v,
)
def test_context_imports_respect_boundaries(ctx: str, path: Path) -> None:
    for module in _imported_modules(path):
        reason = _violation(ctx, module)
        assert reason is None, f"{path.relative_to(APP)}가 {module}를 import한다: {reason}"


@pytest.mark.parametrize(
    ("ctx", "module", "allowed"),
    [
        ("supply", "app.services.catalog.books", True),
        ("supply", "app.schemas.catalog", True),
        ("supply", "app.models.catalog", False),
        ("supply", "app.services.storefront", False),
        ("owner_ops", "app.models.supply.QuoteDraft", False),
        ("catalog", "app.services.supply.institutions", False),
        ("catalog", "app.models.base", True),
        ("storefront", "app.models.storefront.ChatLog", True),
    ],
)
def test_boundary_rule_examples(ctx: str, module: str, allowed: bool) -> None:
    assert (_violation(ctx, module) is None) is allowed
