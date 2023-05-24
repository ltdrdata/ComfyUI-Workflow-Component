# Base Component
class ComponentInput:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {},
            "optional": {"#": ("##IS_COMPONENT_INPUT",), }
        }

    CATEGORY = "ComponentBuilder/Input"
    FUNCTION = "doit"

    def doit(s, *args, **kwargs):
        pass


class ComponentOutput:
    CUSTOM_OUTPUT_TYPE = ""

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {"output": (s.CUSTOM_OUTPUT_TYPE, ), },
            "optional": {"#": ("##IS_COMPONENT_OUTPUT",), }
        }

    RETURN_TYPES = ()
    FUNCTION = "doit"

    CATEGORY = "ComponentBuilder/Output"

    def doit(s, output, *args, **kwargs):
        return (output, )


# Derived Components
class ComponentInputImage(ComponentInput):
    RETURN_TYPES = ("IMAGE",)


class ComponentInputLatent(ComponentInput):
    RETURN_TYPES = ("LATENT",)


class ComponentInputModel(ComponentInput):
    RETURN_TYPES = ("MODEL", )


class ComponentInputClip(ComponentInput):
    RETURN_TYPES = ("CLIP", )


class ComponentInputVAE(ComponentInput):
    RETURN_TYPES = ("VAE", )


class ComponentInputString(ComponentInput):
    RETURN_TYPES = ("STRING", )


class ComponentInputFloat(ComponentInput):
    RETURN_TYPES = ("FLOAT", )


class ComponentInputInt(ComponentInput):
    RETURN_TYPES = ("INT", )


class ComponentOutputImage(ComponentOutput):
    CUSTOM_OUTPUT_TYPE = "IMAGE"


class ComponentOutputLatent(ComponentOutput):
    CUSTOM_OUTPUT_TYPE = "LATENT"

