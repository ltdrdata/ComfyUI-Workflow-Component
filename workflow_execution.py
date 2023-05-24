import execution
from execution_experimental import *
import json
import zlib
import torch

class VirtualServer:
    def __init__(self):
        self.client_id = None

    def send_sync(self):
        pass


vs = VirtualServer()
executor_dict = {}


def get_executor(node_id):
    if not node_id in executor_dict:
        executor_dict[node_id] = ExpPromptExecutor(vs)

    return executor_dict[node_id]


virtual_prompt_id = 0
def get_virtual_prompt_id():
    global virtual_prompt_id
    virtual_prompt_id += 1
    return virtual_prompt_id


def execute(prompt, workflow, input_mapping, output_mapping, *args, **kwargs):
    node_id = kwargs['unique_id']
    pe = get_executor(node_id)

    for key, value in kwargs.items():
        if key not in ["unique_id", "prompt", "extra_pnginfo"]:
            input_node = input_mapping[key]
            input_node_id = str(input_node['id'])

            pe.outputs[input_node_id] = [[value]]  # TODO: check

            pe.old_prompt[input_node_id] = prompt[input_node_id]  # prevent erasing of output cache

    prompt_id = get_virtual_prompt_id()

    execute_outputs = []
    for key in output_mapping:
        _, output_node = output_mapping[key]
        output_node_id = str(output_node['id'])
        execute_outputs.append(output_node_id)

    # this must be calculated on-demand due to custom node loading order
    for node in workflow['nodes']:
        class_type = node['type']
        class_def = nodes.NODE_CLASS_MAPPINGS[class_type]
        if hasattr(class_def, "OUTPUT_NODE") and class_def.OUTPUT_NODE:
            execute_outputs.append(node['id'])

    pe.execute(prompt, prompt_id, workflow, execute_outputs=execute_outputs)

    results = []
    for key in output_mapping:
        order, output_node = output_mapping[key]
        output_node_id = str(output_node['id'])
        inputs = prompt[output_node_id]['inputs']

        class_type = output_node['type']
        class_def = nodes.NODE_CLASS_MAPPINGS[class_type]

        input_data_all = get_input_data(inputs, class_def, output_node_id, pe.outputs, prompt, workflow)
        _, value = next(iter(input_data_all.items()))

        unboxed_value = value[0]  # TODO: check
        results.append((order, unboxed_value))

    results.sort(key=lambda x: x[0])

    return tuple(value for order, value in results)
