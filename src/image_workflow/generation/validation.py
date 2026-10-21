"""Technical response checks only: no persistence, Pass or visual acceptance.

ValueError distinguishes response shape/dimensions; base64 and Pillow retain
their native decode/format exception types. The service records those unchanged.
"""

import base64
import io

from PIL import Image


def decode_response(response):
    if not response.data or len(response.data) != 1 or not response.data[0].b64_json:
        raise ValueError('接口未返回预期的一张图片，已保留实际响应。')
    return base64.b64decode(response.data[0].b64_json, validate=True)


def validate_image(data, size):
    with Image.open(io.BytesIO(data)) as image:
        if image.format != 'PNG' or image.size != tuple(map(int, size.split('x'))):
            raise ValueError('返回图片的格式或尺寸与请求不符，已保留返回字节。')
        image.verify()
    with Image.open(io.BytesIO(data)) as image:
        image.load()
