import argparse
import json
from pathlib import Path

from PIL import Image, ImageOps


def _clamp(value):
    return max(0, min(255, int(round(value))))


def _as_rgb(image):
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a PIL Image")
    return image.convert("RGB")


def load_image(path):
    try:
        return Image.open(path).convert("RGB")
    except Exception as exc:
        raise ValueError(f"cannot load image: {path}") from exc


def save_image(image, path):
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _as_rgb(image).save(output_path)
    return str(output_path)


def resize_image(image, scale):
    scale = float(scale)
    if scale <= 0:
        raise ValueError("scale must be greater than 0")
    source = _as_rgb(image)
    width, height = source.size
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return source.resize(new_size)


def rotate_image(image, angle):
    return _as_rgb(image).rotate(float(angle), expand=False)


def crop_image(image, left, top, right, bottom):
    source = _as_rgb(image)
    left, top, right, bottom = map(int, (left, top, right, bottom))
    width, height = source.size
    if left < 0 or top < 0 or right > width or bottom > height:
        raise ValueError("crop box must be inside image bounds")
    if right <= left or bottom <= top:
        raise ValueError("crop box must have positive width and height")
    return source.crop((left, top, right, bottom))


def invert_image(image):
    return ImageOps.invert(_as_rgb(image))


def blur_image(image):
    source = _as_rgb(image)
    output = source.copy()
    width, height = source.size
    pixels = source.load()
    out_pixels = output.load()
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            neighbors = [
                pixels[x + dx, y + dy]
                for dy in (-1, 0, 1)
                for dx in (-1, 0, 1)
            ]
            out_pixels[x, y] = tuple(
                _clamp(sum(pixel[channel] for pixel in neighbors) / 9)
                for channel in range(3)
            )
    return output


def edge_detect(image):
    source = _as_rgb(image)
    output = Image.new("RGB", source.size, (0, 0, 0))
    width, height = source.size
    pixels = source.load()
    out_pixels = output.load()
    kernel = [
        [-1, -1, -1],
        [-1, 8, -1],
        [-1, -1, -1],
    ]
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            channels = []
            for channel in range(3):
                total = 0
                for ky in range(3):
                    for kx in range(3):
                        px = pixels[x + kx - 1, y + ky - 1][channel]
                        total += px * kernel[ky][kx]
                channels.append(_clamp(abs(total)))
            out_pixels[x, y] = tuple(channels)
    return output


def median_filter(image, size=3):
    size = int(size)
    if size <= 0 or size % 2 == 0:
        raise ValueError("median filter size must be a positive odd integer")
    source = _as_rgb(image)
    output = source.copy()
    width, height = source.size
    radius = size // 2
    pixels = source.load()
    out_pixels = output.load()
    for y in range(radius, height - radius):
        for x in range(radius, width - radius):
            values = [[], [], []]
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    pixel = pixels[x + dx, y + dy]
                    for channel in range(3):
                        values[channel].append(pixel[channel])
            out_pixels[x, y] = tuple(
                sorted(channel_values)[len(channel_values) // 2]
                for channel_values in values
            )
    return output


def transform_image(input_path, output_path, operation, **kwargs):
    image = load_image(input_path)
    operation = str(operation).strip().lower()
    if operation == "resize":
        result = resize_image(image, kwargs.get("scale", 1))
    elif operation == "rotate":
        result = rotate_image(image, kwargs.get("angle", 0))
    elif operation == "crop":
        box = kwargs.get("box")
        if box is None:
            box = (
                kwargs.get("left"),
                kwargs.get("top"),
                kwargs.get("right"),
                kwargs.get("bottom"),
            )
        result = crop_image(image, *box)
    elif operation == "invert":
        result = invert_image(image)
    elif operation == "blur":
        result = blur_image(image)
    elif operation in {"edge", "edge_detect"}:
        result = edge_detect(image)
    elif operation in {"median", "median_filter"}:
        result = median_filter(image, kwargs.get("size", 3))
    else:
        raise ValueError(f"unknown operation: {operation}")
    return save_image(result, output_path)


def _parse_box(value):
    parts = [int(part.strip()) for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError("box must be left,top,right,bottom")
    return tuple(parts)


def build_parser():
    parser = argparse.ArgumentParser(description="ImageLab command line image transformer")
    parser.add_argument("input_path")
    parser.add_argument("output_path")
    parser.add_argument("operation")
    parser.add_argument("--scale", type=float, default=1)
    parser.add_argument("--angle", type=float, default=0)
    parser.add_argument("--box")
    parser.add_argument("--size", type=int, default=3)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        kwargs = {
            "scale": args.scale,
            "angle": args.angle,
            "box": _parse_box(args.box) if args.box else None,
            "size": args.size,
        }
        result = transform_image(args.input_path, args.output_path, args.operation, **kwargs)
        print(json.dumps({"output": result}, ensure_ascii=False))
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    main()
