import { app } from "/scripts/app.js";
import { $el } from "/scripts/ui.js";
import { api } from "/scripts/api.js";

class ProgressBadge {
	constructor() {
		if (!window.__progress_badge__) {
			window.__progress_badge__ = Symbol("__progress_badge__");
		}
		this.symbol = window.__progress_badge__;
	}

	getState(node) {
		return node[this.symbol] || {};
	}

	setState(node, state) {
		node[this.symbol] = state;
		app.canvas.setDirty(true);
	}

	addStatusHandler(nodeType) {
		if (nodeType[this.symbol]?.statusTagHandler) {
			return;
		}
		if (!nodeType[this.symbol]) {
			nodeType[this.symbol] = {};
		}
		nodeType[this.symbol] = {
			statusTagHandler: true,
		};

		api.addEventListener("component/update_status", ({ detail }) => {
			let { node, progress, text } = detail;
			const n = app.graph.getNodeById(+(node || app.runningNodeId));
			if (!n) return;
			const state = this.getState(n);
			state.status = Object.assign(state.status || {}, { progress: text ? progress : null, text: text || null });
			this.setState(n, state);
		});

		const self = this;
		const onDrawForeground = nodeType.prototype.onDrawForeground;
		nodeType.prototype.onDrawForeground = function (ctx) {
			const r = onDrawForeground?.apply?.(this, arguments);
			const state = self.getState(this);
			if (!state?.status?.text) {
				return r;
			}

			const { fgColor, bgColor, text, progress, progressColor } = { ...state.status };

			ctx.save();
			ctx.font = "12px sans-serif";
			const sz = ctx.measureText(text);
			ctx.fillStyle = bgColor || "dodgerblue";
			ctx.beginPath();
			ctx.roundRect(0, -LiteGraph.NODE_TITLE_HEIGHT - 20, sz.width + 12, 20, 5);
			ctx.fill();

			if (progress) {
				ctx.fillStyle = progressColor || "green";
				ctx.beginPath();
				ctx.roundRect(0, -LiteGraph.NODE_TITLE_HEIGHT - 20, (sz.width + 12) * progress, 20, 5);
				ctx.fill();
			}

			ctx.fillStyle = fgColor || "#fff";
			ctx.fillText(text, 6, -LiteGraph.NODE_TITLE_HEIGHT - 6);
			ctx.restore();
			return r;
		};
	}
}

app.registerExtension({
	name: "Comfy.WorkflowComponent",

	async setup() {
		const menu = document.querySelector(".comfy-menu");

		const saveComponentButton = document.createElement("button");
		saveComponentButton.textContent = "Save As Component";
		saveComponentButton.onclick = async () => {
					let filename = "workflow.component.json";

					filename = prompt("Save workflow as:", filename);
					if (!filename) return;
					if (!filename.toLowerCase().endsWith(".component.json")) {
						filename += ".json";
					}

					const p = await app.graphToPrompt();
					p.workflow.output = p.output;

					const json = JSON.stringify(p.workflow, null, 2); // convert the data to a JSON string
					const blob = new Blob([json], { type: "application/json" });
					const url = URL.createObjectURL(blob);
					const a = $el("a", {
						href: url,
						download: filename,
						style: { display: "none" },
						parent: document.body,
					});
					a.click();
					setTimeout(function () {
						a.remove();
						window.URL.revokeObjectURL(url);
					}, 0);
				};

		const loadComponentButton = document.createElement("button");

		const fileInput = $el("input", {
			id: "comfy-file-input",
			type: "file",
			accept: ".component.json",
			style: { display: "none" },
			multiple: true,
			parent: document.body,
			onchange: () => {
				var refreshFlag = false;
				for(let i in fileInput.files) {
					const target_file = fileInput.files[i];
					const filename = target_file.name;
					const reader = new FileReader();
					reader.onload = async () => {
						const body = new FormData();
						body.append("filename", filename);
						body.append("content", reader.result);

						const resp = await fetch(`/component/load`, {
											method: 'POST',
											body: body,
										});

						const data = await resp.json();
						console.log(data['node_name']);

						if(!data['already_loaded']) {
	//						const uri = encodeURIComponent(`## ${data['node_name']}`)
	//						const node_info = await fetch(`object_info/${uri}`, { cache: "no-store" });
	//						const def = await node_info.json();
							refreshFlag = true;
						}

						if (i == fileInput.files.length - 1 && refreshFlag) {
							const result = confirm("To use the new component, you need to refresh the page. Would you like to proceed with the refresh?");
							if(result) {
								location.reload();
							}
						}
					};

					reader.readAsText(target_file);
				}
			},
		});

		loadComponentButton.textContent = "Load Component";
		loadComponentButton.onclick = () => {
				fileInput.value = '';
				fileInput.click();
			}

		menu.append(saveComponentButton);
		menu.append(loadComponentButton);
	},
	registerCustomNodes() {
		class ComponentOutputNode {
			constructor() {
				this.addInput("rename after connect", "*");

				this.onConnectionsChange = function (type, index, connected, link_info) {
					if (type === LiteGraph.INPUT) {			  
					let inputType = null;
					let inputName = null;
					const input = this.inputs ? this.inputs[0].link || null : null;
					let node = null;
					let originSlot = null;

					// Get input type
					if (input !== null) {
						const link = app.graph.links[input];
						const origin = link.origin_id;
						originSlot = link.origin_slot;

						node = app.graph.getNodeById(origin);
						if (node) {
							inputType = node.outputs[originSlot].type;
							inputName = node.outputs[originSlot].label?node.outputs[originSlot].label:null;
						}					  
					} else {
					  // No inputs connected
					}
				  
					const displayType = inputType || "*";
					const color = LGraphCanvas.link_type_colors[displayType];
					
				 	 // Update output properties
					this.inputs[0].type = inputType;
					this.__inputType = displayType;

					// skip if name is assigned, already
					if(this.inputs[0].name == "rename after connect") {
						this.inputs[0].name = inputName || inputType || "rename after connect";
						this.inputs[0].label = inputName;
					}
				  
					const link = app.graph.links[this.inputs[0]];
				  
					if (node !== null) {
						node.outputs[originSlot].color = color;
					}
				  };
				  
				this.serialize_widgets = true;
				this.isVirtualNode = false;
			}
		}};

		class ComponentInputNode {
			constructor() {
				this.addOutput("rename after connect", "*");

				this.onConnectionsChange = function (type, index, connected, link_info) {
					if (connected && type === LiteGraph.OUTPUT) {
					// Get unique output types from connected links
					  const types = new Set(
						this.outputs[0].links
						  .map((l) => app.graph.links[l].type)
						  .filter((t) => t !== "*")
					  );
				  	// If there are multiple output types, disconnect previous links except the last one
					  if (types.size > 1) {
						for (let i = 0; i < this.outputs[0].links.length - 1; i++) {
						  const linkId = this.outputs[0].links[i];
						  const link = app.graph.links[linkId];
						  const node = app.graph.getNodeById(link.target_id);
						  node.disconnectInput(link.target_slot);
						}
					  }
					}
				  
					let outputType = null;
					let outputName = null;
					const outputs = this.outputs ? this.outputs[0].links || [] : [];
				  	
					// Iterate through output links to determine the output type
					if (outputs.length) {
					  for (const linkId of outputs) {
						const link = app.graph.links[linkId];
				  
						if (!link) continue;
				  
						const node = app.graph.getNodeById(link.target_id);
						outputType =
						  node.inputs &&
						  node.inputs[link?.target_slot] &&
						  node.inputs[link.target_slot].type
							? node.inputs[link.target_slot].type
							: null;

						outputName =
						  node.inputs &&
						  node.inputs[link?.target_slot] &&
						  node.inputs[link.target_slot].name
							? node.inputs[link.target_slot].name
							: null;
					  }
					} else {
					  // No outputs
					}
				  
					const displayType = outputType || "*";
					const color = LGraphCanvas.link_type_colors[displayType];

				 	 // Update output properties
					this.outputs[0].type = outputType;
					this.__outputType = displayType;
					this.outputs[0].name = outputName || "*";
				  
					const link = app.graph.links[this.outputs[0]];
				  
					if (link) {
					  link.color = color;
					}
				  };

				this.serialize_widgets = true;
				this.isVirtualNode = false;
			}
		}

		class ComponentInputOptionalNode extends ComponentInputNode {
		}

		LiteGraph.registerNodeType(
			"ComponentInput",
			Object.assign(ComponentInputNode, {
				title: "Component Input",
			})
		);

		LiteGraph.registerNodeType(
			"ComponentInputOptional",
			Object.assign(ComponentInputOptionalNode, {
				title: "Component Input (OPT)",
			})
		);

		LiteGraph.registerNodeType(
			"ComponentOutput",
			Object.assign(ComponentOutputNode, {
				title: "Component Output",
			})
		);

		ComponentOutputNode.category = "ComponentBuilder";
		ComponentInputNode.category = "ComponentBuilder";
	},
});


const progressBadge = new ProgressBadge();
app.registerExtension({
	name: "Comfy.WorkflowComponent.ProgressBadge",
	async beforeRegisterNodeDef(nodeType, nodeData, app) {
		if (nodeData.name.startsWith("##")) {
			progressBadge.addStatusHandler(nodeType);
		}
	}
});
