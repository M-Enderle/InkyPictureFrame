import random
import time

from immich import get_image_ids, download_image

from dotenv import load_dotenv
from inky.auto import auto

load_dotenv()
display = auto()

print(f"Detected Inky display: {display}")

def main():
    while True:
        image_ids = get_image_ids()
        random_id = random.choice(image_ids)
        file_path = download_image(random_id)
        if file_path:
            print(f"Displaying image {random_id} from {file_path}")
            display.set_image(file_path)
            display.show()
        else:
            print(f"Failed to download image {random_id}")
        time.sleep(30)


if __name__ == "__main__":
    main()