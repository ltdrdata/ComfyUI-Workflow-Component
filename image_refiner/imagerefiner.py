import os
import nodes
# import workflow_component.execution_experimental as ee
import execution
import nodes as comfy_nodes
import numpy as np
import torch
import folder_paths
from PIL import Image
import uuid
import comfy.model_management
from ..workflow_component import workflow_execution as we
from execution import PromptExecutor


ir_objs = {}


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
    comfy.model_management.cleanup_models()


def load_checkpoint(ckpt_name):
    global loaded_checkpoints
    if ckpt_name in loaded_checkpoints:
        model, clip, vae = loaded_checkpoints[ckpt_name]
    else:
        model, clip, vae = comfy_nodes.CheckpointLoaderSimple().load_checkpoint(ckpt_name)
        loaded_checkpoints[ckpt_name] = model, clip, vae

    return model, clip, vae


def load_vae(vae_name):
    return comfy_nodes.VAELoader().load_vae(vae_name)[0]


def make_basic_pipe(model, clip, vae, positive, negative):
    positive = comfy_nodes.CLIPTextEncode().encode(clip, positive)[0]
    negative = comfy_nodes.CLIPTextEncode().encode(clip, negative)[0]
    return model, clip, vae, positive, negative


class IR_Input_Provider:
    def __init__(self):
        self.data = {}
        self.image = None
        self.latent = None
        self.mask = None
        self.output_data = {}

    def add_input_image(self, value):
        self.image = value

    def add_input_latent(self, value):
        self.latent = value

    def add_input_mask(self, value):
        self.mask = value

    def add_input(self, key, value):
        self.data[key] = (value,)

    def add_input_mult(self, key, value):
        self.data[key] = value

    def get_input(self, key):
        return self.data[key]

    def add_output(self, slot, value):
        self.output_data[slot] = value

    def get_output(self, slot):
        return self.output_data[slot]

    def get_default_image_output(self):
        image = self.output_data[-1]
        image_json = nodes.PreviewImage().save_images(image, 'ImageRefiner/IR-GEN')['ui']
        return image_json


def prepare_prompt(class_def, component_name, merged_pil, mask_pil, prompt_id, prompt_data):
    global ir_objs

    next_id = 2
    prompt = {}
    ir_obj = IR_Input_Provider()
    ir_objs[prompt_id] = ir_obj

    # set input ----------------------------------------
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
    component_inputs = {}
    for k, v in prompt_data.items():
        if 'type' not in v:
            continue

        ty = v['type']
        if ty == 'BASIC_PIPE':
            model, clip, vae = load_checkpoint(v['checkpoint'])
            basic_pipe = make_basic_pipe(model, clip, vae, v['positive'], v['negative'])
            ir_obj.add_input_mult(k, basic_pipe)

        elif ty == "MODEL":
            model, _, _ = load_checkpoint(v['checkpoint'])
            ir_obj.add_input(k, model)

        elif ty == "VAE":
            if 'checkpoint' in v:
                _, _, vae = load_checkpoint(v['checkpoint'])
            else:
                vae = load_vae(v['vae'])
            ir_obj.add_input(k, vae)

        elif ty == "CONDITIONING":
            _, _, clip = load_checkpoint(v['checkpoint'])
            ir_obj.add_input(k, clip)

        elif ty == "INT":
            ir_obj.add_input(k, int(v['value']))

        elif ty == "FLOAT":
            ir_obj.add_input(k, float(v['value']))

        elif ty == "STRING":
            ir_obj.add_input(k, v['value'])

        elif ty == "BOOLEAN":
            ir_obj.add_input(k, v['value'])

        elif ty == "COMBO":
            ir_obj.add_input(k, v['value'])
        else:
            continue

        this_id = str(next_id)
        prompt[this_id] = {'class_type': '@IR_INPUT //WC', 'inputs': {'prompt_id': prompt_id, 'key': k}}
        component_inputs[k] = [this_id, 0]
        next_id += 1

    # set image
    if 'IMAGE' in prompt_data['@IR_input_image']:
        k = prompt_data['@IR_input_image']['IMAGE']

        ir_obj.add_input_image(image)
        this_id = str(next_id)
        prompt[this_id] = {'class_type': '@IR_INPUT //WC', 'inputs': {'prompt_id': prompt_id, 'key': k}}
        component_inputs[k] = [this_id, 0]

        next_id += 1

    else:
        k = prompt_data['@IR_input_image']['LATENT']

        ir_obj.add_input_latent(image_to_latent(image))
        this_id = str(next_id)
        prompt[this_id] = {'class_type': '@IR_INPUT //WC', 'inputs': {'prompt_id': prompt_id, 'key': k}}
        component_inputs[k] = [this_id, 0]

        next_id += 1

    if '@IR_mask' in prompt_data:
        k = prompt_data['@IR_mask']['MASK']

        ir_obj.add_input_mask(mask)
        this_id = str(next_id)
        prompt[this_id] = {'class_type': '@IR_INPUT //WC', 'inputs': {'prompt_id': prompt_id, 'key': k}}
        component_inputs[k] = [this_id, 0]

        next_id += 1

    # set output ----------------------------------------
    slot = 0
    for name, typ in zip(list(class_def.RETURN_NAMES), list(class_def.RETURN_TYPES)):
        if typ in ['IMAGE', 'LATENT']:
            prompt[str(next_id)] = {'class_type': '@IR_OUTPUT //WC', 'inputs': {'prompt_id': prompt_id, 'slot': -1, 'value': ['1', slot]}}
            next_id += 1
            slot += 1
            break

    # component

    prompt['1'] = {'class_type': component_name, 'inputs': component_inputs}

    return prompt


def process_output(return_id, output_data):
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
    prompt_id = str(uuid.uuid4())

    # create combo
    prompt = prompt_data['prompt']
    vsrv = we.VirtualServer( None, '1')
    pe = execution.PromptExecutor(vsrv)

    pe.execute(prompt, prompt_id)

    output_data = ir_objs[prompt_id].get_default_image_output()
    comfy.model_management.cleanup_models()

    # retrieve output
    return process_output(prompt_id, output_data)


class VirtualServer:
    def __init__(self,):
        pass

    def update_node_status(self, text, progress=None):
        pass

    def send_sync(self, event, data, sid=None):
        pass


executor = PromptExecutor(VirtualServer())


def execute_component(prompt, output_nodes):
    executor.execute(prompt, str(uuid.uuid4()), {}, output_nodes)
