import { app } from "../../scripts/app.js";
import { $el } from "../../scripts/ui.js";
import { api } from "../../scripts/api.js";
import { getPngMetadata, importA1111, getLatentMetadata } from "../../scripts/pnginfo.js";

function removeHashFromNodeName(name) {
	const regex = /##.*\[([^\]]+)\]$/;
	const match = name.match(regex);

	if (match) {
		const hash = match[1];
		const modifiedName = name.replace(` [${hash}]`, '');
		return modifiedName;
	}

	return name;
}

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

const excludeExtensions = new Set([".png", ".jpg", ".webp", ".jpeg", ".safetensors", ".ckpt", ".pt", ".pth"]);

function workflow_security_filter(workflow) {
	workflow.nodes.forEach((node) => {
		// filter for 0 weighted LoraLoader
		if(node.widgets_values && node.widgets_values.length == 3){
			let wv = node.widgets_values;
			if(typeof(wv[0]) == "string" && wv[1] == 0 && wv[2] == 0){
				if(excludeExtensions.has(getFileExtension(wv[0])))
					wv[0] = "";
			}
		}

		if (node.inputs) {
            node.inputs.forEach((input) => {
                if (input.widget && input.widget.config) {
                    const configArray = input.widget.config[0];
                    if (Array.isArray(configArray) && configArray.every((filename) => excludeExtensions.has(getFileExtension(filename)))) {
                        input.widget.config[0] = [];
                    }
                }
            });
		}
		if (node.outputs) {
            node.outputs.forEach((output) => {
                if (output.widget && output.widget.config) {
                    const configArray = output.widget.config[0];
                    if (Array.isArray(configArray) && configArray.every((filename) => excludeExtensions.has(getFileExtension(filename)))) {
                        output.widget.config[0] = [];
                    }
                }
            });
		}
	});

	return workflow;
}

const conflict_table = {};
function is_component_conflicted(name) {
	let pure_name = name.substring(3, name.length - 9);
	let m = conflict_table[pure_name];
	if(m)
		return m.size>1;
	return false;
}

function register_component_name(name) {
	let pure_name = name.substring(3, name.length - 9);
	var s = conflict_table[pure_name];

	if(s) {
		s.add(name);
	}
	else {
		s = new Set();
		s.add(name);
		conflict_table[pure_name] = s;
	}
}

async function loadComponentWorkflows() {
	if(!localStorage.getItem('loaded_components')) {
		localStorage.setItem('loaded_components', '{}');
	}

	const res = await api.fetchApi(`component/get_workflows`, { cache: "no-store" });
	const components = await res.json();
	let loaded_components = JSON.parse(localStorage.getItem('loaded_components'));
	Object.assign(loaded_components, components);
	localStorage.setItem('loaded_components', JSON.stringify(loaded_components));
}

async function loadComponent(component_or_filename, workflow_obj, add_node) {
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
	body.append("component_or_filename", component_or_filename);
	body.append("content", workflow_str);

	const resp = await api.fetchApi(`/component/load`, {
						method: 'POST',
						body: body,
					});

	const data = await resp.json();

	const component_name = data['node_name'];
	if(!data['already_loaded']) {
		const uri = encodeURIComponent(component_name);
		const node_info = await api.fetchApi(`object_info/${uri}`, { cache: "no-store" });
		const def = await node_info.json();

		await app.registerNodesFromDefs.call(app, def);
	}

	// loaded_components might be incomplete after frontend refresh
	let loaded_components = JSON.parse(localStorage.getItem('loaded_components'));

	if(!loaded_components[component_name]) {
		if(!workflow_json) {
			workflow_json = JSON.parse(workflow_str)
		}
		loaded_components[component_name] = workflow_json;
		localStorage.setItem("loaded_components", JSON.stringify(loaded_components));
		register_component_name(component_name);
	}

	if(add_node) {
		// add node
		var node = LiteGraph.createNode(component_name);
		if (node) {
			//paste in last known mouse position
			node.pos[0] += app.canvas.graph_mouse[0] - node.size[0]/2;
			node.pos[1] += app.canvas.graph_mouse[1] - node.size[1]/2;

			app.canvas.graph.add(node,{doProcessChange:false});
		}
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
			await loadComponent(key, workflow_json.components[key], false);
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

app.load_workflow_with_components = loadWorkflowFull;

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
			await loadComponent(filename, reader.result, true);
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
			used_node_types.add(workflow.nodes[i].type);
	}

	let loaded_components = JSON.parse(localStorage.getItem('loaded_components'));
	const used_component_keys = Object.keys(loaded_components).filter(key => used_node_types.has(key));

	workflow = workflow_security_filter(workflow);

	workflow.components = {};
	used_component_keys.forEach(key => {
		workflow.components[key] = loaded_components[key];
	});

	return await original_queuePrompt.call(api, number, { output, workflow });
}

api.queuePrompt = queuePrompt_with_components;

const original_registerNodes = app.registerNodes;

async function registerNodes() {
	await original_registerNodes.call(app);

	if(localStorage.getItem('loaded_components')) {
		let loaded_components = JSON.parse(localStorage.getItem('loaded_components'));
		let workflow = JSON.parse(localStorage.getItem("workflow"));

		let used_node_types = new Set();
		if(workflow) {
            for(let i in workflow.nodes) {
                if(workflow.nodes[i].type.startsWith('## '))
                    used_node_types.add(workflow.nodes[i].type.slice(3));
            }
		}

		localStorage.setItem('loaded_components', "{}"); // clear
		for(let key in loaded_components) {
			if(loaded_components[used_node_types]) {
				await loadComponent(key, components[key], false);
			}
			else {
				register_component_name(key);
			}
		}
	}
}

app.registerNodes = registerNodes;

function getFileExtension(filename) {
  return filename.substring(filename.lastIndexOf("."));
}

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

				if(!localStorage.getItem('loaded_components'))
					localStorage.setItem('loaded_components', "{}");

				// inject used components into workflow
				let used_node_types = new Set();
				for(let i in p.workflow.nodes) {
					if(p.workflow.nodes[i].type.startsWith('## '))
						used_node_types.add(p.workflow.nodes[i].type);
				}

				let loaded_components = JSON.parse(localStorage.getItem('loaded_components'));
				const used_component_keys = Object.keys(loaded_components).filter(key => used_node_types.has(key));

				p.workflow = workflow_security_filter(p.workflow);

				p.workflow.components = {};
				used_component_keys.forEach(key => {
					p.workflow.components[key] = loaded_components[key];
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

	async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === 'ComponentInput') {
            const onConnectionsChange = nodeType.prototype.onConnectionsChange
            nodeType.prototype.onConnectionsChange = function (type, index, connected, link_info) {
                if(!link_info || !connected || !app.graph._nodes_by_id[link_info.target_id].inputs)
                    return;

                let target_node = app.graph._nodes_by_id[link_info.target_id];
                let slot = target_node.inputs[link_info.target_slot];

                let slot_type = slot.type;
                if(slot_type.includes(','))
                    slot_type = "COMBO,";

                if(this.outputs[0].type == "COMBO," && slot_type != "COMBO,") {
                    target_node.disconnectInput(link_info.target_slot);
                    return;
                }

                this.outputs[0].type = slot_type;
                this.outputs[0].name = slot_type;

                this.inputs[0].type = slot_type;

                this.widgets[0].value = slot.name;
                this.widgets[1].value = slot_type;

                if(slot?.widget?.config) {
                    if(slot?.widget?.config.length == 1) {
                        // combo
                        this.widgets[2].value = `COMBO:${target_node.type}:${slot.name}`
                    }
                    else {
                        this.widgets[2].value = JSON.stringify(slot.widget.config[1]).slice(1,-1);
                    }
                }
            }
        }
        else if (nodeData.name === 'ComponentOutput') {
            const onConnectionsChange = nodeType.prototype.onConnectionsChange
            nodeType.prototype.onConnectionsChange = function (type, index, connected, link_info) {
                if(!link_info || !connected || !app.graph._nodes_by_id[link_info.origin_id].outputs)
                    return;

                let origin_node = app.graph._nodes_by_id[link_info.origin_id];
                let origin_slot = origin_node.outputs[link_info.origin_slot];

                let slot_type = origin_slot.type;

                this.inputs[0].type = slot_type;
                this.inputs[0].label = slot_type;

                this.outputs[0].type = slot_type;

                this.widgets[0].value = origin_slot.name;
                this.widgets[1].value = slot_type;
            }
        }
	},

	nodeCreated(node, app) {
		Object.defineProperty(node, "title", {
			set: function(value) {
				node._title = value;
			},
			get: function() {
				if(node.type && node.type.startsWith('## ') && (node.type == node._title || node.type.substring(0,node.type.length-9) == node._title)) {
					if(!is_component_conflicted(node.type))
						return removeHashFromNodeName(node.type);
				}

				return node._title;
			}
		});

		if(node.comfyClass == "ExecutionControlString") {
            node.inputs[0].type = "STRING";

		    node.onConnectionsChange = function (type, index, connected, link_info) {
		        if(node.outputs[0].type != "*" || !link_info)
                    return;

                if(link_info.type == '*') {
                    for(let i in app.graph._nodes) {
                        if(app.graph._nodes[i].id == link_info.origin_id) {
                            link_info.type = app.graph._nodes[i].outputs[link_info.origin_slot].type;
                            break;
                        }
                    }
                }

                node.outputs[0].type = link_info.type;
                node.inputs[1].type = link_info.type;
		    }
		}

        if(node.comfyClass == "ExecutionBlocker") {
		    node.onConnectionsChange = function (type, index, connected, link_info) {
		        if(node.outputs[0].type != "*" || !link_info)
                    return;

                if(link_info.type == '*') {
                    for(let i in app.graph._nodes) {
                        if(app.graph._nodes[i].id == link_info.origin_id) {
                            link_info.type = app.graph._nodes[i].outputs[link_info.origin_slot].type;
                            break;
                        }
                    }
                }

                node.outputs[0].type = link_info.type;
                node.inputs[0].type = link_info.type;
		    }
		}

        if(node.comfyClass == "ExecutionSwitch") {
		    node.onConnectionsChange = function (type, index, connected, link_info) {
		        if(node.outputs[0].type != "*" || !link_info)
                    return;

                if(link_info.type == '*') {
                    for(let i in app.graph._nodes) {
                        if(app.graph._nodes[i].id == link_info.origin_id) {
                            link_info.type = app.graph._nodes[i].outputs[link_info.origin_slot].type;
                            break;
                        }
                    }
                }

                for(let i=0; i<5; i++) {
                    node.outputs[i].type = link_info.type;
                    node.inputs[i].type = link_info.type;
                }
		    }
		}

        if(node.comfyClass == "ExecutionOneOf") {
		    node.onConnectionsChange = function (type, index, connected, link_info) {
		        if(node.outputs[0].type != "*" || !link_info)
                    return;

                if(link_info.type == '*') {
                    for(let i in app.graph._nodes) {
                        if(app.graph._nodes[i].id == link_info.origin_id) {
                            link_info.type = app.graph._nodes[i].outputs[link_info.origin_slot].type;
                            break;
                        }
                    }
                }

                node.outputs[0].type = link_info.type;
                for(let i=0; i<5; i++) {
                    node.inputs[i].type = link_info.type;
                }
		    }
		}
	}
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
