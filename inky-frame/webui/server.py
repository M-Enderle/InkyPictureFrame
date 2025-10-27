from fastapi import FastAPI
from PIL import Image
import io
from starlette.responses import Response

app = FastAPI()

@app.get("/current_image")
async def get_current_image():

    # load test image
    image = Image.open("images/test_image.png")
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    img_byte_arr = img_byte_arr.getvalue()
    return Response(content=img_byte_arr, media_type="image/png")