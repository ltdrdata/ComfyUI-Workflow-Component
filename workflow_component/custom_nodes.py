class AnyType(str):
    def __ne__(self, __value: object) -> bool:
        return False

any = AnyType("*")


class ExecutionOneOf:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                        "input1": ("*", ),
            },
            "optional": {
                        "input2": ("*", ),
                        "input3": ("*", ),
                        "input4": ("*", ),
                        "input5": ("*", ),
                     },
               }

    RETURN_TYPES = ("*", )
    RETURN_NAMES = ("output", )
    FUNCTION = "doit"

    CATEGORY = "execution"

    def doit(s, **kwargs):
        if 'input1' in kwargs and kwargs['input1'] is not None:
            return (kwargs['input1'], )
        elif 'input2' in kwargs and kwargs['input2'] is not None:
            return (kwargs['input2'], )
        elif 'input3' in kwargs and kwargs['input3'] is not None:
            return (kwargs['input3'],)
        elif 'input4' in kwargs and kwargs['input4'] is not None:
            return (kwargs['input4'],)
        elif 'input5' in kwargs and kwargs['input5'] is not None:
            return (kwargs['input5'],)
        else:
            return None


class ExecutionSwitch:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
                        "select": ("INT", {"default": 1, "min": 0, "max": 5}),
                        "input1": ("*", ),
                    },
                "optional": {
                        "input2_opt": ("*", ),
                        "input3_opt": ("*", ),
                        "input4_opt": ("*", ),
                        "input5_opt": ("*", ),
                    }
                }

    RETURN_TYPES = ("*", "*", "*", "*", "*", )
    RETURN_NAMES = ("output1", "output2", "output3", "output4", "output5", )
    FUNCTION = "doit"

    CATEGORY = "execution"

    def doit(s, select, input1, input2_opt=None, input3_opt=None, input4_opt=None, input5_opt=None):
        if select == 1:
            return input1, None, None, None, None
        elif select == 2:
            return None, input2_opt, None, None, None
        elif select == 3:
            return None, None, input3_opt, None, None
        elif select == 4:
            return None, None, None, input4_opt, None
        elif select == 5:
            return None, None, None, None, input5_opt
        else:
            return None, None, None, None, None


class ExecutionControlString:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
                        "A": ("STRING", {"default": ""}),
                        "B_STR": ("*",),
                        "condition_kind": (["A = B", "A != B", "A in B", "A not in B"], ),
                        "pass_value": ("*", )
                    },
                }

    RETURN_TYPES = ("*", )
    RETURN_NAMES = ("pass_value", )
    FUNCTION = "doit"

    CATEGORY = "execution"

    def doit(s, A, B_STR, condition_kind, pass_value):
        if (condition_kind == "A = B" and A == B_STR) or \
                (condition_kind == "A != B" and A != B_STR) or \
                (condition_kind == "A in B" and A in B_STR) or \
                (condition_kind == "A not in B" and A not in B_STR):
            return (pass_value, )
        else:
            return None


class ComboToString:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
                        "spec": ("STRING", {"multiline": True}),
                    },
                }

    RETURN_TYPES = ("*", )
    FUNCTION = "doit"

    CATEGORY = "execution"

    def doit(s, spec):
        return None


class LoopControl:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
                        "loop_condition": ("LOOP_CONDITION", ),
                        "initial_input": ("*", ),
                        "loopback_input": ("*", ),
                    },
                }

    RETURN_TYPES = ("*", )
    FUNCTION = "doit"

    CATEGORY = "execution"

    def doit(s, **kwargs):
        if 'loopback_input' not in kwargs or kwargs['loopback_input'] is None:
            current = kwargs['initial_input']
        else:
            current = kwargs['loopback_input']

        result = kwargs['loop_condition'].get_next(kwargs['initial_input'], current)
        if result is None:
            return None
        else:
            return (result, )


class CounterCondition:
    def __init__(self, value):
        self.max = value
        self.current = 0

    def get_next(self, initial_value, value):
        print(f"CounterCondition: {self.current}/{self.max}")

        self.current += 1
        if self.current == 1:
            return initial_value
        elif self.current <= self.max:
            return value
        else:
            return None


class LoopCounterCondition:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
                        "count": ("INT", {"default": 1, "min": 0, "max": 9999999, "step": 1}),
                        "trigger": (["A", "B"], )
                    },
                }

    RETURN_TYPES = ("LOOP_CONDITION", )
    FUNCTION = "doit"

    CATEGORY = "execution"

    def doit(s, count, trigger):
        return (CounterCondition(count), )


class TensorToCPU:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"tensor": ("*", ), }, }

    RETURN_TYPES = ("*", )
    FUNCTION = "doit"

    CATEGORY = "execution"

    def doit(self, tensor):
        return (tensor.cpu(), )


# To facilitate the use of multiple inputs as loopback inputs, InputZip and InputUnzip are provided.
class InputZip:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
                        "input1": ("*", ),
                        "input2": ("*", ),
                    },
                }

    CATEGORY = "execution"

    RETURN_TYPES = ("ZIP", )
    FUNCTION = "doit"

    def doit(s, input1, input2):
        return ((input1, input2), )


class InputUnzip:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
                        "zipped_input": ("ZIP", ),
                    },
                }

    RETURN_TYPES = ("*", "*", )
    FUNCTION = "doit"

    CATEGORY = "execution"

    def doit(s, zipped_input):
        input1, input2 = zipped_input
        return (input1, input2, )

class OptionalTest:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {},
            "optional": {
                        "option1": ("*", ),
                        "option2": ("*", ),
                    },
                }

    RETURN_TYPES = ("STRING", )
    FUNCTION = "doit"

    CATEGORY = "_for_testing"

    def doit(s, option1=None, option2=None):
        return ("ABC", )


# New implementation based on lazy execution

class ComponentInput:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "name": ("STRING", {"multiline": False}),
                "data_type": ("STRING", {"multiline": False, "default": "IMAGE"}),
                "extra_args": ("STRING", {"multiline": True}),
                "explicit_input_order": ("INT", {"default": 0, "min": 0, "max": 1000, "step": 1}),
                "is_optional": ("BOOLEAN", {"default": False, "label_on": "optional", "label_off": "required"}),
            },
            "optional": {
                "default_value": (AnyType("*"),),
            },
        }

    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("input",)
    FUNCTION = "component_input"

    CATEGORY = "ComponentBuilder"

    def component_input(self, name, data_type, extra_args, explicit_input_order, is_optional, default_value=None):
        return (default_value,)


class ComponentOutput:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "name": ("STRING", {"multiline": False}),
                "data_type": ("STRING", {"multiline": False, "default": "IMAGE"}),
                "index": ("INT", {"default": 0, "min": 0, "max": 1000, "step": 1}),
                "value": (AnyType("*"),),
            },
        }

    RETURN_TYPES = (AnyType("*"),)
    FUNCTION = "component_output"

    CATEGORY = "ComponentBuilder"

    def component_output(self, index, data_type, name, value):
        return (value,)


class ComponentMetadata:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "name": ("STRING", {"multiline": False}),
                "always_output": ([False, True],),
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "nop"

    CATEGORY = "ComponentBuilder"

    def nop(self, name):
        return {}