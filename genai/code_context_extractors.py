import ast
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


HTTP_METHOD_DECORATORS = {"get", "post", "put", "patch", "delete", "options", "head"}
TASK_DECORATORS = {"task", "shared_task"}
SPAN_CALLS = {"start_as_current_span", "start_span"}


def _get_constant_string(node: Optional[ast.AST]) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _full_attr_name(node: ast.AST) -> str:
    parts: List[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _extract_function_calls(function_node: ast.AST) -> List[str]:
    calls: List[str] = []
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            calls.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            calls.append(_full_attr_name(node.func))
    return calls


def _extract_spans(function_node: ast.AST) -> List[Dict[str, Any]]:
    spans: List[Dict[str, Any]] = []
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or not node.args:
            continue
        if node.func.attr not in SPAN_CALLS:
            continue
        span_name = _get_constant_string(node.args[0])
        if span_name:
            spans.append(
                {
                    "span_name": span_name,
                    "line_start": getattr(node, "lineno", None),
                    "line_end": getattr(node, "end_lineno", None),
                }
            )
    return spans


def _extract_tasks(function_node: ast.AST) -> List[Dict[str, Any]]:
    tasks: List[Dict[str, Any]] = []
    for decorator in getattr(function_node, "decorator_list", []):
        decorator_name = ""
        task_name = ""
        if isinstance(decorator, ast.Name):
            decorator_name = decorator.id
        elif isinstance(decorator, ast.Attribute):
            decorator_name = decorator.attr
        elif isinstance(decorator, ast.Call):
            decorator_name = _call_name(decorator.func)
            for keyword in decorator.keywords:
                if keyword.arg == "name":
                    task_name = _get_constant_string(keyword.value)
        if decorator_name in TASK_DECORATORS:
            tasks.append({"queue_name": task_name or function_node.name, "handler_name": function_node.name})
    return tasks


def extract_python_artifacts(repo_root: str) -> Dict[str, List[Dict[str, Any]]]:
    repo_path = Path(repo_root)
    route_bindings: List[Dict[str, Any]] = []
    span_bindings: List[Dict[str, Any]] = []
    symbol_relations: List[Dict[str, Any]] = []
    queue_consumers: List[Dict[str, Any]] = []

    for file_path in repo_path.rglob("*.py"):
        if not file_path.is_file():
            continue
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue

        relative_path = str(file_path.relative_to(repo_path))
        imported_aliases: Dict[str, str] = {}
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imported_aliases[alias.asname or alias.name] = f"{module}.{alias.name}".strip(".")

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            symbol_name = node.name
            for call_name in _extract_function_calls(node):
                symbol_relations.append(
                    {
                        "source_symbol": symbol_name,
                        "source_file_path": relative_path,
                        "target_symbol": call_name,
                        "target_file_path": "",
                        "relation_type": "calls",
                        "confidence": 0.55,
                    }
                )

            for span in _extract_spans(node):
                span_bindings.append(
                    {
                        "span_name": span["span_name"],
                        "symbol_name": symbol_name,
                        "symbol_file_path": relative_path,
                        "line_start": getattr(node, "lineno", None),
                        "line_end": getattr(node, "end_lineno", None),
                        "confidence": 0.8,
                        "metadata": {"matched_by": "python_span_call"},
                    }
                )

            for task in _extract_tasks(node):
                queue_consumers.append(
                    {
                        "queue_name": task["queue_name"],
                        "handler_name": task["handler_name"],
                        "handler_file_path": relative_path,
                        "line_start": getattr(node, "lineno", None),
                        "line_end": getattr(node, "end_lineno", None),
                        "confidence": 0.75,
                    }
                )

            for decorator in getattr(node, "decorator_list", []):
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                    decorator_name = decorator.func.attr.lower()
                    if decorator_name in HTTP_METHOD_DECORATORS and decorator.args:
                        route = _get_constant_string(decorator.args[0])
                        if route:
                            route_bindings.append(
                                {
                                    "http_method": decorator_name.upper(),
                                    "route_pattern": route,
                                    "handler_name": symbol_name,
                                    "handler_file_path": relative_path,
                                    "line_start": getattr(node, "lineno", None),
                                    "line_end": getattr(node, "end_lineno", None),
                                    "confidence": 0.85,
                                    "metadata": {"matched_by": "python_http_decorator"},
                                }
                            )
                    elif decorator_name == "route" and decorator.args:
                        route = _get_constant_string(decorator.args[0])
                        methods = ["ANY"]
                        for keyword in decorator.keywords:
                            if keyword.arg == "methods" and isinstance(keyword.value, (ast.List, ast.Tuple)):
                                methods = [
                                    _get_constant_string(item).upper()
                                    for item in keyword.value.elts
                                    if _get_constant_string(item)
                                ] or ["ANY"]
                        if route:
                            for method in methods:
                                route_bindings.append(
                                    {
                                        "http_method": method,
                                        "route_pattern": route,
                                        "handler_name": symbol_name,
                                        "handler_file_path": relative_path,
                                        "line_start": getattr(node, "lineno", None),
                                        "line_end": getattr(node, "end_lineno", None),
                                        "confidence": 0.82,
                                        "metadata": {"matched_by": "python_route_decorator"},
                                    }
                                )

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in {"path", "re_path"} or len(node.args) < 2:
                continue
            route = _get_constant_string(node.args[0])
            handler_expr = node.args[1]
            handler_name = ""
            if isinstance(handler_expr, ast.Attribute):
                handler_name = _full_attr_name(handler_expr)
            elif isinstance(handler_expr, ast.Name):
                handler_name = imported_aliases.get(handler_expr.id, handler_expr.id)
            elif isinstance(handler_expr, ast.Call):
                handler_name = _call_name(handler_expr.func)
            if route and handler_name:
                route_bindings.append(
                    {
                        "http_method": "ANY",
                        "route_pattern": route,
                        "handler_name": handler_name,
                        "handler_file_path": relative_path,
                        "line_start": getattr(node, "lineno", None),
                        "line_end": getattr(node, "end_lineno", None),
                        "confidence": 0.7,
                        "metadata": {"matched_by": "django_urlpattern"},
                    }
                )

    return {
        "route_bindings": route_bindings,
        "span_bindings": span_bindings,
        "symbol_relations": symbol_relations,
        "queue_consumers": queue_consumers,
    }


def extract_route_hint_from_text(text: str) -> str:
    if not text:
        return ""
    matches = re.findall(r"(/[A-Za-z0-9_\-./{}:]+)", text)
    return matches[0] if matches else ""
