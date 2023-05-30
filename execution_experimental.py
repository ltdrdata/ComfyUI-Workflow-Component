# This module modifies the original code for experimentation with a new execution structure intended to replace the original execution structure.
# Original: https://github.com/comfyanonymous/ComfyUI/blob/master/execution.py

import sys
import copy
import traceback
import gc
import time

import torch
import nodes

import comfy.model_management
from execution import get_input_data, get_output_data, map_node_over_list, format_value, full_type_name
from queue import Queue


class DummyNode:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {}}

    RETURN_TYPES = ()
    FUNCTION = "doit"

    def doit(s, *args, **kwargs):
        if len(kwargs) == 1:
            key = list(kwargs.keys())[0]
            output = kwargs[key]
            return (output,)
        else:
            pass


def worklist_execute(server, prompt, outputs, current_item, extra_data, prompt_id, outputs_ui):
    worklist = Queue()
    executed = set()
    will_execute = {}

    def add_work(item):
        worklist.put(item)
        cnt = will_execute.get(item, 0)
        will_execute[item] = cnt + 1

    def get_work():
        item = worklist.get()
        cnt = will_execute.get(item, 0)
        if cnt <= 0:
            del will_execute[item]
        else:
            will_execute[item] = cnt - 1

        return str(item)

    def get_progress():
        total = len(executed)+len(will_execute.keys())
        return len(executed)/total

    add_work(current_item)

    while not worklist.empty():
        unique_id = get_work()

        if unique_id in executed:
            continue

        inputs = prompt[unique_id]['inputs']
        if 'class_type' not in prompt[unique_id]:
            class_def = DummyNode
        else:
            class_type = prompt[unique_id]['class_type']
            class_def = nodes.NODE_CLASS_MAPPINGS[class_type]

        if unique_id in outputs:
            continue

        for x in inputs:
            input_data = inputs[x]

            if isinstance(input_data, list):
                input_unique_id = input_data[0]
                output_index = input_data[1]
                if input_unique_id not in outputs:
                    if input_unique_id not in executed:
                        add_work(input_unique_id)

        input_data_all = None
        try:
            input_data_all = get_input_data(inputs, class_def, unique_id, outputs, prompt, extra_data)

            if input_data_all is None:
                add_work(unique_id)
                continue

            if server.client_id is not None:
                server.last_node_id = unique_id
                server.send_sync("executing", {"node": unique_id, "prompt_id": prompt_id, "progress": get_progress()}, server.client_id)
            obj = class_def()

            output_data, output_ui = get_output_data(obj, input_data_all)
            outputs[unique_id] = output_data
            if len(output_ui) > 0:
                outputs_ui[unique_id] = output_ui
                if server.client_id is not None:
                    server.send_sync("executed", {"node": unique_id, "output": output_ui, "prompt_id": prompt_id},
                                     server.client_id)
            executed.add(unique_id)
        except comfy.model_management.InterruptProcessingException as iex:
            print("Processing interrupted")

            # skip formatting inputs/outputs
            error_details = {
                "node_id": unique_id,
            }

            return executed, False, error_details, iex
        except Exception as ex:
            typ, _, tb = sys.exc_info()
            exception_type = full_type_name(typ)
            input_data_formatted = {}
            if input_data_all is not None:
                input_data_formatted = {}
                for name, inputs in input_data_all.items():
                    input_data_formatted[name] = [format_value(x) for x in inputs]

            output_data_formatted = {}
            for node_id, node_outputs in outputs.items():
                output_data_formatted[node_id] = [[format_value(x) for x in l] for l in node_outputs]

            print("!!! Exception during processing !!!")
            print(traceback.format_exc())

            error_details = {
                "node_id": unique_id,
                "exception_message": str(ex),
                "exception_type": exception_type,
                "traceback": traceback.format_tb(tb),
                "current_inputs": input_data_formatted,
                "current_outputs": output_data_formatted
            }
            return executed, False, error_details, ex

    return executed, True, None, None


def worklist_will_execute(prompt, outputs, current_item):
    worklist = [current_item]
    will_execute = []

    while worklist:
        unique_id = str(worklist.pop())

        inputs = prompt[unique_id]['inputs']

        if unique_id in outputs:
            continue

        for x in inputs:
            input_data = inputs[x]
            if isinstance(input_data, list):
                input_unique_id = input_data[0]
                output_index = input_data[1]
                if input_unique_id not in outputs:
                    worklist.append(input_unique_id)

        will_execute.append(unique_id)

    return will_execute


def worklist_output_delete_if_changed(prompt, old_prompt, outputs):
    worklist = []
    deleted = set()

    # build forward map
    nexts = {}
    for key, value in prompt.items():
        inputs = value['inputs']

        for input_data in inputs.values():
            if isinstance(input_data, list):
                input_unique_id = input_data[0]
                if input_unique_id in nexts:
                    nexts[input_unique_id].append(key)
                else:
                    nexts[input_unique_id] = [key]

    # set seeds
    for unique_id, value in prompt.items():
        inputs = value['inputs']
        if 'class_type' not in value:
            class_def = DummyNode
        else:
            class_type = value['class_type']
            class_def = nodes.NODE_CLASS_MAPPINGS[class_type]

        is_changed_old = ''
        is_changed = ''
        to_delete = False

        if hasattr(class_def, 'IS_CHANGED'):
            if unique_id in old_prompt and 'is_changed' in old_prompt[unique_id]:
                is_changed_old = old_prompt[unique_id]['is_changed']
            if 'is_changed' not in value:
                input_data_all = get_input_data(inputs, class_def, unique_id, outputs)
                if input_data_all is not None:
                    try:
                        is_changed = map_node_over_list(class_def, input_data_all, "IS_CHANGED")
                        value['is_changed'] = is_changed
                    except:
                        to_delete = True
            else:
                is_changed = value['is_changed']

        if unique_id not in outputs:
            to_delete = True
        else:
            if not to_delete:
                if is_changed != is_changed_old:
                    to_delete = True
                elif unique_id not in old_prompt:
                    to_delete = True
                elif inputs == old_prompt[unique_id]['inputs']:
                    for x in inputs:
                        input_data = inputs[x]

                        if isinstance(input_data, list):
                            input_unique_id = input_data[0]

                            if input_unique_id not in outputs:
                                to_delete = True
                                break
                else:
                    to_delete = True

        if to_delete:
            worklist.append(unique_id)

    # cascade removing
    while worklist:
        unique_id = worklist.pop()

        if unique_id in deleted:
            continue

        if unique_id in outputs:
            d = outputs.pop(unique_id)
            del d

        new_works = nexts.get(unique_id, [])
        worklist.extend(new_works)
        deleted.add(unique_id)

    return outputs


class ExpPromptExecutor:
    def __init__(self, server):
        self.outputs = {}
        self.outputs_ui = {}
        self.old_prompt = {}
        self.server = server

    def handle_execution_error(self, prompt_id, prompt, current_outputs, executed, error, ex):
        node_id = error["node_id"]
        if "class_type" in prompt[node_id]:
            class_type = prompt[node_id]["class_type"]
        else:
            class_type = "ComponentInput/Output"

        # First, send back the status to the frontend depending
        # on the exception type
        if isinstance(ex, comfy.model_management.InterruptProcessingException):
            mes = {
                "prompt_id": prompt_id,
                "node_id": node_id,
                "node_type": class_type,
                "executed": list(executed),
            }
            self.server.send_sync("execution_interrupted", mes, self.server.client_id)
        else:
            if self.server.client_id is not None:
                mes = {
                    "prompt_id": prompt_id,
                    "node_id": node_id,
                    "node_type": class_type,
                    "executed": list(executed),

                    "exception_message": error["exception_message"],
                    "exception_type": error["exception_type"],
                    "traceback": error["traceback"],
                    "current_inputs": error["current_inputs"],
                    "current_outputs": error["current_outputs"],
                }
                self.server.send_sync("execution_error", mes, self.server.client_id)

        # Next, remove the subsequent outputs since they will not be executed
        to_delete = []
        for o in self.outputs:
            if (o not in current_outputs) and (o not in executed):
                to_delete += [o]
                if o in self.old_prompt:
                    d = self.old_prompt.pop(o)
                    del d
        for o in to_delete:
            d = self.outputs.pop(o)
            del d

    def execute(self, prompt, prompt_id, extra_data={}, execute_outputs=[]):
        nodes.interrupt_processing(False)

        if "client_id" in extra_data:
            self.server.client_id = extra_data["client_id"]
        else:
            self.server.client_id = None

        execution_start_time = time.perf_counter()
        if self.server.client_id is not None:
            self.server.send_sync("execution_start", { "prompt_id": prompt_id}, self.server.client_id)

        with torch.inference_mode():
            #delete cached outputs if nodes don't exist for them
            to_delete = []
            for o in self.outputs:
                if o not in prompt:
                    to_delete += [o]
            for o in to_delete:
                d = self.outputs.pop(o)
                del d

            worklist_output_delete_if_changed(prompt, self.old_prompt, self.outputs)

            current_outputs = set(self.outputs.keys())
            for x in list(self.outputs_ui.keys()):
                if x not in current_outputs:
                    d = self.outputs_ui.pop(x)
                    del d

            if self.server.client_id is not None:
                self.server.send_sync("execution_cached", { "nodes": list(current_outputs) , "prompt_id": prompt_id}, self.server.client_id)
            executed = set()
            output_node_id = None
            to_execute = []

            for node_id in list(execute_outputs):
                to_execute += [(0, node_id)]

            while len(to_execute) > 0:
                #always execute the output that depends on the least amount of unexecuted nodes first
                to_execute = sorted(list(map(lambda a: (len(worklist_will_execute(prompt, self.outputs, a[-1])), a[-1]), to_execute)))
                output_node_id = to_execute.pop(0)[-1]

                # This call shouldn't raise anything if there's an error deep in
                # the actual SD code, instead it will report the node where the
                # error was raised
                executed, success, error, ex = worklist_execute(self.server, prompt, self.outputs, output_node_id, extra_data, prompt_id, self.outputs_ui)
                if success is not True:
                    self.handle_execution_error(prompt_id, prompt, current_outputs, executed, error, ex)
                    break

            for x in executed:
                self.old_prompt[x] = copy.deepcopy(prompt[x])
            self.server.last_node_id = None
            if self.server.client_id is not None:
                self.server.send_sync("executing", { "node": None, "prompt_id": prompt_id }, self.server.client_id)

        print("Prompt executed in {:.2f} seconds".format(time.perf_counter() - execution_start_time))
        gc.collect()
        comfy.model_management.soft_empty_cache()