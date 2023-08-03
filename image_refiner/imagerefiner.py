import os
import nodes
import workflow_component.execution_experimental as ee
import nodes as comfy_nodes
import numpy as np
import torch
import folder_paths
from PIL import Image
import uuid
import comfy.model_management

def tensor2pil(image):
    return Image.fromarray(np.clip(255. * image.cpu().numpy().squeeze(), 0, 255).astype(np.uint8))


def image_to_latent(image):
    pass


loaded_checkpoints = {}


def unload_unused_checkpoints(ckpts):
    pass


def unload_all():
    global loaded_checkpoints
    loaded_checkpoints = {}
    comfy.model_management.unload_model()


def load_checkpoint(ckpt_name):
    global loaded_checkpoints
    if ckpt_name in loaded_checkpoints:
        model, clip, vae = loaded_checkpoints[ckpt_name]
    else:
        model, clip, vae, _ = comfy_nodes.CheckpointLoaderSimple().load_checkpoint(ckpt_name)
        loaded_checkpoints[ckpt_name] = model, clip, vae

    return model, clip, vae


def load_vae(vae_name):
    return comfy_nodes.VAELoader().load_vae(vae_name)[0]


def make_basic_pipe(model, clip, vae, positive, negative):
    positive = comfy_nodes.CLIPTextEncode().encode(clip, positive)[0]
    negative = comfy_nodes.CLIPTextEncode().encode(clip, negative)[0]
    return model, clip, vae, positive, negative


def prepare_input(class_def, merged_pil, mask_pil, prompt_data):
    input_data_all = {'extra_pnginfo': [{'workflow': {'nodes': []}}], 'unique_id': ['-1'], 'used_output_names': [set()]}

    for name, type in zip(list(class_def.RETURN_NAMES), list(class_def.RETURN_TYPES)):
        if type in ['IMAGE', 'LATENT']:
            input_data_all['used_output_names'][0].add(name)

    mask = np.array(mask_pil).astype(np.float32) / 255.0
    mask = 1. - torch.from_numpy(mask)

    # get annotated path
    image = np.array(merged_pil).astype(np.float32) / 255.0
    image = torch.from_numpy(image)[None, ]

    # unload unused checkpoints
    used_checkpoints = set()
    used_vae = set()
    for k, v in prompt_data.items():
        if 'type' not in v:
            continue

        ty = v['type']
        if ty in ['BASIC_PIPE', "MODEL", 'CONDITIONING']:
            used_checkpoints.add(v['checkpoint'])

        elif ty == "VAE":
            if 'checkpoint' in v:
                used_checkpoints.add(v['checkpoint'])
            else:
                used_vae.add(v['vae'])

    unload_unused_checkpoints(used_checkpoints)

    # load checkpoints
    for k, v in prompt_data.items():
        if 'type' not in v:
            continue

        ty = v['type']
        if ty == 'BASIC_PIPE':
            model, clip, vae = load_checkpoint(v['checkpoint'])
            basic_pipe = make_basic_pipe(model, clip, vae, v['positive'], v['negative'])
            input_data_all[k] = [basic_pipe]

        elif ty == "MODEL":
            model, _, _ = load_checkpoint(v['checkpoint'])
            input_data_all[k] = [model]

        elif ty == "VAE":
            if 'checkpoint' in v:
                _, _, vae = load_checkpoint(v['checkpoint'])
            else:
                vae = load_vae(v['vae'])

            input_data_all[k] = [vae]

        elif ty == "CONDITIONING":
            _, _, clip = load_checkpoint(v['checkpoint'])
            input_data_all[k] = [model]

        elif ty == "INT":
            input_data_all[k] = [int(v['value'])]

        elif ty == "FLOAT":
            input_data_all[k] = [float(v['value'])]

        elif ty == "STRING":
            input_data_all[k] = [v['value']]

        elif ty == "BOOLEAN":
            input_data_all[k] = [v['value']]

        elif ty == "COMBO":
            input_data_all[k] = [v['value']]

    # set image
    if 'IMAGE' in prompt_data['@IR_input_image']:
        input_data_all[prompt_data['@IR_input_image']['IMAGE']] = [image]
    else:
        input_data_all[prompt_data['@IR_input_image']['LATENT']] = [image_to_latent(image)]

    if '@IR_mask' in prompt_data:
        input_data_all[prompt_data['@IR_mask']] = [mask]

    return input_data_all


def process_output(class_def, output_data):
    l = list(zip(list(class_def.RETURN_NAMES), list(class_def.RETURN_TYPES)))

    output = None
    for i in range(len(l)):
        _, type = l[i]
        if type in ['IMAGE', 'LATENT']:
            output = output_data[i][0]
            break

    img_id = str(uuid.uuid4())
    filename = f"{img_id}.png"
    path = os.path.join(folder_paths.get_temp_directory(), "imagerefiner", filename)
    image_pil = tensor2pil(output)
    image_pil.save(path, optimize=True, compress_level=4)

    return {'filename': filename, 'type': 'temp', 'subfolder': 'imagerefiner'}


def generate(merged_pil, mask_pil, prompt_data):
    # create combo
    component_name = prompt_data['component_name']

    if component_name == "none":
        print(f"[WARN] Workflow-Component: there is no selected component")
        return None

    if component_name not in nodes.NODE_CLASS_MAPPINGS:
        print(f"[WARN] Workflow-Component: invalid component name '{component_name}'")
        return None 

    class_def = nodes.NODE_CLASS_MAPPINGS[component_name]

    input_data_all = prepare_input(class_def, merged_pil, mask_pil, prompt_data)
    output_data, _ = ee.get_output_data(class_def(), input_data_all)

    comfy.model_management.unload_model()

    # retrieve output
    return process_output(class_def, output_data)



