import os
import server
from aiohttp import web
import json
from PIL import Image

import folder_paths
import image_refiner.imagerefiner as ir
from PIL import ImageOps


def get_path_from_fileitem(image):
    image_path = ""
    if 'subfolder' in image and image['subfolder'] != "":
        image_path = image['subfolder'] + "/"

    image_path += f"{image['filename']}"

    if 'type' in image and image['type'] != "":
        image_path += f" [{image['type']}]"

    image_path = folder_paths.get_annotated_filepath(image_path)

    return image_path


def get_image_from_fileitem(image):
    image_path = get_path_from_fileitem(image)
    return Image.open(image_path)


@server.PromptServer.instance.routes.post("/imagerefiner/generate")
async def imagerefiner_generate(request):
    post = await request.post()

    mask = post.get("mask")
    prompt_data = json.loads(post.get("prompt_data"))
    mask_pil = Image.open(mask.file).convert('RGBA').getchannel('A')

    path = os.path.join(folder_paths.get_temp_directory(), "imagerefiner")

    if not os.path.exists(path):
        os.makedirs(path)

    # prepare input image
    images = []
    for x in prompt_data['image_paths']:
        if x['id'] != 0:
            if x['is_mask_mode']:
                layer_mask = post.get(str(x['id']))
                layer_mask_pil = Image.open(layer_mask.file).convert('RGBA').getchannel('A')
                layer_mask_pil_inverted = ImageOps.invert(layer_mask_pil)
                image_pil = get_image_from_fileitem(x['image']).convert('RGBA')
                image_pil.putalpha(layer_mask_pil_inverted)
                images.append(image_pil)
            else:
                layer_draw = post.get(str(x['id']))
                layer_draw_pil = Image.open(layer_draw.file).convert('RGBA')
                images.append(layer_draw_pil)
        else:
            base_pil = get_image_from_fileitem(x['image']).convert('RGBA')

    for result_pil in images:
        base_pil = Image.alpha_composite(base_pil, result_pil)

    result = ir.generate(base_pil.convert('RGB'), mask_pil, prompt_data)

    return web.json_response(result, content_type='application/json')


@server.PromptServer.instance.routes.post("/imagerefiner/save")
async def imagerefiner_save(request):
    post = await request.post()

    save_info = json.loads(post.get("save_info"))

    images = []
    for x in save_info['image_paths']:
        if x['id'] != 0:
            mask = post.get(str(x['id']))
            mask_pil = Image.open(mask.file).convert('RGBA').getchannel('A')
            mask_pil_inverted = ImageOps.invert(mask_pil)
            image_pil = get_image_from_fileitem(x['image']).convert('RGBA')
            image_pil.putalpha(mask_pil_inverted)
            images.append(image_pil)
        else:
            base_pil = get_image_from_fileitem(x['image']).convert('RGBA')

    for result_pil in images:
        base_pil = Image.alpha_composite(base_pil, result_pil)

    base_pil.save(get_path_from_fileitem(save_info['savepath']))

    ir.unload_all()

    return web.json_response({}, content_type='application/json')


@server.PromptServer.instance.routes.get("/imagerefiner/get_checkpoints")
async def imagerefiner_generate(request):
    result = {"checkpoints": folder_paths.get_filename_list("checkpoints")}
    return web.json_response(result, content_type='application/json')
