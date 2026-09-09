"""
Deterministic static AST route and schema extractor for FastAPI applications.
Executes FIRST before any network or model interaction.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any
from app.agents.builder.schemas import RouteItem

HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}


def normalize_route_template(path: str) -> str:
    """Normalize route path: strip trailing slashes, ensure leading slash."""
    clean = path.strip()
    if not clean.startswith("/"):
        clean = "/" + clean
    if len(clean) > 1 and clean.endswith("/"):
        clean = clean.rstrip("/")
    return clean


class FastAPIASTVisitor(ast.NodeVisitor):
    """AST visitor extracting FastAPI route decorators and parameter dependencies."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.routes: list[RouteItem] = []
        self.models_with_extra_allow: set[str] = set()
        self.debug_mode_enabled: bool = False

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Check for Pydantic models with extra='allow'."""
        for item in node.body:
            # Check model_config = ConfigDict(extra="allow") or dict(extra="allow")
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "model_config":
                        if isinstance(item.value, ast.Call):
                            for kw in item.value.keywords:
                                if kw.arg == "extra" and isinstance(kw.value, ast.Constant):
                                    if kw.value.value == "allow":
                                        self.models_with_extra_allow.add(node.name)
                        elif isinstance(item.value, ast.Dict):
                            for k, v in zip(item.value.keys, item.value.values):
                                if isinstance(k, ast.Constant) and k.value == "extra":
                                    if isinstance(v, ast.Constant) and v.value == "allow":
                                        self.models_with_extra_allow.add(node.name)
            # Check legacy class Config: extra = "allow"
            elif isinstance(item, ast.ClassDef) and item.name == "Config":
                for cfg_item in item.body:
                    if isinstance(cfg_item, ast.Assign):
                        for target in cfg_item.targets:
                            if isinstance(target, ast.Name) and target.id == "extra":
                                if isinstance(cfg_item.value, ast.Constant) and cfg_item.value.value == "allow":
                                    self.models_with_extra_allow.add(node.name)

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Check for FastAPI(debug=True)."""
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        if func_name == "FastAPI":
            for kw in node.keywords:
                if kw.arg == "debug" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    self.debug_mode_enabled = True

        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Extract route decorators from function definitions."""
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue

            # Case: @app.get("/path") or @router.post("/path")
            method = None
            if isinstance(dec.func, ast.Attribute) and dec.func.attr.lower() in HTTP_METHODS:
                method = dec.func.attr.upper()

            if method and dec.args and isinstance(dec.args[0], ast.Constant):
                raw_path = str(dec.args[0].value)
                route_template = normalize_route_template(raw_path)

                # Inspect function arguments for dependencies and input schemas
                requires_auth = False
                auth_dep = None
                input_fields = []
                extra_fields_allowed = False

                for arg in node.args.args:
                    arg_name = arg.arg
                    # Check type annotation for Pydantic models
                    if arg.annotation and isinstance(arg.annotation, ast.Name):
                        if arg.annotation.id in self.models_with_extra_allow:
                            extra_fields_allowed = True

                # Check defaults for Depends(get_current_user) or Header
                for default_val in node.args.defaults:
                    if isinstance(default_val, ast.Call):
                        call_func = ""
                        if isinstance(default_val.func, ast.Name):
                            call_func = default_val.func.id
                        elif isinstance(default_val.func, ast.Attribute):
                            call_func = default_val.func.attr

                        if call_func in ("Depends", "Security"):
                            requires_auth = True
                            if default_val.args and isinstance(default_val.args[0], ast.Name):
                                auth_dep = default_val.args[0].id
                        elif call_func == "Header":
                            requires_auth = True
                            auth_dep = "HeaderAuth"

                # Check if route is a debug endpoint
                is_debug = "debug" in route_template.lower() or "config" in route_template.lower()

                # Infer candidate owner parameter from path (e.g. {user_id}, {doc_id})
                owner_param = None
                for param in ("user_id", "owner_id", "account_id", "doc_id"):
                    if f"{{{param}}}" in route_template:
                        owner_param = param
                        break

                start_line = node.lineno
                end_line = getattr(node, "end_lineno", start_line)

                route_item = RouteItem(
                    route_template=route_template,
                    method=method,
                    handler_name=node.name,
                    source_file=self.file_path,
                    source_line_range=(start_line, end_line),
                    requires_auth=requires_auth,
                    auth_dependency=auth_dep,
                    resource_owner_param=owner_param,
                    input_fields=input_fields,
                    extra_fields_allowed=extra_fields_allowed,
                    is_debug_or_internal=is_debug,
                )
                self.routes.append(route_item)

        self.generic_visit(node)


def extract_routes_from_file(file_path: str | Path) -> tuple[list[RouteItem], bool]:
    """Parse a single Python file and extract declared routes and debug status."""
    path = Path(file_path)
    if not path.exists() or path.suffix != ".py":
        return [], False

    content = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(content, filename=str(path))
    except SyntaxError:
        return [], False

    visitor = FastAPIASTVisitor(file_path=path.name)
    visitor.visit(tree)
    return visitor.routes, visitor.debug_mode_enabled


def extract_routes_from_project(project_dir: str | Path) -> list[RouteItem]:
    """Scan all Python files in a directory and return sorted, normalized routes."""
    root = Path(project_dir)
    all_routes: list[RouteItem] = []

    for py_file in sorted(root.glob("**/*.py")):
        # Skip hidden or vendored dirs
        if any(
            part.startswith(".") or part in ("venv", ".venv", "__pycache__", "node_modules")
            for part in py_file.relative_to(root).parts
        ):
            continue
        routes, _ = extract_routes_from_file(py_file)
        all_routes.extend(routes)

    # Sort deterministically by route_template and method
    all_routes.sort(key=lambda r: (r.route_template, r.method))
    return all_routes
