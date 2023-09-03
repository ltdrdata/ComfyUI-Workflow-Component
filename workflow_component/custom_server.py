import os
import server
from aiohttp import web

import workflow_component.component_loader as component_loader
import workflow_component.workflow_execution as workflow_execution


def onprompt(json_data):
    extra_data = json_data.get('extra_data', {})
    extra_pnginfo = extra_data.get('extra_pnginfo', {})
    workflow = extra_pnginfo.get('workflow', {})
    nodes = workflow.get('nodes', [])

    workflow_execution.extra_pnginfo = extra_pnginfo

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
        unresolved_nodes -= set(['Reroute', 'Note', 'PrimitiveNode'])

        if len(unresolved_nodes) > 0:
            msg = f"<B>Non-installed custom nodes are being used within the component.</B><BR><BR>{unresolved_nodes}"
            return web.json_response({"error": {"message": msg}, "node_errors": {}}, status=400)

    if "prompt" in json_data:
        prompt = json_data["prompt"]
        workflow_execution.garbage_collect(prompt.keys())

    return json_data


server.PromptServer.instance.add_on_prompt_handler(onprompt)


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
