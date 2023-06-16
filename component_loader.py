import os
import json
import traceback

import workflow_execution
import nodes as comfy_nodes
import hashlib

directory = os.path.join(os.path.dirname(__file__), "components")

NODE_CLASS_MAPPINGS = {}
unresolved_map = {}
workflow_components = {}


class ComponentBase:
    FUNCTION = "doit"

    CATEGORY = "WorkflowComponents"


def convert_nodes_to_dict(nodes):
    nodes_dict = {}

    for node in nodes:
        node_id = node["id"]
        nodes_dict[node_id] = node

    return nodes_dict


def convert_links_to_dict(links):
    node_links_dict = {}

    for link in links:
        node_id = link[0]
        node_links_dict[node_id] = link

    return node_links_dict


def get_linked_slots_config(json_data):
    linked_slots_config = {}

    # Extract nodes and links from JSON data
    nodes = convert_nodes_to_dict(json_data["nodes"])
    links = convert_links_to_dict(json_data["links"])

    # Iterate over nodes
    for node in nodes.values():
        if node['type'] in ["ComponentInput", "ComponentInputOptional"]:
            node_outputs = node["outputs"] if 'outputs' in node else []

            for output in node_outputs:
                if output["links"] is None:
                    continue

                output_links = output["links"]

                for link_id in output_links:
                    dest_node = links[link_id][3]
                    dest_slot = links[link_id][4]

                    if dest_node in nodes and "inputs" in nodes[dest_node]:
                        inputs = nodes[dest_node]["inputs"]
                        widgets_values = nodes[dest_node]['widgets_values'] if 'widgets_values' in nodes[dest_node] else None

                        input_slot = inputs[dest_slot]

                        if "widget" in input_slot:
                            widget_config = input_slot["widget"].get("config")
                            if widget_config is not None:
                                linked_slots_config[link_id] = (input_slot['type'], widget_config, nodes[dest_node]['type'], input_slot['name'], widgets_values)
                        else:
                            linked_slots_config[link_id] = (input_slot['type'], None, None, None, None)

        if node['type'] == "ComponentOutput":
            node_inputs = node["inputs"] if 'inputs' in node else []
            for input in node_inputs:
                if input["link"] is None:
                    continue

                link_id = input["link"]

                src_node = links[link_id][1]
                src_slot = links[link_id][2]

                if src_node in nodes and "outputs" in nodes[src_node]:
                    outputs = nodes[src_node]["outputs"]
                    output_slot = outputs[src_slot]

                    linked_slots_config[link_id] = (output_slot['type'], None, None, None, None)

    return linked_slots_config


def create_dynamic_class(component_name, workflow, category=None):
    nodes = workflow['nodes']
    prompt = workflow['output']

    input_nodes = [node for node in nodes if node['type'] == "ComponentInput"]
    input_optional_nodes = [node for node in nodes if node['type'] == "ComponentInputOptional"]
    output_nodes = [node for node in nodes if node['type'] == "ComponentOutput"]

    input_mapping = {}
    internal_id_name_map = {}

    for node in workflow['nodes']:
        internal_id_name_map[str(node['id'])] = node['title'] if 'title' in node else node['type']

    # get widget config infos for auto recognition of input setting
    node_config_map = get_linked_slots_config(workflow)

    sorted_input_nodes = sorted(input_nodes, key=lambda x: (x.get('title', ''), x.get('title') is None))

    def get_input_types_dynamic():
        try:
            input_types = {}
            for i, node in enumerate(sorted_input_nodes):
                build_input_types(i, input_mapping, input_types, node, node_config_map)
            return input_types
        except Exception as e:
            print(f"[Workflow-Component] '{component_name}' is broken. Maybe there are missing nodes. (INFO: {e})")
            traceback.print_exc()
            return {"BROKEN component": ("BROKEN component", )}

    sorted_input_optional_nodes = sorted(input_optional_nodes, key=lambda x: (x.get('title', ''), x.get('title') is None))

    def get_input_optional_types_dynamic():
        try:
            input_optional_types = {}
            for i, node in enumerate(sorted_input_optional_nodes):
                build_input_types(i, input_mapping, input_optional_types, node, node_config_map)
            return input_optional_types
        except Exception as e:
            print(f"[Workflow-Component] BROKEN component - {e}")
            traceback.print_exc()
            return {"BROKEN component": ("BROKEN component", )}

    return_types = []
    return_names = []
    output_mapping = {}
    optional_inputs = {str(node['id']) for node in input_optional_nodes}

    sorted_nodes = sorted(output_nodes, key=lambda x: (x.get('title', ''), x.get('title') is None))
    for i, node in enumerate(sorted_nodes):
        build_output_types(i, node, node_config_map, output_mapping, return_names, return_types)

    category = "Workflow/Temp" if category is None else f"Workflow/{category}"

    class DynamicClass:
        @classmethod
        def INPUT_TYPES(s):
            input_optional_types = get_input_optional_types_dynamic()
            if len(input_optional_types) > 0:
                return {
                    "required": get_input_types_dynamic(),
                    "optional": input_optional_types,
                    "hidden": {"unique_id": "UNIQUE_ID", "extra_pnginfo": "EXTRA_PNGINFO"},
                }
            else:
                return {
                    "required": get_input_types_dynamic(),
                    "hidden": {"unique_id": "UNIQUE_ID", "extra_pnginfo": "EXTRA_PNGINFO"},
                }

        RETURN_TYPES = tuple(return_types)
        RETURN_NAMES = tuple(return_names)

        OUTPUT_NODE = len(output_mapping) == 0

        FUNCTION = "doit"

        CATEGORY = category

        def doit(self, *args, **kwargs):
            return workflow_execution.execute(component_name, prompt, workflow,
                                              internal_id_name_map, optional_inputs, input_mapping, output_mapping,
                                              *args, **kwargs)

        @classmethod
        def IS_CHANGED(cls, **kwargs):
            return workflow_execution.is_changed(component_name, internal_id_name_map, output_mapping, **kwargs)

    return DynamicClass


def build_output_types(i, node, node_config_map, output_mapping, return_names, return_types):
    component_outputs = node['inputs']
    if len(component_outputs) > 0:
        output_link = component_outputs[0].get('link', None)

        if output_link is None:
            # hide unconnected output
            pass
        else:
            if output_link in node_config_map:
                output_type, node_config, node_type, output_slot, widget_values = node_config_map[output_link]
                output_label = None

                for output in node['inputs']:
                    output_label = output.get('label', f"{output_type}_{i}")
                    break

                if output_label is None:
                    output_label = output_type

                if output_type:
                    output_mapping[node['id']] = (i, node)
                    return_types.append(output_type)
                    return_names.append(output_label)


def flatten_INPUT_TYPES(data):
    # order assumption: required, optional
    # ref: app.js registerNodes()
    items = {}
    if 'required' in data:
        items = data['required']

    if 'optional' in data:
        items.update(data['optional'])

    return items


def build_input_types(i, input_mapping, input_types, node, node_config_map):
    component_inputs = node['outputs']
    if len(component_inputs) > 0:
        input_links = component_inputs[0]['links']

        used_labels = set()

        if input_links is None:
            # hide unconnected input
            pass
        else:
            if len(input_links) > 0:
                input_link = input_links[0]  # we need only 1 link for a slot
                if input_link in node_config_map:
                    input_type, node_config, node_type, input_slot, widget_values = node_config_map[input_link]

                    if 'label' in node['outputs'][0]:
                        input_label = node['outputs'][0]['label']
                    else:
                        input_label = None

                    if node_type is not None and input_slot is not None:
                        node_input_types = comfy_nodes.NODE_CLASS_MAPPINGS[node_type].INPUT_TYPES()

                        widget_idx = -1
                        widget_values_found = False
                        last_is_int = False
                        if input_type in ['FLOAT', 'INT', 'STRING'] and node_config is not None:
                            for _, key in enumerate(node_input_types['required'].keys()):
                                slot = node_input_types['required'][key]
                                if len(slot) >= 2 and 'default' in slot[1] or isinstance(slot[0], list):
                                    widget_idx += 1

                                if last_is_int and widget_values[widget_idx] in ['randomize', 'fixed', 'increment', 'decrement']:
                                    widget_idx += 1  # skip 'control after...' widget. It belongs to former INT widget

                                last_is_int = slot[0] == 'INT'

                                if key == input_slot:
                                    widget_values_found = True
                                    break

                            if not widget_values_found and 'optional' in node_input_types:
                                for _, key in enumerate(node_input_types['optional'].keys()):
                                    slot = node_input_types['optional'][key]
                                    if len(slot) >= 2 and 'default' in slot[1] or isinstance(slot[0], list):
                                        widget_idx += 1

                                    if last_is_int and widget_values[widget_idx] in ['randomize', 'fixed', 'increment', 'decrement']:
                                        widget_idx += 1  # skip 'control after...' widget. It belongs to former INT widget

                                    last_is_int = slot[0] == 'INT'

                                    if key == input_slot:
                                        widget_values_found = True
                                        break

                        if widget_values_found:
                            node_config[1]['default'] = widget_values[widget_idx]
                            input_value = tuple(node_config)
                        else:
                            input_value = flatten_INPUT_TYPES(node_input_types)[input_slot]

                        if input_label is None and isinstance(input_value[0], list):
                            input_label = input_slot
                    else:
                        input_value = (input_type,)

                    if input_label is None:
                        if input_slot is not None:
                            input_label = component_inputs[0].get('label', input_slot)
                        else:
                            input_label = component_inputs[0].get('label', input_type)

                        if input_label in used_labels:
                            input_label = f"{input_label}_{i}"

                        used_labels.add(input_label)

                    input_mapping[input_label] = node

                    input_types[input_label] = input_value


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
            obj = create_dynamic_class(node_name, workflow, category)

            if direct_reflect:
                comfy_nodes.NODE_CLASS_MAPPINGS[node_name] = obj
            else:
                NODE_CLASS_MAPPINGS[node_name] = obj

            update_unresolved_map(node_name, workflow)

            return (True, node_name)
        else:
            return (False, node_name)
    except Exception as e:
        print(f"[ERROR] Failed to load component '{node_name}'\n\tMSG: {e}")
        traceback.print_exc()
        return (False, None)


def load_all():
    global workflow_components

    def doit(category, cur_dir, filename):
        if filename.endswith(".component.json"):
            file_path = os.path.join(cur_dir, filename)

            component_name = os.path.basename(filename)[:-15]

            with open(file_path, "r") as file:
                data = json.load(file)
                _, component_full_name = load_component(component_name, False, data, category=category)
                workflow_components[component_full_name] = data

    for root, dirs, files in os.walk(directory):
        relative_path = os.path.relpath(root, directory)

        if os.path.basename(root).startswith("."):
            continue

        category = None if relative_path == "." else relative_path

        for file in files:
            doit(category, root, file)

    resolve_unresolved_map()



