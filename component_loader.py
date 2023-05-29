import os
import json
import workflow_execution
import nodes as comfy_nodes

directory = os.path.join(os.path.dirname(__file__), "components")

NODE_CLASS_MAPPINGS = {}


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
        if node['type'] == "ComponentInput":
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
                        input_slot = inputs[dest_slot]

                        if "widget" in input_slot:
                            widget_config = input_slot["widget"].get("config")
                            if widget_config is not None:
                                linked_slots_config[link_id] = (input_slot['type'], widget_config)
                        else:
                            linked_slots_config[link_id] = (input_slot['type'], None)

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

                    linked_slots_config[link_id] = (output_slot['type'], None)

    return linked_slots_config


def create_dynamic_class(component_name, input_nodes, output_nodes, workflow, prompt):
    input_types = {}
    input_mapping = {}
    internal_id_name_map = {}

    for node in workflow['nodes']:
        internal_id_name_map[str(node['id'])] = node['title'] if 'title' in node else node['type']

    # get widget config infos for auto recognition of input setting
    node_config_map = get_linked_slots_config(workflow)

    sorted_nodes = sorted(input_nodes, key=lambda x: (x.get('title', ''), x.get('title') is None))
    for i, node in enumerate(sorted_nodes):
        component_inputs = node['outputs']
        if len(component_inputs) > 0:
            input_links = component_inputs[0]['links']

            if input_links is None:
                # hide unconnected input
                pass
            else:
                for input_link in input_links:
                    if input_link in node_config_map:
                        input_type, node_config = node_config_map[input_link]
                        input_label = component_inputs[0].get('label', f"{input_type}_{i}")
                        input_mapping[input_label] = node

                        if node_config is not None:
                            input_types[input_label] = tuple(node_config)
                        else:
                            input_types[input_label] = (input_type,)

    return_types = []
    return_names = []
    output_mapping = {}

    sorted_nodes = sorted(output_nodes, key=lambda x: (x.get('title', ''), x.get('title') is None))
    for i, node in enumerate(sorted_nodes):
        component_outputs = node['inputs']

        if len(component_outputs) > 0:
            output_link = component_outputs[0].get('link', None)

            if output_link is None:
                # hide unconnected output
                pass
            else:
                if output_link in node_config_map:
                    output_type, node_config = node_config_map[output_link]
                    output_label = None

                    for output in node['inputs']:
                        output_label = output.get('label', f"{output_type}_{i}")
                        break

                    if output_type:
                        output_mapping[output_label] = (i, node)
                        return_types.append(output_type)
                        return_names.append(output_label)

    class DynamicClass:
        @classmethod
        def INPUT_TYPES(s):
            return {
                "required": input_types,
                "hidden": {"unique_id": "UNIQUE_ID"},
            }

        RETURN_TYPES = tuple(return_types)
        RETURN_NAMES = tuple(return_names)

        OUTPUT_NODE = len(output_mapping) == 0

        FUNCTION = "doit"

        CATEGORY = "Workflow"

        def doit(self, *args, **kwargs):
            return workflow_execution.execute(component_name, prompt, workflow,
                                              internal_id_name_map, input_mapping, output_mapping, *args, **kwargs)

    return DynamicClass


def process_node(component_name, workflow):
    nodes = workflow['nodes']
    prompt = workflow['output']

    input_nodes = [node for node in nodes if node['type'] == "ComponentInput"]
    output_nodes = [node for node in nodes if node['type'] == "ComponentOutput"]

    NODE_CLASS_MAPPINGS[f"## {component_name}"] = create_dynamic_class(component_name, input_nodes, output_nodes, workflow, prompt)


def load_all():
    workflow_components = {}

    for filename in os.listdir(directory):
        if filename.endswith(".component.json"):
            file_path = os.path.join(directory, filename)

            component_name = os.path.basename(filename)[:-15]

            with open(file_path, "r") as file:
                data = json.load(file)
                workflow_components[component_name] = data
                process_node(component_name, data)
