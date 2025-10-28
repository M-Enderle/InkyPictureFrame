from fastapi import FastAPI
from PIL import Image
import io
from starlette.responses import Response

app = FastAPI()

@app.get("/current_image")
async def get_current_image():
    # load test image
    image = Image.open("images/image.png")

    target_w, target_h = 800, 480
    w, h = image.size

    # scale image to cover target area while preserving aspect ratio (no stretching)
    scale = max(target_w / w, target_h / h)
    if scale != 1:
        new_size = (int(w * scale), int(h * scale))
        image = image.resize(new_size, Image.LANCZOS)

    # center-crop to target size
    left = (image.width - target_w) // 2
    top = (image.height - target_h) // 2
    right = left + target_w
    bottom = top + target_h
    image = image.crop((left, top, right, bottom))

    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    img_byte_arr = img_byte_arr.getvalue()
    return Response(content=img_byte_arr, media_type="image/png")