import os
import sys
import folder_paths
import shutil

impact_path = os.path.dirname(__file__)
sys.path.append(impact_path)

import component_loader

print("### Loading: ComfyUI-Workflow-Component (V0.22) !! WARN: This is an experimental extension. Extremely unstable. !!")

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

import server
from aiohttp import web

import uuid
import workflow_execution
import execution_experimental


async def original_post_prompt(request):
    self = server.PromptServer.instance

    print("got prompt")
    resp_code = 200
    out_string = ""
    json_data = await request.json()

    if "number" in json_data:
        number = float(json_data['number'])
    else:
        number = self.number
        if "front" in json_data:
            if json_data['front']:
                number = -number

        self.number += 1

    if "prompt" in json_data:
        prompt = json_data["prompt"]
        valid = execution_experimental.validate_prompt(prompt)
        extra_data = {}
        if "extra_data" in json_data:
            extra_data = json_data["extra_data"]

        if "client_id" in json_data:
            extra_data["client_id"] = json_data["client_id"]
        if valid[0]:
            prompt_id = str(uuid.uuid4())
            outputs_to_execute = valid[2]
            self.prompt_queue.put((number, prompt_id, prompt, extra_data, outputs_to_execute))
            return web.json_response({"prompt_id": prompt_id})
        else:
            print("invalid prompt:", valid[1])
            return web.json_response({"error": valid[1], "node_errors": valid[3]}, status=400)
    else:
        return web.json_response({"error": "no prompt", "node_errors": []}, status=400)


@server.PromptServer.instance.routes.post("/prompt")
async def prompt_hook(request):
    json_data = await request.json()

    nodes = json_data['extra_data']['extra_pnginfo']['workflow']['nodes']
    if any(node['type'] in ["ComponentInput", "ComponentOutput", "ComponentOptional"] for node in nodes):
        msg = "<B>The Workflow Component being composed is not executable.</B><BR><BR>If ComponentInput, ComponentInputOptional, or ComponentOutput nodes are used, it is considered that the Component being composed is in progress."
        return web.json_response({"error": {"message": msg}, "node_errors": {}}, status=400)

    component_loader.resolve_unresolved_map()
    if len(component_loader.unresolved_map) > 0:
        unresolved_nodes = set()
        for node in nodes:
            if node['type'] in component_loader.unresolved_map:
                unresolved_nodes.update(component_loader.unresolved_map[node['type']])

        # excludes
        unresolved_nodes -= set(['Reroute'])

        if len(unresolved_nodes) > 0:
            msg = f"<B>Non-installed custom nodes are being used within the component.</B><BR><BR>{unresolved_nodes}"
            return web.json_response({"error": {"message": msg}, "node_errors": {}}, status=400)

    if "prompt" in json_data:
        prompt = json_data["prompt"]
        workflow_execution.garbage_collect(prompt.keys())

    return await original_post_prompt(request)


server.PromptServer.instance.app.router.add_post('/prompt', prompt_hook)


import json
@server.PromptServer.instance.routes.post("/component/load")
async def load_component(request):
    post = await request.post()
    component_name = post.get("component_or_filename")
    json_text = post.get("content")
    workflow = json.loads(json_text)

    is_full_name = False
    if component_name.endswith('.component.json'):
        component_name = os.path.basename(component_name)[:-15]
    else:
        is_full_name = True

    new_created, component_full_name = component_loader.load_component(component_name, is_full_name, workflow, True)

    result = {'node_name': component_full_name,
              "already_loaded": not new_created}

    return web.json_response(result, content_type='application/json')


@server.PromptServer.instance.routes.get("/component/get_workflows")
async def get_workflows(request):
    return web.json_response(component_loader.workflow_components, content_type='application/json')


@server.PromptServer.instance.routes.get("/component/get_unresolved")
async def get_unresolved(request):
    component_loader.resolve_unresolved_map()

    unresolved_nodes = set()
    for nodes in component_loader.unresolved_map.values():
        unresolved_nodes.update(nodes)

    return web.json_response({'nodes': list(unresolved_nodes)}, content_type='application/json')


class ExecutionBlocker:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
                        "input": ("*", ),
                        "signal": ("*", ),
                     },
                }

    RETURN_TYPES = ("*", )
    FUNCTION = "doit"

    def doit(s, input, signal):
        return input


class ExecutionSwitch:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
                        "select": ("INT", {"default": 1, "min": 0, "max": 5}),
                        "input1": ("*", ),
                    },
                "optional": {
                        "input2_opt": ("*", ),
                        "input3_opt": ("*", ),
                        "input4_opt": ("*", ),
                        "input5_opt": ("*", ),
                    }
                }

    RETURN_TYPES = ("*", "*", "*", "*", "*", )
    FUNCTION = "doit"

    def doit(s, select, input1, input2_opt=None, input3_opt=None, input4_opt=None, input5_opt=None):
        if select == 1:
            return input1, None, None, None, None
        elif select == 2:
            return None, input2_opt, None, None, None
        elif select == 3:
            return None, None, input3_opt, None, None
        elif select == 4:
            return None, None, None, input4_opt, None
        elif select == 5:
            return None, None, None, None, input5_opt
        else:
            return None, None, None, None, None


class LoopControl:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
                        "loop_condition": ("LOOP_CONDITION", ),
                        "initial_input": ("*", ),
                        "loopback_input": ("*", ),
                    },
                }

    RETURN_TYPES = ("*", )
    FUNCTION = "doit"

    def doit(s, **kwargs):
        if 'loopback_input' not in kwargs or kwargs['loopback_input'] is None:
            current = kwargs['initial_input']
        else:
            current = kwargs['loopback_input']

        return (kwargs['loop_condition'].get_next(kwargs['initial_input'], current), )


class CounterCondition:
    def __init__(self, value):
        self.max = value
        self.current = 0

    def get_next(self, initial_value, value):
        print(f"CounterCondition: {self.current}/{self.max}")

        self.current += 1
        if self.current == 1:
            return initial_value
        elif self.current <= self.max:
            return value
        else:
            return None


class LoopCounterCondition:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
                        "count": ("INT", {"default": 1, "min": 0, "max": 9999999, "step": 1}),
                        "trigger": (["A", "B"], )
                    },
                }

    RETURN_TYPES = ("LOOP_CONDITION", )
    FUNCTION = "doit"

    def doit(s, count, trigger):
        return (CounterCondition(count), )


class TensorToCPU:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"tensor": ("*", ), }, }

    RETURN_TYPES = ("*", )
    FUNCTION = "doit"

    def doit(self, tensor):
        return (tensor.cpu(), )


NODE_CLASS_MAPPINGS = {
    "ExecutionSwitch": ExecutionSwitch,
    "ExecutionBlocker": ExecutionBlocker,
    "TensorToCPU": TensorToCPU,
    "LoopControl": LoopControl,
    "LoopCounterCondition": LoopCounterCondition,
}

NODE_DISPLAY_NAME_MAPPINGS = {
}


component_loader.load_all()
NODE_CLASS_MAPPINGS.update(component_loader.NODE_CLASS_MAPPINGS)

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']