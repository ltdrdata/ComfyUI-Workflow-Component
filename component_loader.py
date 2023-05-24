import os
import json
import workflow_execution
import nodes as comfy_nodes

directory = os.path.join(os.path.dirname(__file__), "components")

NODE_CLASS_MAPPINGS = {}


class ComponentBase:
    FUNCTION = "doit"

    CATEGORY = "WorkflowComponents"


def create_dynamic_class(input_nodes, output_nodes, workflow, prompt):
    input_types = {}
    input_mapping = {}
    for i, node in enumerate(input_nodes):
        input_type = node['outputs'][0]['type']
        input_label = node['outputs'][0].get('label', f"{input_type}_{i}")

        input_mapping[input_label] = node

        # TODO: recognize automatically based on workflow
        if input_type == "STRING":
            input_types[input_label] = (input_type, {'default': ""})
        elif input_type == "INT":
            input_types[input_label] = (input_type, {'default': "5"})
        elif input_type == "FLOAT":
            input_types[input_label] = (input_type, {'default': "0.5"})
        else:
            input_types[input_label] = (input_type,)

    return_types = []
    return_names = []
    output_mapping = {}

    for i, node in enumerate(output_nodes):
        output_type = None
        output_label = None

        for output in node['inputs']:
            if output['type'] != "##IS_COMPONENT_OUTPUT":
                output_type = output['type']
                output_label = output.get('name', f"{output_type}_{i}")
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
            return workflow_execution.execute(prompt, workflow, input_mapping, output_mapping, *args, **kwargs)

    return DynamicClass


def process_node(component_name, workflow):
    nodes = workflow['nodes']
    prompt = workflow['output']

    input_nodes = [node for node in nodes if
                   any(input_node['type'] == '##IS_COMPONENT_INPUT' for input_node in node['inputs'])]
    output_nodes = [node for node in nodes if
                    any(input_node['type'] == '##IS_COMPONENT_OUTPUT' for input_node in node['inputs'])]

    NODE_CLASS_MAPPINGS[f"## {component_name}"] = create_dynamic_class(input_nodes, output_nodes, workflow, prompt)


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
