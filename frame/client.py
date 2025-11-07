import random
import time

from immich import get_image_ids, download_image
from PIL import Image

from dotenv import load_dotenv
from inky.auto import auto

load_dotenv()
display = auto()

print(f"Detected Inky display: {display}")

def crop_image_to_display(image_path: str, display) -> str:
    resolution = display.resolution
    with Image.open(image_path) as img:
        img_ratio = img.width / img.height
        display_ratio = resolution[0] / resolution[1]

        if img_ratio > display_ratio:
            new_height = img.height
            new_width = int(new_height * display_ratio)
        else:
            new_width = img.width
            new_height = int(new_width / display_ratio)

        left = (img.width - new_width) / 2
        top = (img.height - new_height) / 2
        right = (img.width + new_width) / 2
        bottom = (img.height + new_height) / 2

        img_cropped = img.crop((left, top, right, bottom))
        img_resized = img_cropped.resize(resolution)

        return img_resized



def main():
    while True:
        image_ids = get_image_ids()
        random_id = random.choice(image_ids)
        file_path = download_image(random_id)
        if file_path:
            print(f"Displaying image {random_id} from {file_path}")
            cropped_image = crop_image_to_display(file_path, display)
            display.set_image(cropped_image)
            display.show()
        else:
            print(f"Failed to download image {random_id}")
        time.sleep(30)


if __name__ == "__main__":
    main()