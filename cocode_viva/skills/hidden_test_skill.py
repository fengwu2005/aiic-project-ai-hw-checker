from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


TIMEOUT_SECONDS = 8


def run_hidden_tests(extract_dir: Path) -> dict:
    """Run deterministic instructor checks against final/image_ops.py in a subprocess."""
    source_path = _find_final_code(extract_dir)
    if not source_path.exists():
        return {
            "enabled": True,
            "passed": 0,
            "total": 1,
            "pass_rate": 0,
            "status": "failed",
            "cases": [{"name": "final/image_ops.py exists", "ok": False, "detail": "file not found"}],
            "error": "final/image_ops.py not found",
        }

    with tempfile.TemporaryDirectory(prefix="imagelab_hidden_") as temp_dir:
        runner = Path(temp_dir) / "hidden_runner.py"
        runner.write_text(_runner_script(source_path), encoding="utf-8")
        try:
            completed = subprocess.run(
                [sys.executable, str(runner)],
                cwd=temp_dir,
                text=True,
                capture_output=True,
                timeout=TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "enabled": True,
                "passed": 0,
                "total": 1,
                "pass_rate": 0,
                "status": "timeout",
                "cases": [{"name": "hidden test timeout", "ok": False, "detail": f">{TIMEOUT_SECONDS}s"}],
                "error": "student code timed out during hidden tests",
            }

    output = completed.stdout.strip().splitlines()
    marker_lines = [line for line in output if line.startswith("__HIDDEN_TEST_RESULT__")]
    if not marker_lines:
        return {
            "enabled": True,
            "passed": 0,
            "total": 1,
            "pass_rate": 0,
            "status": "failed",
            "cases": [{"name": "hidden runner output", "ok": False, "detail": completed.stderr[-800:] or completed.stdout[-800:]}],
            "error": "hidden runner did not return structured result",
        }

    try:
        result = json.loads(marker_lines[-1].replace("__HIDDEN_TEST_RESULT__", "", 1))
    except json.JSONDecodeError as exc:
        return {
            "enabled": True,
            "passed": 0,
            "total": 1,
            "pass_rate": 0,
            "status": "failed",
            "cases": [{"name": "hidden runner json", "ok": False, "detail": str(exc)}],
            "error": "hidden runner returned invalid JSON",
        }

    result["enabled"] = True
    result["returncode"] = completed.returncode
    if completed.stderr:
        result["stderr_tail"] = completed.stderr[-1200:]
    return result


def _runner_script(source_path: Path) -> str:
    source = json.dumps(str(source_path))
    return textwrap.dedent(f"""
        import importlib.util
        import json
        from pathlib import Path

        from PIL import Image

        RESULT = {{"cases": []}}

        def record(name, ok, detail=""):
            RESULT["cases"].append({{"name": name, "ok": bool(ok), "detail": str(detail)[:500]}})

        def require(condition, message="assertion failed"):
            if not condition:
                raise AssertionError(message)

        def rgb(pixel):
            if isinstance(pixel, int):
                return (pixel, pixel, pixel)
            return tuple(pixel[:3])

        def close_tuple(actual, expected, tolerance=3):
            actual = rgb(actual)
            expected = rgb(expected)
            return all(abs(a - e) <= tolerance for a, e in zip(actual, expected))

        try:
            spec = importlib.util.spec_from_file_location("student_image_ops", {source})
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            record("import final/image_ops.py", True)
        except Exception as exc:
            record("import final/image_ops.py", False, repr(exc))
            module = None

        required_functions = [
            "load_image", "save_image", "resize_image", "rotate_image", "crop_image",
            "invert_image", "blur_image", "edge_detect", "median_filter", "transform_image",
        ]

        if module is not None:
            try:
                missing = [name for name in required_functions if not callable(getattr(module, name, None))]
                require(not missing, "missing functions: " + ", ".join(missing))
                record("required image function API", True)
            except Exception as exc:
                record("required image function API", False, repr(exc))

            base = Image.new("RGB", (4, 4))
            values = [
                [(0, 0, 0), (40, 0, 0), (80, 0, 0), (120, 0, 0)],
                [(0, 40, 0), (40, 40, 40), (80, 40, 40), (120, 40, 40)],
                [(0, 80, 0), (40, 80, 40), (80, 80, 80), (120, 80, 80)],
                [(0, 120, 0), (40, 120, 40), (80, 120, 80), (120, 120, 120)],
            ]
            for y, row in enumerate(values):
                for x, value in enumerate(row):
                    base.putpixel((x, y), value)

            try:
                input_path = Path("input.png")
                output_path = Path("output.png")
                base.save(input_path)
                loaded = module.load_image(input_path)
                require(getattr(loaded, "size", None) == (4, 4), "load_image should return image with original size")
                saved_path = module.save_image(loaded, output_path)
                require(output_path.exists(), "save_image should write output file")
                record("load_image and save_image", True)
            except Exception as exc:
                record("load_image and save_image", False, repr(exc))

            try:
                up = module.resize_image(base, scale=2)
                down = module.resize_image(base, scale=0.5)
                require(up.size == (8, 8), "scale=2 should produce 8x8 image")
                require(down.size == (2, 2), "scale=0.5 should produce 2x2 image")
                record("resize enlarge and shrink", True)
            except Exception as exc:
                record("resize enlarge and shrink", False, repr(exc))

            try:
                rotated = module.rotate_image(base, 90)
                require(rotated.size in {{(4, 4), (4, 4)}}, "90 degree rotation should preserve square size")
                require(close_tuple(rotated.getpixel((0, 0)), base.getpixel((3, 0))) or close_tuple(rotated.getpixel((0, 0)), base.getpixel((0, 3))), "rotation should move pixels")
                record("rotate_image", True)
            except Exception as exc:
                record("rotate_image", False, repr(exc))

            try:
                cropped = module.crop_image(base, 1, 1, 3, 3)
                require(cropped.size == (2, 2), "crop should return selected region size")
                require(close_tuple(cropped.getpixel((0, 0)), base.getpixel((1, 1))), "crop top-left pixel mismatch")
                record("crop_image", True)
            except Exception as exc:
                record("crop_image", False, repr(exc))

            try:
                inverted = module.invert_image(base)
                require(close_tuple(inverted.getpixel((0, 0)), (255, 255, 255)), "black should invert to white")
                require(close_tuple(inverted.getpixel((1, 1)), (215, 215, 215)), "gray pixel inversion mismatch")
                record("invert_image", True)
            except Exception as exc:
                record("invert_image", False, repr(exc))

            try:
                impulse = Image.new("RGB", (5, 5), (0, 0, 0))
                impulse.putpixel((2, 2), (255, 255, 255))
                blurred = module.blur_image(impulse)
                center = rgb(blurred.getpixel((2, 2)))[0]
                require(20 <= center <= 40, f"3x3 average blur center should be about 28, got {{center}}")
                record("blur_image average kernel", True)
            except Exception as exc:
                record("blur_image average kernel", False, repr(exc))

            try:
                edge_source = Image.new("RGB", (5, 5), (0, 0, 0))
                for y in range(5):
                    for x in range(3, 5):
                        edge_source.putpixel((x, y), (255, 255, 255))
                edged = module.edge_detect(edge_source)
                edge_value = max(rgb(edged.getpixel((2, 2))))
                flat_value = max(rgb(edged.getpixel((0, 2))))
                require(edge_value > flat_value, "edge pixel should be stronger than flat area")
                record("edge_detect fixed convolution", True)
            except Exception as exc:
                record("edge_detect fixed convolution", False, repr(exc))

            try:
                noisy = Image.new("RGB", (5, 5), (30, 30, 30))
                noisy.putpixel((2, 2), (255, 255, 255))
                filtered = module.median_filter(noisy, size=3)
                require(close_tuple(filtered.getpixel((2, 2)), (30, 30, 30)), "median filter should remove isolated bright noise")
                record("median_filter", True)
            except Exception as exc:
                record("median_filter", False, repr(exc))

            try:
                transformed_path = Path("transformed.png")
                result = module.transform_image(input_path, transformed_path, "invert")
                require(transformed_path.exists(), "transform_image should write output")
                transformed = Image.open(transformed_path).convert("RGB")
                require(close_tuple(transformed.getpixel((0, 0)), (255, 255, 255)), "transform_image invert failed")
                record("transform_image dispatcher", True)
            except Exception as exc:
                record("transform_image dispatcher", False, repr(exc))

            try:
                try:
                    module.resize_image(base, scale=0)
                    raise AssertionError("scale=0 should fail")
                except Exception:
                    pass
                try:
                    module.crop_image(base, 3, 3, 1, 1)
                    raise AssertionError("invalid crop box should fail")
                except Exception:
                    pass
                record("parameter validation", True)
            except Exception as exc:
                record("parameter validation", False, repr(exc))

        passed = sum(1 for case in RESULT["cases"] if case["ok"])
        total = len(RESULT["cases"]) or 1
        RESULT.update({{
            "passed": passed,
            "total": total,
            "pass_rate": round(passed / total, 3),
            "status": "passed" if passed == total else "partial" if passed else "failed",
        }})
        print("__HIDDEN_TEST_RESULT__" + json.dumps(RESULT, ensure_ascii=False))
    """)


def _find_final_code(extract_dir: Path) -> Path:
    direct = (extract_dir / "final" / "image_ops.py").resolve()
    if direct.exists():
        return direct
    matches = sorted(extract_dir.glob("*/final/image_ops.py"))
    if matches:
        return matches[0].resolve()
    return direct
