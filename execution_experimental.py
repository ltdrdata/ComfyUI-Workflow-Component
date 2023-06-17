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
from execution import map_node_over_list, format_value, full_type_name
from queue import Queue


DEBUG_FLAG = True


def print_dbg(x):
    if DEBUG_FLAG:
        print(f"[DBG] {x()}")


# To handling virtual node
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


def get_output_data(obj, input_data_all):
    results = []
    uis = []
    return_values = map_node_over_list(obj, input_data_all, obj.FUNCTION, allow_interrupt=True)

    for r in return_values:
        if isinstance(r, dict):
            if 'ui' in r:
                uis.append(r['ui'])
            if 'result' in r:
                results.append(r['result'])
        else:
            results.append(r)

    output = []
    if len(results) > 0 and results[0] is not None:
        # check which outputs need concatenating
        output_is_list = [False] * len(results[0])
        if hasattr(obj, "OUTPUT_IS_LIST"):
            output_is_list = obj.OUTPUT_IS_LIST

        # merge node execution results
        for i, is_list in zip(range(len(results[0])), output_is_list):
            if is_list:
                output.append([x for o in results for x in o[i]])
            else:
                output.append([o[i] for o in results])

    ui = dict()
    if len(uis) > 0:
        ui = {k: [y for x in uis for y in x[k]] for k in uis[0].keys()}
    return output, ui


def get_input_data(inputs, class_def, unique_id, outputs={}, prompt={}, extra_data={}):
    valid_inputs = class_def.INPUT_TYPES()
    input_data_all = {}
    for x in inputs:
        input_data = inputs[x]
        if isinstance(input_data, list):
            input_unique_id = input_data[0]
            output_index = input_data[1]
            if input_unique_id in outputs and len(outputs[input_unique_id]) == 0:
                input_data_all[x] = []
            else:
                if class_def.__name__ != "LoopControl" and class_def.__name__ != "ExecutionOneOf":
                    if input_unique_id not in outputs or outputs[input_unique_id][input_data[1]] == [None]:
                        return None

                if input_unique_id in outputs and outputs[input_unique_id][input_data[1]] != [None]:
                    obj = outputs[input_unique_id][output_index]
                    input_data_all[x] = obj
        else:
            if ("required" in valid_inputs and x in valid_inputs["required"]) or ("optional" in valid_inputs and x in valid_inputs["optional"]):
                input_data_all[x] = [input_data]

    if "hidden" in valid_inputs:
        h = valid_inputs["hidden"]
        for x in h:
            if h[x] == "PROMPT":
                input_data_all[x] = [prompt]
            if h[x] == "EXTRA_PNGINFO":
                if "extra_pnginfo" in extra_data:
                    input_data_all[x] = [extra_data['extra_pnginfo']]
            if h[x] == "UNIQUE_ID":
                input_data_all[x] = [unique_id]
    return input_data_all


def exception_helper(unique_id, input_data_all, executed, outputs, task):
    try:
        task()
        return None
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


def is_incomplete_input_slots(class_def, inputs, outputs):
    required_inputs = set(class_def.INPUT_TYPES().get("required", []))

    if len(required_inputs - inputs.keys()) > 0:
        return True

    # "ExecutionOneof" node is a special node that allows only one of the multiple execution paths to be reached and passed through.
    if class_def.__name__ == "ExecutionOneOf":
        for x in inputs:
            input_data = inputs[x]

            if isinstance(input_data, list):
                input_unique_id = input_data[0]
                if input_unique_id in outputs and outputs[input_unique_id][input_data[1]] != [None]:
                    return False

        return True

    # The "LoopControl" is a special node that can be executed even without loopback_input.
    if class_def.__name__ == "LoopControl":
        inputs = {
                    'loop_condition': inputs['loop_condition'],
                    'initial_input': inputs['initial_input'],
                  }

    for x in inputs:
        input_data = inputs[x]

        if isinstance(input_data, list):
            input_unique_id = input_data[0]
            if input_unique_id not in outputs or \
                    len(outputs[input_unique_id]) == 0 or \
                    outputs[input_unique_id][input_data[1]] == [None]:
                return True

    return False


def get_class_def(prompt, unique_id):
    if 'class_type' not in prompt[unique_id]:
        class_def = DummyNode
    else:
        class_type = prompt[unique_id]['class_type']
        class_def = nodes.NODE_CLASS_MAPPINGS[class_type]

    return class_def


def get_next_nodes_map(prompt):
    next_nodes = {}
    for key, value in prompt.items():
        inputs = value['inputs']

        for input_data in inputs.values():
            if isinstance(input_data, list):
                input_unique_id = input_data[0]
                if input_unique_id in next_nodes:
                    next_nodes[input_unique_id].add(key)
                else:
                    next_nodes[input_unique_id] = {key}
    return next_nodes


def worklist_execute(server, prompt, outputs, extra_data, prompt_id, outputs_ui, to_execute, next_nodes):
    worklist = Queue()
    executed = set()
    will_execute = {}

    def add_work_high(item):
        worklist.put(item)
        cnt = will_execute.get(item, 0)
        will_execute[item] = cnt + 1

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

    def apply_priority(items):
        high_priority = []
        low_priority = []

        for cur_id, cur_class_def in items:
            if cur_class_def.__name__ == "LoopControl":
                low_priority.append(cur_id)
            elif cur_class_def.RETURN_TYPES == ():
                high_priority.append(cur_id)
            else:
                low_priority.append(cur_id)

        return (high_priority, low_priority)

    def get_progress():
        total = len(executed)+len(will_execute.keys())
        return len(executed)/total

    # init seeds: the nodes that have their output not erased in the input slot are the seeds.
    for unique_id in to_execute:
        inputs = prompt[unique_id]['inputs']
        class_def = get_class_def(prompt, unique_id)

        if unique_id in outputs:
            continue

        if is_incomplete_input_slots(class_def, inputs, outputs):
            continue

        input_data_all = None

        def task():
            nonlocal input_data_all
            input_data_all = get_input_data(inputs, class_def, unique_id, outputs, prompt, extra_data)

            if input_data_all is None:
                return

            if not is_incomplete_input_slots(class_def, prompt[unique_id]['inputs'], outputs):
                add_work(unique_id)  # add to seed if all input is properly provided

        result = exception_helper(unique_id, input_data_all, executed, outputs, task)
        if result is not None:
            return result  # error state

    while not worklist.empty():
        unique_id = get_work()

        inputs = prompt[unique_id]['inputs']
        class_def = get_class_def(prompt, unique_id)

        print_dbg(lambda: f"work: {unique_id} ({class_def.__name__}) / worklist: {list(worklist.queue)}")

        input_data_all = None

        def task():
            nonlocal input_data_all
            input_data_all = get_input_data(inputs, class_def, unique_id, outputs, prompt, extra_data)

            if server.client_id is not None:
                server.last_node_id = unique_id
                server.send_sync("executing", {"node": unique_id, "prompt_id": prompt_id, "progress": get_progress()},
                                 server.client_id)
            obj = class_def()

            output_data, output_ui = get_output_data(obj, input_data_all)

            outputs[unique_id] = output_data
            if len(output_ui) > 0:
                outputs_ui[unique_id] = output_ui
                if server.client_id is not None:
                    server.send_sync("executed", {"node": unique_id, "output": output_ui, "prompt_id": prompt_id},
                                     server.client_id)
            executed.add(unique_id)

        result = exception_helper(unique_id, input_data_all, executed, outputs, task)
        if result is not None:
            return result  # error state
        else:
            if unique_id in next_nodes:
                if class_def.__name__ == "LoopControl" and outputs[unique_id] == [[None]]:
                    continue

                candidates = []
                for next_node in next_nodes[unique_id]:
                    if next_node in to_execute:
                        # If all input slots are not completed, do not add to the work.
                        # This prevents duplicate entries of the same work in the worklist.
                        # For loop support, it is important to fire only once when the input slot is completed.
                        next_class_def = get_class_def(prompt, next_node)
                        if not is_incomplete_input_slots(next_class_def, prompt[next_node]['inputs'], outputs):
                            candidates.append((next_node, next_class_def))

                high_priority_works, low_priority_works = apply_priority(candidates)

                for next_node in high_priority_works:
                    add_work_high(next_node)

                for next_node in low_priority_works:
                    add_work(next_node)

    return executed, True, None, None


def worklist_will_execute(prompt, outputs, worklist):
    visited = set()

    will_execute = []

    while worklist:
        unique_id = str(worklist.pop())

        if unique_id in visited:  # to avoid infinite loop and redundant processing
            continue
        else:
            visited.add(unique_id)

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


def worklist_output_delete_if_changed(prompt, old_prompt, outputs, next_nodes):
    worklist = []
    deleted = set()

    # init seeds
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

        new_works = next_nodes.get(unique_id, [])
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

            next_nodes = get_next_nodes_map(prompt)
            worklist_output_delete_if_changed(prompt, self.old_prompt, self.outputs, next_nodes)

            current_outputs = set(self.outputs.keys())
            for x in list(self.outputs_ui.keys()):
                if x not in current_outputs:
                    d = self.outputs_ui.pop(x)
                    del d

            if self.server.client_id is not None:
                self.server.send_sync("execution_cached", {"nodes": list(current_outputs), "prompt_id": prompt_id},
                                      self.server.client_id)

            to_execute = worklist_will_execute(prompt, self.outputs, execute_outputs)

            # This call shouldn't raise anything if there's an error deep in
            # the actual SD code, instead it will report the node where the
            # error was raised
            executed, success, error, ex = worklist_execute(self.server, prompt, self.outputs, extra_data, prompt_id,
                                                            self.outputs_ui, to_execute, next_nodes)
            if success is not True:
                self.handle_execution_error(prompt_id, prompt, current_outputs, executed, error, ex)

            for x in executed:
                self.old_prompt[x] = copy.deepcopy(prompt[x])
            self.server.last_node_id = None
            if self.server.client_id is not None:
                self.server.send_sync("executing", {"node": None, "prompt_id": prompt_id}, self.server.client_id)

        print("Prompt executed in {:.2f} seconds".format(time.perf_counter() - execution_start_time))
        gc.collect()
        comfy.model_management.soft_empty_cache()


def validate_prompt(prompt):
    outputs = set()
    for x in prompt:
        class_ = nodes.NODE_CLASS_MAPPINGS[prompt[x]['class_type']]
        if hasattr(class_, 'OUTPUT_NODE') and class_.OUTPUT_NODE == True:
            outputs.add(x)

    if len(outputs) == 0:
        error = {
            "type": "prompt_no_outputs",
            "message": "Prompt has no outputs",
            "details": "",
            "extra_info": {}
        }
        return (False, error, [], [])

    good_outputs = set()
    errors = []
    node_errors = {}
    validated = {}
    for o in outputs:
        valid = False
        reasons = []
        try:
            m = validate_inputs(prompt, o, validated)
            valid = m[0]
            reasons = m[1]
        except Exception as ex:
            typ, _, tb = sys.exc_info()
            valid = False
            exception_type = full_type_name(typ)
            reasons = [{
                "type": "exception_during_validation",
                "message": "Exception when validating node",
                "details": str(ex),
                "extra_info": {
                    "exception_type": exception_type,
                    "traceback": traceback.format_tb(tb)
                }
            }]
            validated[o] = (False, reasons, o)

        if valid is True:
            good_outputs.add(o)
        else:
            print(f"Failed to validate prompt for output {o}:")
            if len(reasons) > 0:
                print("* (prompt):")
                for reason in reasons:
                    print(f"  - {reason['message']}: {reason['details']}")
            errors += [(o, reasons)]
            for node_id, result in validated.items():
                valid = result[0]
                reasons = result[1]
                # If a node upstream has errors, the nodes downstream will also
                # be reported as invalid, but there will be no errors attached.
                # So don't return those nodes as having errors in the response.
                if valid is not True and len(reasons) > 0:
                    if node_id not in node_errors:
                        class_type = prompt[node_id]['class_type']
                        node_errors[node_id] = {
                            "errors": reasons,
                            "dependent_outputs": [],
                            "class_type": class_type
                        }
                        print(f"* {class_type} {node_id}:")
                        for reason in reasons:
                            print(f"  - {reason['message']}: {reason['details']}")
                    node_errors[node_id]["dependent_outputs"].append(o)
            print("Output will be ignored")

    if len(good_outputs) == 0:
        errors_list = []
        for o, errors in errors:
            for error in errors:
                errors_list.append(f"{error['message']}: {error['details']}")
        errors_list = "\n".join(errors_list)

        error = {
            "type": "prompt_outputs_failed_validation",
            "message": "Prompt outputs failed validation",
            "details": errors_list,
            "extra_info": {}
        }

        return (False, error, list(good_outputs), node_errors)

    return (True, None, list(good_outputs), node_errors)

def validate_inputs(prompt, item, validated, visited=set()):
    if item in visited:
        return (True, [], item)
    else:
        visited.add(item)

    unique_id = item
    if unique_id in validated:
        return validated[unique_id]

    inputs = prompt[unique_id]['inputs']
    class_type = prompt[unique_id]['class_type']
    obj_class = nodes.NODE_CLASS_MAPPINGS[class_type]

    class_inputs = obj_class.INPUT_TYPES()
    required_inputs = class_inputs['required']

    errors = []
    valid = True

    for x in required_inputs:
        if x not in inputs:
            error = {
                "type": "required_input_missing",
                "message": "Required input is missing",
                "details": f"{x}",
                "extra_info": {
                    "input_name": x
                }
            }
            errors.append(error)
            continue

        val = inputs[x]
        info = required_inputs[x]
        type_input = info[0]
        if isinstance(val, list):
            if len(val) != 2:
                error = {
                    "type": "bad_linked_input",
                    "message": "Bad linked input, must be a length-2 list of [node_id, slot_index]",
                    "details": f"{x}",
                    "extra_info": {
                        "input_name": x,
                        "input_config": info,
                        "received_value": val
                    }
                }
                errors.append(error)
                continue

            o_id = val[0]
            o_class_type = prompt[o_id]['class_type']
            r = nodes.NODE_CLASS_MAPPINGS[o_class_type].RETURN_TYPES
            if r[val[1]] != type_input and r[val[1]] != '*' and type_input != '*':
                received_type = r[val[1]]
                details = f"{x}, {received_type} != {type_input}"
                error = {
                    "type": "return_type_mismatch",
                    "message": "Return type mismatch between linked nodes",
                    "details": details,
                    "extra_info": {
                        "input_name": x,
                        "input_config": info,
                        "received_type": received_type,
                        "linked_node": val
                    }
                }
                errors.append(error)
                continue
            try:
                r = validate_inputs(prompt, o_id, validated, visited)
                if r[0] is False:
                    # `r` will be set in `validated[o_id]` already
                    valid = False
                    continue
            except Exception as ex:
                typ, _, tb = sys.exc_info()
                valid = False
                exception_type = full_type_name(typ)
                reasons = [{
                    "type": "exception_during_inner_validation",
                    "message": "Exception when validating inner node",
                    "details": str(ex),
                    "extra_info": {
                        "input_name": x,
                        "input_config": info,
                        "exception_message": str(ex),
                        "exception_type": exception_type,
                        "traceback": traceback.format_tb(tb),
                        "linked_node": val
                    }
                }]
                validated[o_id] = (False, reasons, o_id)
                continue
        else:
            try:
                if type_input == "INT":
                    val = int(val)
                    inputs[x] = val
                if type_input == "FLOAT":
                    val = float(val)
                    inputs[x] = val
                if type_input == "STRING":
                    val = str(val)
                    inputs[x] = val
            except Exception as ex:
                error = {
                    "type": "invalid_input_type",
                    "message": f"Failed to convert an input value to a {type_input} value",
                    "details": f"{x}, {val}, {ex}",
                    "extra_info": {
                        "input_name": x,
                        "input_config": info,
                        "received_value": val,
                        "exception_message": str(ex)
                    }
                }
                errors.append(error)
                continue

            if len(info) > 1:
                if "min" in info[1] and val < info[1]["min"]:
                    error = {
                        "type": "value_smaller_than_min",
                        "message": "Value {} smaller than min of {}".format(val, info[1]["min"]),
                        "details": f"{x}",
                        "extra_info": {
                            "input_name": x,
                            "input_config": info,
                            "received_value": val,
                        }
                    }
                    errors.append(error)
                    continue
                if "max" in info[1] and val > info[1]["max"]:
                    error = {
                        "type": "value_bigger_than_max",
                        "message": "Value {} bigger than max of {}".format(val, info[1]["max"]),
                        "details": f"{x}",
                        "extra_info": {
                            "input_name": x,
                            "input_config": info,
                            "received_value": val,
                        }
                    }
                    errors.append(error)
                    continue

            if hasattr(obj_class, "VALIDATE_INPUTS"):
                input_data_all = get_input_data(inputs, obj_class, unique_id)
                #ret = obj_class.VALIDATE_INPUTS(**input_data_all)
                ret = map_node_over_list(obj_class, input_data_all, "VALIDATE_INPUTS")
                for i, r in enumerate(ret):
                    if r is not True:
                        details = f"{x}"
                        if r is not False:
                            details += f" - {str(r)}"

                        error = {
                            "type": "custom_validation_failed",
                            "message": "Custom validation failed for node",
                            "details": details,
                            "extra_info": {
                                "input_name": x,
                                "input_config": info,
                                "received_value": val,
                            }
                        }
                        errors.append(error)
                        continue
            else:
                if isinstance(type_input, list):
                    if val not in type_input:
                        input_config = info
                        list_info = ""

                        # Don't send back gigantic lists like if they're lots of
                        # scanned model filepaths
                        if len(type_input) > 20:
                            list_info = f"(list of length {len(type_input)})"
                            input_config = None
                        else:
                            list_info = str(type_input)

                        error = {
                            "type": "value_not_in_list",
                            "message": "Value not in list",
                            "details": f"{x}: '{val}' not in {list_info}",
                            "extra_info": {
                                "input_name": x,
                                "input_config": input_config,
                                "received_value": val,
                            }
                        }
                        errors.append(error)
                        continue

    if len(errors) > 0 or valid is not True:
        ret = (False, errors, unique_id)
    else:
        ret = (True, [], unique_id)

    validated[unique_id] = ret
    return ret
