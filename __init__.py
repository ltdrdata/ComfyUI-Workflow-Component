import os
import sys
import folder_paths
import shutil

impact_path = os.path.dirname(__file__)
sys.path.append(impact_path)

from component_io_node import *
import component_loader

print("### Loading: ComfyUI-Workflow-Component (V0.1) !! WARN: This is an experimental extension. Extremely unstable. !!")

comfy_path = os.path.dirname(folder_paths.__file__)
this_extension_path = os.path.dirname(__file__)
js_path = os.path.join(comfy_path, "web", "extensions")

def setup_js():
    # setup js
    js_dest_path = os.path.join(js_path, "workflow-component")
    if not os.path.exists(js_dest_path):
        os.makedirs(js_dest_path)
    js_src_path = os.path.join(this_extension_path, "js", "workflow-component.js")
    shutil.copy(js_src_path, js_dest_path)

setup_js()

NODE_CLASS_MAPPINGS = {
    "ComponentInputImage": ComponentInputImage,
    "ComponentInputModel": ComponentInputModel,
    "ComponentInputClip": ComponentInputClip,
    "ComponentInputVAE": ComponentInputVAE,

    "ComponentInputString": ComponentInputString,
    "ComponentInputFloat": ComponentInputFloat,
    "ComponentInputInt": ComponentInputInt,

    "ComponentOutputImage": ComponentOutputImage,
    "ComponentOutputLatent": ComponentOutputLatent,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ComponentInputImage": "ComponentInput (Image)",
    "ComponentOutputImage": "ComponentOutput (Image)",
}


component_loader.load_all()
NODE_CLASS_MAPPINGS.update(component_loader.NODE_CLASS_MAPPINGS)

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
