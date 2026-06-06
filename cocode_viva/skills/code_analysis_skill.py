from __future__ import annotations

import ast
def analyze_code(source: str) -> dict:
    result = {
        "line_count": len([line for line in source.splitlines() if line.strip()]),
        "functions": [],
        "classes": [],
        "imports": [],
        "syntax_ok": True,
        "syntax_error": "",
        "features": {},
    }

    try:
        tree = ast.parse(source or "\n")
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                result["functions"].append(node.name)
            elif isinstance(node, ast.ClassDef):
                result["classes"].append(node.name)
            elif isinstance(node, ast.Import):
                result["imports"].extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                result["imports"].append(node.module)
    except SyntaxError as exc:
        result["syntax_ok"] = False
        result["syntax_error"] = f"第 {exc.lineno} 行：{exc.msg}"

    lowered = source.lower()
    result["features"] = {
        "image_io": "image.open" in lowered or "pil" in lowered or "save(" in lowered,
        "cli_interface": "argparse" in lowered or "click" in lowered or "sys.argv" in lowered,
        "resize": "resize" in lowered or "scale" in lowered or "thumbnail" in lowered or "放大" in lowered or "缩小" in lowered,
        "rotate": "rotate" in lowered or "旋转" in lowered,
        "crop": "crop" in lowered or "剪切" in lowered or "裁剪" in lowered,
        "invert": "invert" in lowered or "255 -" in lowered or "反色" in lowered,
        "blur": "blur" in lowered or "mean" in lowered or "average" in lowered or "模糊" in lowered,
        "edge_detection": "edge" in lowered or "kernel" in lowered or "convolution" in lowered or "卷积" in lowered or "边缘" in lowered,
        "median_filter": "median" in lowered or "中值" in lowered,
        "pixel_access": "getpixel" in lowered or "putpixel" in lowered or "load()" in lowered,
        "parameter_validation": "valueerror" in lowered or "raise" in lowered or "validate" in lowered,
        "error_handling": "try:" in lowered and "except" in lowered,
    }

    return result
