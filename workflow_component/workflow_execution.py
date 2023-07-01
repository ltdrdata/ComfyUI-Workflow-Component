from workflow_component.execution_experimental import *
from server import PromptServer


class VirtualServer:
    def __init__(self, component_name, internal_id_name_map, node_id):
        self.internal_id_name_map = internal_id_name_map
        self.client_id = PromptServer.instance.client_id
        self.component_name = component_name
        self.node_id = node_id
        self.occurred_event = None

    def update_node_status(self, text, progress=None):
        if self.client_id is None:
            return

        PromptServer.instance.send_sync("component/update_status", {
            "node_id": self.node_id,
            "progress": progress,
            "text": text
        }, self.client_id)

    def send_sync(self, event, data, sid=None):
        # print(f"event: {event}")
        # print(f"data: {data}")
        # print(f"sid: {sid}")

        if event == "execution_interrupted":
            print(f"An interrupt occurred while processing the workflow component '## {self.component_name}'(id={self.node_id})")
            data['node_id'] = self.node_id
            data['executed'] = []
            self.occurred_event = event, data, sid

        elif event == "execution_error":
            print(f"\nAn error occurred in the '{data['node_type']}'(id={data['node_id']}) node within the component '## {self.component_name}'(id={self.node_id}).")
            print(f"ERROR MESSAGE: {data['exception_message']}\n")
            data['node_id'] = self.node_id
            data['executed'] = []
            self.occurred_event = event, data, sid

        elif event == "executing":
            data['executed'] = []

            if data['node'] is not None:
                data['text'] = f"{self.internal_id_name_map[data['node']]} ({int(data['progress']*100)}%)"
                data['node'] = self.node_id
                PromptServer.instance.send_sync("component/update_status", data, sid)
            else:
                data['text'] = None
                data['progress'] = None
                data['node'] = self.node_id
                PromptServer.instance.send_sync("component/update_status", data, sid)

        return PromptServer.instance.send_sync(event, data, sid)


executor_dict = {}


def garbage_collect(keys):
    global executor_dict
    executor_dict = {key: value for key, value in executor_dict.items() if key in keys}


def get_executor(component_name, internal_id_name_map, node_id):
    if node_id in executor_dict:
        if executor_dict[node_id][0] != component_name:
            del executor_dict[node_id]

    if node_id not in executor_dict:
        vs = VirtualServer(component_name, internal_id_name_map, node_id)
        executor = ExpPromptExecutor(vs)
        executor.calculated_outputs = set()
        executor_dict[node_id] = (component_name, executor)

    return executor_dict[node_id][1]


virtual_prompt_id = 0


def get_virtual_prompt_id(node_id):
    global virtual_prompt_id
    virtual_prompt_id += 1
    return f"wc-{node_id}-{virtual_prompt_id}"


def is_changed(component_name, internal_id_name_map, output_mapping, **kwargs):
    node_id = int(kwargs['unique_id'])
    nodes = kwargs['extra_pnginfo']['workflow']['nodes']
    current_component_node = [node for node in nodes if node['id'] == node_id]

    if len(current_component_node) == 0:
        print(f"MISSING NODE: {node_id}")
        return False
    else:
        current_component_node = current_component_node[0]

    pe = get_executor(component_name, internal_id_name_map, node_id)

    for key in output_mapping:
        order, _ = output_mapping[key]

        if 'outputs' in current_component_node:
            c_outputs = current_component_node['outputs']
            if len(c_outputs) > order and 'links' in c_outputs[order]:
                c_links = c_outputs[order]['links']
                if c_links is not None and len(c_links) > 0:
                    if order not in pe.calculated_outputs:
                        return True

    return False


def execute(component_name, prompt, workflow, internal_id_name_map, optional_inputs, input_mapping, output_mapping,
            *args, **kwargs):
    node_id = kwargs['unique_id']
    pe = get_executor(component_name, internal_id_name_map, node_id)
    pe.server.occurred_event = None
    pe.server.update_node_status("Begin (0%)", 0)
    pe.calculated_outputs = set()

    changed_inputs = set()

    for node in kwargs['extra_pnginfo']['workflow']['nodes']:
        if node['id'] == int(node_id):
            current_component_node = node
            break

    def not_equal(a, b):
        try:
            return a != b
        except:
            return True

    # get empty prompt option
    empty_option_prompts = [key for key, value in prompt.items() if key in optional_inputs and not value['inputs']]

    # unlink unprovided option prompt
    for key, value in prompt.items():
        new_value = {name: input_value for name, input_value in value['inputs'].items() if
                     not isinstance(input_value, list) or input_value[0] not in empty_option_prompts}
        prompt[key]['inputs'] = new_value

    # pass input interface to internal nodes
    for key, value in kwargs.items():
        if key not in ["unique_id", "prompt", "extra_pnginfo", 'used_output_names']:
            input_node = input_mapping[key]
            input_node_id = str(input_node['id'])

            if input_node_id not in pe.outputs.keys() or not_equal(pe.outputs[input_node_id], [[value]]):
                pe.outputs[input_node_id] = [[value]]  # TODO: check
                changed_inputs.add(input_node_id)

            pe.old_prompt[input_node_id] = prompt[input_node_id]  # prevent erasing of output cache

    # remove output's old_prompt for regeneration of changed
    for key, value in prompt.items():
        inputs = value['inputs']
        for x in inputs:
            input_data = inputs[x]
            if isinstance(input_data, list):
                input_unique_id = input_data[0]
                if input_unique_id in changed_inputs and key in pe.old_prompt:
                    del pe.old_prompt[key]

    prompt_id = get_virtual_prompt_id(node_id)

    execute_outputs = []
    for key in output_mapping:
        order, output_node = output_mapping[key]
        # add to execute_outputs if feasible output
        # current_component_node == None -> virtual execution
        if 'used_output_names' in kwargs:
            if output_node['inputs'][0]['name'] in kwargs['used_output_names']:
                execute_outputs.append(output_node['id'])

        elif 'outputs' in current_component_node:
            c_outputs = current_component_node['outputs']
            if len(c_outputs) > order and 'links' in c_outputs[order]:
                c_links = c_outputs[order]['links']
                if c_links is not None and len(c_links) > 0:
                    output_node_id = str(output_node['id'])
                    execute_outputs.append(output_node_id)

    # this must be calculated on-demand due to custom node loading order
    for node in workflow['nodes']:
        class_type = node['type']
        if class_type in ["ComponentInput", "ComponentInputOptional", "ComponentOutput", "Reroute"]:
            pass
        elif class_type:
            class_def = nodes.NODE_CLASS_MAPPINGS[class_type]
            if hasattr(class_def, "OUTPUT_NODE") and class_def.OUTPUT_NODE:
                execute_outputs.append(node['id'])

    workflow['client_id'] = pe.server.client_id
    pe.execute(prompt, prompt_id, workflow, execute_outputs=execute_outputs)

    if pe.server.occurred_event is not None:
        pe.server.update_node_status("Error", None)
        if pe.server.occurred_event[0] == "execution_interrupted":
            raise comfy.model_management.InterruptProcessingException()
        else:
            err = pe.server.occurred_event[1]

            traceback_msg = ""
            for item in err['traceback']:
                traceback_msg += f"&nbsp;&nbsp;&nbsp;{item}"

            msg = f"\n------------------------\nComponent internal error on [{err['node_id']}]:{err['node_type']}\nError:{err['exception_message']}\nTraceback:\n{traceback_msg}\n------------------------\n"
            raise Exception(msg)

    results = []
    for key in output_mapping:
        order, output_node = output_mapping[key]
        output_node_id = str(output_node['id'])
        inputs = prompt[output_node_id]['inputs']

        class_def = DummyNode

        input_data_all = get_input_data(inputs, class_def, output_node_id, pe.outputs, prompt, workflow)

        if input_data_all is None:
            print(f"ERROR: Output slot '{key}' in '{component_name}[{node_id}]' doesn't provide any value.")
            unboxed_value = None
        else:
            _, value = next(iter(input_data_all.items()))
            unboxed_value = value[0]  # TODO: check

        results.append((order, unboxed_value))
        pe.calculated_outputs.add(order)

    results.sort(key=lambda x: x[0])

    return tuple(value for order, value in results)
