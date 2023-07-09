import os
import io
import json
from aiohttp import web
from PIL import Image, ImageOps
import zipfile
import datetime

import server
import folder_paths
import image_refiner.imagerefiner as ir


def get_path_from_fileitem(image):
    image_path = ""
    if 'subfolder' in image and image['subfolder'] != "":
        image_path = image['subfolder'] + "/"

    image_path += f"{image['filename']}"

    if not image_path.endswith('[input]') and not image_path.endswith('[temp]') and not image_path.endswith('[output]'):
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
        if 'is_mask_mode' not in x or x['is_mask_mode']:
            if x['id'] != 0:
                layer_mask = post.get(str(x['id']))
                layer_mask_pil = Image.open(layer_mask.file).convert('RGBA').getchannel('A')
                layer_mask_pil_inverted = ImageOps.invert(layer_mask_pil)
                image_pil = get_image_from_fileitem(x['image']).convert('RGBA')
                image_pil.putalpha(layer_mask_pil_inverted)
                images.append(image_pil)
            else:
                base_pil = get_image_from_fileitem(x['image']).convert('RGBA')
        else:
            layer_draw = post.get(str(x['id']))
            layer_draw_pil = Image.open(layer_draw.file).convert('RGBA')
            images.append(layer_draw_pil)

    for result_pil in images:
        base_pil = Image.alpha_composite(base_pil, result_pil)

    result = ir.generate(base_pil.convert('RGB'), mask_pil, prompt_data)

    return web.json_response(result, content_type='application/json')


@server.PromptServer.instance.routes.post("/imagerefiner/upload_archive")
async def imagerefiner_upload_archive(request):
    post = await request.post()

    zip_archive = post.get("file").file
    
    path = os.path.join(folder_paths.get_temp_directory(), "imagerefiner")
    
    with zipfile.ZipFile(zip_archive, 'r') as archive:
        archive.extractall(path)

    data_file_path = os.path.join(path, 'data.json')

    if os.path.exists(data_file_path):
        with open(data_file_path, 'r') as data_file:
            data = json.load(data_file)

        return web.json_response(data)
    else:
        return web.Response(status=400)


@server.PromptServer.instance.routes.post("/imagerefiner/get_archive")
async def imagerefiner_get_archive(request):
    post = await request.post()

    data = json.loads(post.get("data"))

    layers_data = data['layers_data']
    prompt_data = data['prompt_data']

    path = os.path.join(folder_paths.get_temp_directory(), "imagerefiner")

    if not os.path.exists(path):
        os.makedirs(path)

    image_dict = {}
    img_id = 0

    def get_normalized_image_path(image_path):
        nonlocal img_id
        nonlocal image_dict

        img_id += 1

        image_real_path = get_path_from_fileitem(image_path)

        if image_real_path in image_dict:
            return image_dict[image_real_path]
        else:
            normalized_name = f"ir-{img_id}.png"

            new_image_path = {
                'filename': normalized_name,
                'type': 'temp',
                'subfolder': 'imagerefiner'
            }

            image_dict[image_real_path] = new_image_path
            return new_image_path

    # normalize image paths
    prompt_data['base_image_path'] = get_normalized_image_path(prompt_data['base_image_path'])

    draws = []
    for layer in layers_data:
        if 'image' in layer:
            layer['image'] = get_normalized_image_path(layer['image'])

            new_cands = []
            for cand in layer['cands']:
                new_cands.append(get_normalized_image_path(cand))

            layer['cands'] = new_cands

            for value in layer['prompt_data']['image_paths']:
                if 'image' in value:
                    value['image'] = get_normalized_image_path(value['image'])

                if 'is_mask_mode' in value and not value['is_mask_mode']:
                    draws.append(f"draw_{value['id']}")

    # Create a zip file in memory
    zip_blob = io.BytesIO()
    with zipfile.ZipFile(zip_blob, 'w') as zf:
        # Archive layer images
        for real_path, image_name in image_dict.items():
            zf.writestr(image_name['filename'], open(real_path, 'rb').read())

        # Archive masks
        mask_pil = Image.open(post.get("mask").file).convert('RGBA')
        mask_filename = "mask_base.png"
        png_buffer = io.BytesIO()
        mask_pil.save(png_buffer, 'PNG')
        zf.writestr(mask_filename, png_buffer.getvalue())

        for value in draws:
            mask_pil = Image.open(post.get(value).file).convert('RGBA')
            mask_filename = f"{value}.png"
            png_buffer = io.BytesIO()
            mask_pil.save(png_buffer, 'PNG')
            zf.writestr(mask_filename, png_buffer.getvalue())

        # Archive layer masks
        for value in layers_data:
            layer_id = str(value['id'])
            layer_mask_pil = Image.open(post.get(layer_id).file).convert('RGBA')
            layer_mask_filename = f"mask_{layer_id}.png"
            png_buffer = io.BytesIO()
            layer_mask_pil.save(png_buffer, 'PNG')
            zf.writestr(layer_mask_filename, png_buffer.getvalue())

        # Save json data
        zf.writestr('data.json', json.dumps(data))

    zip_blob.seek(0)

    current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"imagerefiner_archive_{current_time}.imagerefiner"

    return web.Response(body=zip_blob.getvalue(), headers={"Content-Disposition": f"filename=\"{filename}\""})


@server.PromptServer.instance.routes.post("/imagerefiner/save")
async def imagerefiner_save(request):
    post = await request.post()

    save_info = json.loads(post.get("save_info"))

    images = []
    for x in save_info['image_paths']:
        if x['id'] != 0:
            mask = post.get(str(x['id']))
            mask_pil = Image.open(mask.file).convert('RGBA')

            if 'image' in x:
                mask_pil = mask_pil.getchannel('A')
                mask_pil_inverted = ImageOps.invert(mask_pil)
                image_pil = get_image_from_fileitem(x['image']).convert('RGBA')
                image_pil.putalpha(mask_pil_inverted)
            else:
                image_pil = mask_pil

            images.append(image_pil)
        else:
            base_pil = get_image_from_fileitem(x['image']).convert('RGBA')

    for result_pil in images:
        base_pil = Image.alpha_composite(base_pil, result_pil)

    image_path = get_path_from_fileitem(save_info['savepath'])

    if not os.path.exists(os.path.dirname(image_path)):
        os.makedirs(os.path.dirname(image_path))

    base_pil.save(image_path)

    ir.unload_all()

    return web.json_response({}, content_type='application/json')


@server.PromptServer.instance.routes.get("/imagerefiner/get_checkpoints")
async def imagerefiner_generate(request):
    result = {"checkpoints": folder_paths.get_filename_list("checkpoints")}
    return web.json_response(result, content_type='application/json')
