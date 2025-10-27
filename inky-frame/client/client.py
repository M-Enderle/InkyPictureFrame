from PIL import Image
from inky.auto import auto
import requests
import io

server_url = "https://nondemocratical-maple-linebred.ngrok-free.dev"
api_endpoint = f"{server_url}/current_image"

inky = auto(ask_user=True, verbose=True)

def fetch_and_display_image():
    response = requests.get(api_endpoint)
    response.raise_for_status()

    image_data = io.BytesIO(response.content)
    image = Image.open(image_data)

    inky.set_image(image)
    inky.show()

if __name__ == "__main__":
    fetch_and_display_image()