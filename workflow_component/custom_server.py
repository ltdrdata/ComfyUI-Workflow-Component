import os
import uuid
import server
from aiohttp import web

import workflow_component.component_loader as component_loader
import workflow_component.workflow_execution as workflow_execution
import workflow_component.execution_experimental as execution_experimental



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
            response = {"prompt_id": prompt_id, "number": number, "node_errors": valid[3]}
            return web.json_response(response)
        else:
            print("invalid prompt:", valid[1])
            return web.json_response({"error": valid[1], "node_errors": valid[3]}, status=400)
    else:
        return web.json_response({"error": "no prompt", "node_errors": []}, status=400)


@server.PromptServer.instance.routes.post("/prompt")
async def prompt_hook(request):
    json_data = await request.json()

    extra_data = json_data.get('extra_data', {})
    extra_pnginfo = extra_data.get('extra_pnginfo', {})
    workflow = extra_pnginfo.get('workflow', {})
    nodes = workflow.get('nodes', [])
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
        unresolved_nodes -= set(['Reroute', 'Note'])

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
