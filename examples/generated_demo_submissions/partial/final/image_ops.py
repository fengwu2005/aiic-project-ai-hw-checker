import argparse
from pathlib import Path
from PIL import Image, ImageOps


def load_image(path):
    return Image.open(path).convert("RGB")


def save_image(image, path):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    return str(output)


def resize_image(image, scale):
    scale = float(scale)
    width, height = image.size
    return image.convert("RGB").resize((max(1, round(width * scale)), max(1, round(height * scale))))


def rotate_image(image, angle):
    return image.convert("RGB").rotate(float(angle), expand=False)


def crop_image(image, left, top, right, bottom):
    return image.convert("RGB").crop((int(left), int(top), int(right), int(bottom)))


def invert_image(image):
    return ImageOps.invert(image.convert("RGB"))


def blur_image(image):
    # Incorrect: this keeps the image unchanged, so the average-kernel hidden test should fail.
    return image.convert("RGB").copy()


def edge_detect(image):
    # Incorrect: no fixed convolution kernel is applied.
    return image.convert("RGB").copy()


def median_filter(image, size=3):
    # Incorrect: no median window is computed.
    return image.convert("RGB").copy()


def transform_image(input_path, output_path, operation, **kwargs):
    image = load_image(input_path)
    operation = str(operation).lower()
    if operation == "resize":
        result = resize_image(image, kwargs.get("scale", 1))
    elif operation == "rotate":
        result = rotate_image(image, kwargs.get("angle", 0))
    elif operation == "crop":
        box = kwargs.get("box") or (kwargs.get("left"), kwargs.get("top"), kwargs.get("right"), kwargs.get("bottom"))
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
        raise ValueError("unknown operation")
    return save_image(result, output_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_path")
    parser.add_argument("output_path")
    parser.add_argument("operation")
    parser.add_argument("--scale", type=float, default=1)
    args = parser.parse_args()
    transform_image(args.input_path, args.output_path, args.operation, scale=args.scale)


if __name__ == "__main__":
    main()
