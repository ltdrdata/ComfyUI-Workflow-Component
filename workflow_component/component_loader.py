import os
import json
import traceback
import nodes as comfy_nodes
import hashlib
import copy
import comfy.graph_utils

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
unresolved_map = {}
workflow_components = {}


def default_extra_data(data_type, extra_args):
    if data_type == "STRING":
        args = {"multiline": False}
    elif data_type == "INT":
        args = {"default": 0, "min": -1000000, "max": 1000000, "step": 1}
    elif data_type == "FLOAT":
        args = {"default": 0.0, "min": -1000000.0, "max": 1000000.0, "step": 0.1}
    else:
        args = {}
    args.update(extra_args)
    return args


def create_dynamic_class(component_raw_name, workflow, category=None):
    component_display_name = component_raw_name
    component_inputs = []
    component_outputs = []
    is_output_component = False

    graph = workflow["output"]

    for node_id, data in graph.items():
        if data["class_type"] == "ComponentMetadata":
            component_display_name = data["inputs"].get("name", component_raw_name)
            is_output_component = data["inputs"].get("always_output", False)
        elif data["class_type"] == "ComponentInput":
            data_type = data["inputs"]["data_type"]
            if len(data_type) > 0 and data_type[0] == "[":
                try:
                    data_type = json.loads(data_type)
                except:
                    pass
            try:
                if data["inputs"]["extra_args"].startswith("COMBO:"):
                    combo_info = data["inputs"]["extra_args"].split(':')
                    if len(combo_info) == 3:
                        extra_args = combo_info[1], combo_info[2]
                else:
                    extra_args = json.loads("{" + data["inputs"]["extra_args"] + "}")

                if data_type == "STRING":
                    if 'placeholder' not in extra_args:
                        extra_args['placeholder'] = data['inputs']['name']
            except:
                extra_args = {}

            component_inputs.append({
                "node_id": node_id,
                "name": data["inputs"]["name"],
                "data_type": data_type,
                "extra_args": extra_args,
                "explicit_input_order": data["inputs"]["explicit_input_order"],
                "optional": data["inputs"]["is_optional"],
            })
        elif data["class_type"] == "ComponentOutput":
            component_outputs.append({
                "node_id": node_id,
                "name": data["inputs"]["name"] or data["inputs"]["data_type"],
                "index": data["inputs"]["index"],
                "data_type": data["inputs"]["data_type"],
            })
    component_inputs.sort(key=lambda x: (x["explicit_input_order"], x["name"]))
    component_outputs.sort(key=lambda x: x["index"])
    for i in range(1, len(component_inputs)):
        if component_inputs[i]["name"] == component_inputs[i - 1]["name"]:
            raise Exception("Component input name is not unique: {}".format(component_inputs[i]["name"]))
    for i in range(1, len(component_outputs)):
        if component_outputs[i]["index"] == component_outputs[i - 1]["index"]:
            raise Exception("Component output index is not unique: {}".format(component_outputs[i]["index"]))

    def gen_input(node):
        if isinstance(node['extra_args'], tuple):
            combo_info = node['extra_args']
            if combo_info[0] in comfy_nodes.NODE_CLASS_MAPPINGS:
                cls = comfy_nodes.NODE_CLASS_MAPPINGS[combo_info[0]]
                cls_inputs = cls.INPUT_TYPES()
                node_input = cls_inputs['required'].get(combo_info[1], None)

                if node_input is None and 'optional' in cls_inputs:
                    node_input = cls_inputs['optional'].get(combo_info[1], None)

                if node_input is not None:
                    return node_input
                else:
                    return (f"Missing: '{combo_info[0]}'", {})
            else:
                return (f"Missing: '{combo_info[0]}'", {})
        else:
            return node["data_type"], default_extra_data(node["data_type"], node["extra_args"])


    class ComponentNode:
        def __init__(self):
            pass

        @classmethod
        def INPUT_TYPES(cls):
            return {
                "required": {node["name"]: gen_input(node) for node in component_inputs if not node["optional"]},
                "optional": {node["name"]: gen_input(node) for node in component_inputs if node["optional"]},
            }

        RETURN_TYPES = tuple([node["data_type"] for node in component_outputs])
        RETURN_NAMES = tuple([node["name"] for node in component_outputs])
        FUNCTION = "expand_component"

        CATEGORY = "Custom Components"
        OUTPUT_NODE = is_output_component

        def expand_component(self, **kwargs):
            new_graph = copy.deepcopy(graph)
            for input_node in component_inputs:
                if input_node["name"] in kwargs:
                    new_graph[input_node["node_id"]]["inputs"]["default_value"] = kwargs[input_node["name"]]
            outputs = tuple([[node["node_id"], 0] for node in component_outputs])
            new_graph, outputs = comfy.graph_utils.add_graph_prefix(new_graph, outputs, comfy.graph_utils.GraphBuilder.alloc_prefix())
            return {
                "result": outputs,
                "expand": new_graph,
            }
    ComponentNode.__name__ = component_raw_name

    print("Loaded component: {}".format(component_display_name))
    return ComponentNode, component_display_name


def update_unresolved_map(node_name, workflow):
    global unresolved_map

    # add new unresolved
    for node in workflow['nodes']:
        if node['type'] not in comfy_nodes.NODE_CLASS_MAPPINGS and node['type'] not in ['ComponentInput', 'ComponentInputOptional', 'ComponentOutput']:
            if node_name not in unresolved_map:
                unresolved_map[node_name] = set()

            unresolved_nodes = unresolved_map[node_name]
            unresolved_nodes.add(node['type'])


def resolve_unresolved_map():
    global unresolved_map

    fully_resolved = []
    for node_name, unresolved_nodes in unresolved_map.items():
        unresolved_nodes -= set(comfy_nodes.NODE_CLASS_MAPPINGS)
        if len(unresolved_nodes) == 0:
            fully_resolved.append(node_name)

    for node_name in fully_resolved:
        del unresolved_map[node_name]


def get_workflow_hash(workflow):
    json_str = json.dumps(workflow, sort_keys=True)
    hash_obj = hashlib.md5(json_str.encode())
    return hash_obj.hexdigest()[:6]


def load_component(component_name, is_full_name, workflow, direct_reflect=False, category=None):
    component_hash = get_workflow_hash(workflow)
    if is_full_name:
        node_name = component_name
    else:
        node_name = f"## {component_name} [{component_hash}]"

    try:
        if node_name not in comfy_nodes.NODE_CLASS_MAPPINGS:
            obj, display_name = create_dynamic_class(node_name, workflow, category)

            if direct_reflect:
                comfy_nodes.NODE_CLASS_MAPPINGS[node_name] = obj
                comfy_nodes.NODE_DISPLAY_NAME_MAPPINGS[node_name] = display_name
            else:
                NODE_CLASS_MAPPINGS[node_name] = obj
                NODE_DISPLAY_NAME_MAPPINGS[node_name] = display_name

            update_unresolved_map(node_name, workflow)

            return (True, node_name)
        else:
            return (False, node_name)
    except Exception as e:
        print(f"[ERROR] Failed to load component '{node_name}'\n\tMSG: {e}")
        traceback.print_exc()
        return (False, None)


def load_all(directory):
    global workflow_components

    def doit(category, cur_dir, filename):
        if filename.endswith(".component.json"):
            file_path = os.path.join(cur_dir, filename)

            component_name = os.path.basename(filename)[:-15]

            with open(file_path, "r", encoding="utf-8") as file:
                try:
                    data = json.load(file)
                    _, component_full_name = load_component(component_name, False, data, category=category)
                    # print(f"LOAD: {component_full_name}")
                    workflow_components[component_full_name] = data
                except Exception as ex:
                    print(f"[ERROR] Workflow-Component: Failed to loading component '{component_name}'\n{ex}")


    for root, dirs, files in os.walk(directory):
        relative_path = os.path.relpath(root, directory)

        if any(part.startswith(".") for part in root.split("/")):
            continue

        category = None if relative_path == "." else relative_path

        for file in files:
            doit(category, root, file)

    resolve_unresolved_map()



