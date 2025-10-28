from PIL import Image
from inky.auto import auto
import requests
import io
import time
import hashlib

server_url = "https://nondemocratical-maple-linebred.ngrok-free.dev"
api_endpoint = f"{server_url}/current_image"

inky = auto(ask_user=True, verbose=True)

def fetch_and_display_image():
    previous_hash = None
    while True:
        response = requests.get(api_endpoint)
        response.raise_for_status()

        image_data = io.BytesIO(response.content)
        image = Image.open(image_data)

        # Compute hash of the image
        current_hash = hashlib.md5(image.tobytes()).hexdigest()

        if current_hash != previous_hash:
            # Save the image as PNG
            image.save("current_image.png")
            # Display on Inky
            inky.set_image(image)
            inky.show()
            previous_hash = current_hash

        time.sleep(30)

if __name__ == "__main__":
    fetch_and_display_image()