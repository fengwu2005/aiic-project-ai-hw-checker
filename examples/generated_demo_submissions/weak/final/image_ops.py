from pathlib import Path
from PIL import Image, ImageOps


def load_image(path):
    return Image.open(path).convert("RGB")


def save_image(image, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return str(path)


def resize_image(image, scale):
    width, height = image.size
    return image.resize((int(width * float(scale)), int(height * float(scale))))


def rotate_image(image, angle):
    return image.rotate(float(angle))


def crop_image(image, left, top, right, bottom):
    return image.crop((left, top, right, bottom))


def invert_image(image):
    return ImageOps.invert(image.convert("RGB"))


def blur_image(image):
    return image


def edge_detect(image):
    return image


def median_filter(image, size=3):
    return image


def transform_image(input_path, output_path, operation, **kwargs):
    image = load_image(input_path)
    if operation == "invert":
        image = invert_image(image)
    save_image(image, output_path)
    return str(output_path)
