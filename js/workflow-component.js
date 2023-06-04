import { app } from "/scripts/app.js";
import { $el } from "/scripts/ui.js";
import { api } from "/scripts/api.js";
import { getPngMetadata, importA1111, getLatentMetadata } from "/scripts/pnginfo.js";

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

async function loadComponentWorkflows() {
    if(!app.loaded_components) {
        app.loaded_components = {};
    }

    const res = await fetch(`component/get_workflows`, { cache: "no-store" });
    const components = await res.json();
    Object.assign(app.loaded_components, components);
}

async function loadComponent(filename, workflow_obj) {
	var workflow_str = null;
	var workflow_json = null;
	if(typeof workflow_obj == "string") {
		workflow_str = workflow_obj;
	}
	else {
		workflow_json = workflow_obj;
		workflow_str = JSON.stringify(workflow_json);
	}

	const body = new FormData();
	body.append("filename", filename);
	body.append("content", workflow_str);

	const resp = await fetch(`/component/load`, {
						method: 'POST',
						body: body,
					});

	const data = await resp.json();

	const component_name = data['node_name'];
	const component_type = `## ${component_name}`;
	if(!data['already_loaded']) {
		const uri = encodeURIComponent(component_type);
		const node_info = await fetch(`object_info/${uri}`, { cache: "no-store" });
		const def = await node_info.json();

		await app.registerNodesFromDefs.call(app, def);
	}

	// loaded_components might be incomplete after frontend refresh
	if(!app.loaded_components[component_name]) {
		if(!workflow_json) {
			workflow_json = JSON.parse(workflow_str)
		}
		app.loaded_components[component_name] = workflow_json;
	}

	// add node
    var node = LiteGraph.createNode(component_type);
    if (node) {
		//paste in last known mouse position
        node.pos[0] += app.canvas.graph_mouse[0] - node.size[0]/2;
        node.pos[1] += app.canvas.graph_mouse[1] - node.size[1]/2;

        app.canvas.graph.add(node,{doProcessChange:false});
    }
}

async function loadWorkflowFull(workflow_obj) {
	var workflow_json = null;

	if(typeof workflow_obj == "string") {
		workflow_json = JSON.parse(workflow_obj);
	}
	else {
		workflow_json = workflow_obj;
	}

	if(workflow_json.components) {
		for(let key in workflow_json.components) {
			await loadComponent(`${key}.component.json`, workflow_json.components[key]);
		}
	}

	app.loadGraphData(workflow_json);
}

const componentLoadMode = app.ui.settings.addSetting({
	id: "Comfy.ComponentLoadMode",
	name: "Require confirmation for the component edit mode when loading a .component.json file.",
	type: "boolean",
	defaultValue: false,
});

async function handleFileForFull(file) {
	const load_json_normal_from_file = () => {
		const reader = new FileReader();
		reader.onload = async () => {
			const workflow = JSON.parse(reader.result);

			loadWorkflowFull(workflow);
		};
		reader.readAsText(file);
	};

	const load_as_component_from_file = () => {
		const filename = file.name;
		const reader = new FileReader();
		reader.onloadend = async () => {
			await loadComponent(filename, reader.result);
		};

		reader.readAsText(file);
	};

	if (file.type === "image/png") {
		const pngInfo = await getPngMetadata(file);
		if (pngInfo) {
			if (pngInfo.workflow) {
				loadWorkflowFull(pngInfo.workflow);
			} else if (pngInfo.parameters) {
				importA1111(this.graph, pngInfo.parameters);
			}
		}
	} else if (file.name?.endsWith(".component.json")) {
		var result = false;

		if(componentLoadMode.value) {
			result = confirm("Will you load as component edit mode?");
		}

		if (result) {
			load_json_normal_from_file();
		} else {
			load_as_component_from_file();
		}

	} else if (file.type === "application/json" || file.name?.endsWith(".json")) {
		load_json_normal_from_file();
	} else if (file.name?.endsWith(".latent")) {
		const info = await getLatentMetadata(file);
		if (info.workflow) {
			loadWorkflowFull(info.workflow);
		}
	}
}

app.handleFile = handleFileForFull;

const original_queuePrompt = api.queuePrompt;
async function queuePrompt_with_components(number, { output, workflow }) {
	let used_node_types = new Set();
	for(let i in workflow.nodes) {
		if(workflow.nodes[i].type.startsWith('## '))
			used_node_types.add(workflow.nodes[i].type.slice(3));
	}

	const used_component_keys = Object.keys(app.loaded_components).filter(key => used_node_types.has(key));

	workflow.components = {};
	used_component_keys.forEach(key => {
		workflow.components[key] = app.loaded_components[key];
	});

	await original_queuePrompt.call(api, number, { output, workflow });
}

api.queuePrompt = queuePrompt_with_components;

app.registerExtension({
	name: "Comfy.WorkflowComponent",

	async setup() {
		loadComponentWorkflows();
		const menu = document.querySelector(".comfy-menu");

		// NOTE: Ultimately, the current Save should be replaced with Save Full.
		const saveFullButton = document.createElement("button");
		saveFullButton.textContent = "Save Full";
		saveFullButton.onclick = async () => {
				let filename = "workflow.json";

				filename = prompt("Save workflow as:", filename);
				if (!filename) return;
				if (!filename.toLowerCase().endsWith(".json")) {
					filename += ".json";
				}

				const p = await app.graphToPrompt();

				if(!app.loaded_components)
					app.loaded_components = {};

				// inject used components into workflow
				let used_node_types = new Set();
				for(let i in p.workflow.nodes) {
					if(p.workflow.nodes[i].type.startsWith('## '))
						used_node_types.add(p.workflow.nodes[i].type.slice(3));
				}

				const used_component_keys = Object.keys(app.loaded_components).filter(key => used_node_types.has(key));

				p.workflow.components = {};
				used_component_keys.forEach(key => {
					p.workflow.components[key] = app.loaded_components[key];
				});

				// save
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

		const saveComponentButton = document.createElement("button");
		saveComponentButton.textContent = "Export As Component";
		saveComponentButton.onclick = async () => {
					let filename = "workflow.component.json";

					filename = prompt("Save workflow as:", filename);
					if (!filename) return;
					if (!filename.toLowerCase().endsWith(".component.json")) {
						filename += ".component.json";
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

		menu.append(saveFullButton);
		menu.append(saveComponentButton);
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
