from .imagerefiner import ir_objs

class IR_Input:
    @classmethod
    def INPUT_TYPES(self):
        return {"required": {'prompt_id': ("STRING",), 'key': ("STRING",)}}

    RETURN_TYPES = ("*",)
    FUNCTION = "doit"

    CATEGORY = "ComponentBuilder/__internal"

    def doit(self, prompt_id, key):
        res = ir_objs[prompt_id][key]
        return (res,)


class IR_Output:
    @classmethod
    def INPUT_TYPES(self):
        return {"required": {'prompt_id': ("STRING",), 'slot': ("INT",), 'value': ("*",)}}

    RETURN_TYPES = ()
    FUNCTION = "doit"

    CATEGORY = "ComponentBuilder/__internal"

    def doit(self, prompt_id, slot, value):
        ir_objs[prompt_id].add_output(slot, value)
        return ()
