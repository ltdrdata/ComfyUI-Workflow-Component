import { app } from "/scripts/app.js";
import { $el } from "/scripts/ui.js";

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

		menu.append(saveComponentButton);
	}
});
