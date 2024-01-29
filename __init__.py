import os
import folder_paths

print("### Loading: ComfyUI-Workflow-Component (V1.0) !! WARN: This is an experimental extension. Extremely unstable. !!")

comfy_path = os.path.dirname(folder_paths.__file__)
this_extension_path = os.path.dirname(__file__)

# DON'T REMOVE: load server APIs -------------
from .image_refiner import custom_server
# --------------------------------------------

from .image_refiner.ir_nodes import *

NODE_CLASS_MAPPINGS = {
    # "ExecutionSwitch": ExecutionSwitch,
    # "ComponentInput": ComponentInput,
    # "ComponentOutput": ComponentOutput,
    # "ExecutionControlString": ExecutionControlString,
    # "ExecutionOneOf": ExecutionOneOf,
    # "ComboToString": ComboToString,
    # "TensorToCPU": TensorToCPU,
    # "LoopControl": LoopControl,
    # "LoopCounterCondition": LoopCounterCondition,
    # "InputZip": InputZip,
    # "InputUnzip": InputUnzip,
    # "OptionalTest": OptionalTest,
    # "@IR_INPUT //WC": IR_Input,
    # "@IR_OUTPUT //WC": IR_Output,
}

NODE_DISPLAY_NAME_MAPPINGS = {}

WEB_DIRECTORY = "./js"
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', "WEB_DIRECTORY"]
