from io import BytesIO
from PIL import Image
import pytest
from nohtus.services.product_images import product_jpeg_preview


@pytest.mark.parametrize("size", [(1600,1000),(200,300),(800,800)])
def test_preview_download_is_800px_jpeg_and_preserves_source(tmp_path,size):
    original=tmp_path/"source.png"
    Image.new("RGBA",size,(255,0,0,0)).save(original)
    before=original.read_bytes()
    result=product_jpeg_preview(original)
    with Image.open(BytesIO(result)) as image:
        assert image.format=="JPEG"
        assert image.size==(800,round(size[1]*800/size[0]))
        assert image.mode=="RGB"
        assert min(image.getpixel((0,0)))>=250
    assert original.read_bytes()==before


def test_jpg_url_returns_800px_image_and_jpg_filename(tmp_path):
    from streamlit.runtime.memory_media_file_storage import MemoryMediaFileStorage
    from streamlit.runtime.media_file_storage import MediaFileKind
    from streamlit.web.server.starlette.starlette_routes import create_media_routes
    import asyncio
    from starlette.requests import Request
    original=tmp_path/"source.png"
    Image.new("RGB",(1200,600),"white").save(original)
    data=product_jpeg_preview(original)
    storage=MemoryMediaFileStorage("/media")
    id=storage.load_and_get_id(data,"image/jpeg",MediaFileKind.DOWNLOADABLE,"product.jpg")
    route=next(route for route in create_media_routes(storage, "") if "GET" in route.methods)
    request=Request({"type":"http","method":"GET","path_params":{"file_id":f"{id}.jpg"},"headers":[]})
    response=asyncio.run(route.endpoint(request))
    assert response.status_code==200
    assert response.headers["content-type"]=="image/jpeg"
    assert 'filename="product.jpg"' in response.headers["content-disposition"]
    with Image.open(BytesIO(response.body)) as image:
        assert image.size==(800,400)
