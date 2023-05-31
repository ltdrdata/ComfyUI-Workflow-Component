import os
import sys
import folder_paths
import shutil

impact_path = os.path.dirname(__file__)
sys.path.append(impact_path)

import component_loader

print("### Loading: ComfyUI-Workflow-Component (V0.8.1) !! WARN: This is an experimental extension. Extremely unstable. !!")

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

import execution
import uuid
import workflow_execution

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
        valid = execution.validate_prompt(prompt)
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

    if "prompt" in json_data:
        prompt = json_data["prompt"]
        workflow_execution.garbage_collect(prompt.keys())

    return await original_post_prompt(request)


server.PromptServer.instance.app.router.add_post('/prompt', prompt_hook)


NODE_CLASS_MAPPINGS = {
}

NODE_DISPLAY_NAME_MAPPINGS = {
}


component_loader.load_all()
NODE_CLASS_MAPPINGS.update(component_loader.NODE_CLASS_MAPPINGS)

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
