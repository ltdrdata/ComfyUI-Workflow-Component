import os
import sys
import folder_paths
import shutil

extension_path = os.path.dirname(__file__)
sys.path.append(extension_path)

import workflow_component.component_loader as component_loader

print("### Loading: ComfyUI-Workflow-Component (V0.27) !! WARN: This is an experimental extension. Extremely unstable. !!")

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

    js_src_path = os.path.join(this_extension_path, "js", "image-refiner.js")
    shutil.copy(js_src_path, js_dest_path)

setup_js()


# DON'T REMOVE: load server apis -------------
import image_refiner.custom_server
import workflow_component.custom_server
# --------------------------------------------

from workflow_component.custom_nodes import *

NODE_CLASS_MAPPINGS = {
    "ExecutionSwitch": ExecutionSwitch,
    "ExecutionBlocker": ExecutionBlocker,
    "ExecutionControlString": ExecutionControlString,
    "ExecutionOneOf": ExecutionOneOf,
    "ComboToString": ComboToString,
    "TensorToCPU": TensorToCPU,
    "LoopControl": LoopControl,
    "LoopCounterCondition": LoopCounterCondition,
    "InputZip": InputZip,
    "InputUnzip": InputUnzip,
}

NODE_DISPLAY_NAME_MAPPINGS = {
}

directory = os.path.join(os.path.dirname(__file__), "components")

component_loader.load_all(directory)
NODE_CLASS_MAPPINGS.update(component_loader.NODE_CLASS_MAPPINGS)

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']