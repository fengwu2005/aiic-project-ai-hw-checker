from PIL import Image


def load_image(path):
    return Image.open(path)


def save_image(image, path):
    image.save(path)
    return path


def resize_image(image, scale):
    return image.resize((1, 1))


def rotate_image(image, angle):
    return image


def crop_image(image, left, top, right, bottom):
    return image

# Missing invert_image, blur_image, edge_detect, median_filter and transform_image.
