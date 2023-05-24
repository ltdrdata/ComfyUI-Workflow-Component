# This module modifies the original code for experimentation with a new execution structure intended to replace the original execution structure.
# Original: https://github.com/comfyanonymous/ComfyUI/blob/master/execution.py

import copy
import traceback
import gc
import time

import torch
import nodes

import comfy.model_management
from execution import get_input_data, get_output_data, map_node_over_list
from queue import Queue

def worklist_execute(server, prompt, outputs, current_item, extra_data, prompt_id, outputs_ui):
    worklist = Queue()
    executed = set()

    worklist.put(current_item)

    while not worklist.empty():
        unique_id = str(worklist.get())

        if unique_id in executed:
            continue

        inputs = prompt[unique_id]['inputs']
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
                        worklist.put(input_unique_id)

        input_data_all = get_input_data(inputs, class_def, unique_id, outputs, prompt, extra_data)

        if input_data_all is None:
            worklist.put(unique_id)
            continue

        if server.client_id is not None:
            server.last_node_id = unique_id
            server.send_sync("executing", {"node": unique_id, "prompt_id": prompt_id}, server.client_id)
        obj = class_def()

        output_data, output_ui = get_output_data(obj, input_data_all)
        outputs[unique_id] = output_data
        if len(output_ui) > 0:
            outputs_ui[unique_id] = output_ui
            if server.client_id is not None:
                server.send_sync("executed", {"node": unique_id, "output": output_ui, "prompt_id": prompt_id},
                                 server.client_id)
        executed.add(unique_id)

    return executed


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


def worklist_output_delete_if_changed(prompt, old_prompt, outputs, current_item):
    worklist = [current_item]

    while worklist:
        unique_id = worklist.pop()

        inputs = prompt[unique_id]['inputs']
        class_type = prompt[unique_id]['class_type']
        class_def = nodes.NODE_CLASS_MAPPINGS[class_type]

        is_changed_old = ''
        is_changed = ''
        to_delete = False

        if hasattr(class_def, 'IS_CHANGED'):
            if unique_id in old_prompt and 'is_changed' in old_prompt[unique_id]:
                is_changed_old = old_prompt[unique_id]['is_changed']
            if 'is_changed' not in prompt[unique_id]:
                input_data_all = get_input_data(inputs, class_def, unique_id, outputs)
                if input_data_all is not None:
                    try:
                        is_changed = map_node_over_list(class_def, input_data_all, "IS_CHANGED")
                        prompt[unique_id]['is_changed'] = is_changed
                    except:
                        to_delete = True
            else:
                is_changed = prompt[unique_id]['is_changed']

        if unique_id not in outputs:
            continue

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
                        output_index = input_data[1]
                        if input_unique_id in outputs:
                            worklist.append(input_unique_id)
                        else:
                            to_delete = True
                            break
            else:
                to_delete = True

        if to_delete:
            d = outputs.pop(unique_id)
            del d

    return outputs


class ExpPromptExecutor:
    def __init__(self, server):
        self.outputs = {}
        self.outputs_ui = {}
        self.old_prompt = {}
        self.server = server

    def execute(self, prompt, prompt_id, extra_data={}, execute_outputs=[]):
        nodes.interrupt_processing(False)

        if "client_id" in extra_data:
            self.server.client_id = extra_data["client_id"]
        else:
            self.server.client_id = None

        execution_start_time = time.perf_counter()
        if self.server.client_id is not None:
            self.server.send_sync("execution_start", {"prompt_id": prompt_id}, self.server.client_id)

        with torch.inference_mode():
            # delete cached outputs if nodes don't exist for them
            to_delete = []
            for o in self.outputs:
                if o not in prompt:
                    to_delete += [o]
            for o in to_delete:
                d = self.outputs.pop(o)
                del d

            for x in prompt:
                worklist_output_delete_if_changed(prompt, self.old_prompt, self.outputs, x)

            current_outputs = set(self.outputs.keys())
            for x in list(self.outputs_ui.keys()):
                if x not in current_outputs:
                    d = self.outputs_ui.pop(x)
                    del d

            if self.server.client_id is not None:
                self.server.send_sync("execution_cached", {"nodes": list(current_outputs), "prompt_id": prompt_id},
                                      self.server.client_id)
            executed = set()
            try:
                to_execute = []
                for x in list(execute_outputs):
                    to_execute += [(0, x)]

                while len(to_execute) > 0:
                    # always execute the output that depends on the least amount of unexecuted nodes first
                    to_execute = sorted(list(
                        map(lambda a: (len(worklist_will_execute(prompt, self.outputs, a[-1])), a[-1]), to_execute)))
                    x = to_execute.pop(0)[-1]

                    executed = worklist_execute(self.server, prompt, self.outputs, x, extra_data, prompt_id, self.outputs_ui)
            except Exception as e:
                if isinstance(e, comfy.model_management.InterruptProcessingException):
                    print("Processing interrupted")
                else:
                    message = str(traceback.format_exc())
                    print(message)
                    if self.server.client_id is not None:
                        self.server.send_sync("execution_error", {"message": message, "prompt_id": prompt_id},
                                              self.server.client_id)

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
            finally:
                for x in executed:
                    self.old_prompt[x] = copy.deepcopy(prompt[x])
                self.server.last_node_id = None
                if self.server.client_id is not None:
                    self.server.send_sync("executing", {"node": None, "prompt_id": prompt_id}, self.server.client_id)

        print("Prompt executed in {:.2f} seconds".format(time.perf_counter() - execution_start_time))
        gc.collect()
        comfy.model_management.soft_empty_cache()
