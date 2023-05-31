# ComfyUI-Workflow-Component
This is a side project to experiment with using workflows as components.
This extension, as an extension of the Proof of Concept, lacks many features, is unstable, and has many parts that do not function properly.
There is a high possibility that the existing components created may not be compatible during the update process.

## How To Build Component
![component-build](misc/component-build.png)

* Through the ComponentBuilder under the ComponentInput node, specify the input interface of the component, and specify the output interface of the component through the ComponentOutput node.
* The slot name of the ComponentInput/Output node is used as the external interface name of the component.
* The order of the interface is determined by sorting the titles of the nodes in ascending order.

![component-menu](misc/menu.png)

* Once all the component workflows have been created, you can save them through the "SaveAsComponent" option in the menu. The file extension will be .component.json.


## How To Use Component
![component-files](misc/component-files.png)

* If you place the .components.json file, which is stored in the "components" subdirectory, and then restart ComfyUI, you will be able to add the corresponding component that starts with "##."
![component-menu2](misc/menu2.png)

![component-use](misc/component-use.png)


# Requirements
* Dynamic component loading relies on this PR
  * https://github.com/comfyanonymous/ComfyUI/pull/716


## Todo
- [x] Default interface name
- [x] Support of refresh combo (ex. ckpt, images, lora, ...)
- [x] Hot loading
- [ ] used components must be included into workflow
  - [x] Save .json
  - [ ] Load .json
  - [ ] Save .png
  - [ ] Load .png
- [ ] Efficient traversal
- [ ] Better internal error message
- [ ] Report missing nodes in components when component is loaded

## Credit

ComfyUI/[ComfyUI](https://github.com/comfyanonymous/ComfyUI) - A powerful and modular stable diffusion GUI.
pythongosssss/[ComfyUI-WD14-Tagger](https://github.com/pythongosssss/ComfyUI-WD14-Tagger) - A very cool badge-style progress came from here.