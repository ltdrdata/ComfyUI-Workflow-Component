import { app, ComfyApp } from "/scripts/app.js";
import { api } from "/scripts/api.js";
import { ComfyDialog, $el } from "/scripts/ui.js";
import { ClipspaceDialog } from "/extensions/core/clipspace.js";

function itemToImagepath(data) {
	let name = data.filename;
	var subfolder = "";
	if(data.subfolder) {
		subfolder = `&subfolder=${data.subfolder}`;
	}

	return `view?filename=${name}${subfolder}&type=${data.type}&no-cache=${Date.now()}`;
}

function loadImage(imagePath) {
    return new Promise((resolve, reject) => {
        const image = new Image();

        image.onload = function() {
          resolve(image);
        };

        image.src = imagePath;
    });
}

function drawImageToCanvas(image, canvas) {
    canvas.width = image.width;
    canvas.height = image.height;

    const ctx = canvas.getContext('2d', {willReadFrequently: true });
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
}

async function load_image_to_canvas(imagePath, canvas) {
    const image = await loadImage(imagePath);
    drawImageToCanvas(image, canvas);
    return image;
}

function createToggleControl() {
	var control = document.createElement('div');
	control.className = 'toggle-control';

	var toggle = document.createElement('input');
	toggle.type = 'checkbox';
	toggle.className = 'toggle-switch';
	toggle.id = 'toggle-switch';

	var label = document.createElement('label');
	label.className = 'toggle-label';
	label.setAttribute('for', 'toggle-switch');

	var toggleHandle = document.createElement('span');
	toggleHandle.className = 'toggle-handle';

	var penText = document.createElement('span');
	penText.className = 'toggle-text pen-text';
	penText.innerText = 'Pen';

	var maskText = document.createElement('span');
	maskText.className = 'toggle-text mask-text';
	maskText.innerText = 'Mask';

	label.appendChild(penText);
	label.appendChild(maskText);
	label.appendChild(toggleHandle);
	control.appendChild(toggle);
	control.appendChild(label);

	return control;
}

// CSS 스타일 추가
var style = document.createElement('style');
style.innerHTML = `
	.toggle-control {
		display: inline-block;
		position: relative;
		width: 75px;
		height: 28px;
		margin-top: 3px;
	}
	.toggle-switch {
		opacity: 0;
		width: 0;
		height: 0;
	}
	.toggle-label {
		position: absolute;
		top: 0;
		left: 0;
		width: 100%;
		height: 100%;
		background-color: #ccc;
		border-radius: 40px;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0 8px;
		box-sizing: border-box;
		z-index: 1;
	}
	.toggle-handle {
		position: absolute;
		width: 25px;
		height: 25px;
		background-color: #fff;
		border-radius: 50%;
		transition: transform 0.2s ease;
		z-index: 2;
	}
	.toggle-text {
		color: #fff;
		font-weight: bold;
		font-size: 14px;
		pointer-events: none;
		position: relative;
		z-index: 3;
	}
	.pen-text {
		margin-right: 2px;
		opacity: 0;
		transition: opacity 0.2s ease;
	}
	.mask-text {
		margin-left: 2px;
		opacity: 1;
		color: #2196F3;
		transition: opacity 0.2s ease;
	}
	.toggle-switch:checked + .toggle-label {
		background-color: #2196F3;
	}
	.toggle-switch:checked + .toggle-label .toggle-handle {
		transform: translateX(33px);
	}
	.toggle-switch:checked + .toggle-label .pen-text {
		opacity: 0;
	}
	.toggle-switch:checked + .toggle-label .mask-text {
		opacity: 1;
	}
    .progress-button {
        position: relative;
        width: 200px;
        height: 30px;
        background-color: #f0f0f0;
        border: none;
        overflow: hidden;
    }
    .progress-button::before {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        width: 0;
        height: 100%;
        background-color: #4caf50;
        transition: width 0.5s ease;
    }
    .progress-button.progress::before {
        width: 100%;
    }
`;

document.head.appendChild(style);



function addMenuHandler(nodeType, cb) {
	const getOpts = nodeType.prototype.getExtraMenuOptions;
	nodeType.prototype.getExtraMenuOptions = function () {
		const r = getOpts.apply(this, arguments);
		cb.apply(this, arguments);
		return r;
	};
}

function getOriginalSizeMaskCanvas(mask_canvas, orig_image, dont_touch, whole_inpaint) {
	let new_canvas = document.createElement("canvas");
	new_canvas.width = orig_image.width;
	new_canvas.height = orig_image.height;

	const new_ctx = new_canvas.getContext('2d', {willReadFrequently: true });

	new_ctx.drawImage(mask_canvas, 0, 0, mask_canvas.width, mask_canvas.height);

	// paste mask data into alpha channel
	const data = new_ctx.getImageData(0, 0, new_canvas.width, new_canvas.height);

	// refine mask image
	if(!dont_touch) {
		for (let i = 0; i < data.data.length; i += 4) {
            if(whole_inpaint) {
                data.data[i] = 0;
                data.data[i+1] = 0;
                data.data[i+2] = 0;
                data.data[i+3] = 0;
            }
            else {
                if(data.data[i+3] == 255)
                    data.data[i+3] = 0;
                else
                    data.data[i+3] = 255;
            }
		}
	}

	new_ctx.globalCompositeOperation = 'source-over';
	new_ctx.putImageData(data, 0, 0);

	return new_canvas;
}

// Helper function to convert a data URL to a Blob object
function dataURLToBlob(dataURL) {
	const parts = dataURL.split(';base64,');
	const contentType = parts[0].split(':')[1];
	const byteString = atob(parts[1]);
	const arrayBuffer = new ArrayBuffer(byteString.length);
	const uint8Array = new Uint8Array(arrayBuffer);
	for (let i = 0; i < byteString.length; i++) {
		uint8Array[i] = byteString.charCodeAt(i);
	}
	return new Blob([arrayBuffer], { type: contentType });
}

function loadedImageToBlob(image) {
	const canvas = document.createElement('canvas');

	canvas.width = image.width;
	canvas.height = image.height;

	const ctx = canvas.getContext('2d', {willReadFrequently: true });

	ctx.drawImage(image, 0, 0);

	const dataURL = canvas.toDataURL('image/png', 1);
	const blob = dataURLToBlob(dataURL);

	return blob;
}

function image_to_filepath(img) {
	let url = new URL(img.src);

	let filename = url.searchParams.get('filename');
	let type = url.searchParams.get('type');
	let subfolder = url.searchParams.get('subfolder');

	const item =
		{
			"filename": filename,
			"type": type,
			"subfolder": subfolder
		};

	return item;
}

async function gen_flatten(base_image, layers) {
	const formData = new FormData();

	let image_paths = [{id:0, image:image_to_filepath(base_image)}];
	var id = 0;
	for(let x in layers) {
		id++;
        if(layers[x].image) {
		    image_paths.push({id:id, image:image_to_filepath(layers[x].image)});
        }

		let dataURL = layers[x].mask.toDataURL();
		let blob = dataURLToBlob(dataURL);
		formData.append(id+"", blob);
	}

	const filename = "imagerefiner-" + performance.now() + ".png";
	const savepath =
		{
			"filename": filename,
			"subfolder": "clipspace",
			"type": "input",
		};

	let save_info = {
			image_paths: image_paths,
			savepath: savepath
		};

	formData.append('save_info', JSON.stringify(save_info));

	let response = await fetch('/imagerefiner/save', {
		method: 'POST',
		body: formData
	}).catch(error => {
		console.error('Error:', error);
	});


	let json = await response.json();
	return "/view?" + new URLSearchParams(savepath).toString();
}

var unique_id = 0;
function prepare_generate_data(component_name, prompt_data, mask_canvas, base_image, layers, images_in_layers) {
	const formData = new FormData();

	const dataURL = mask_canvas.toDataURL();
	const blob = dataURLToBlob(dataURL);

    if(images_in_layers)
        prompt_data.image_paths = images_in_layers;
    else
	    prompt_data.image_paths = [{id:0, image:image_to_filepath(base_image)}];

	if(layers) {
		for(let x in layers) {
			var is_hidden = false;
			if(!layers[x].visibilityCheckbox.checked)
                continue;

			unique_id++;
            let base_item = {id:unique_id, mask:layers[x].mask};

			if(layers[x].prompt_data) {
				let image_path = image_to_filepath(layers[x].image);

				// mask won't passed by this (this mask is for front)
				prompt_data.image_paths.push({...base_item, image:image_path, is_mask_mode:true});
			}
			else {
				prompt_data.image_paths.push({...base_item, is_mask_mode:false});
			}

			// mask will be passed by this
			let dataURL = layers[x].mask.toDataURL();
			let blob = dataURLToBlob(dataURL);
			formData.append(unique_id+"", blob);
		}
	}
	else {
		// regenerate mode
		for(let x in prompt_data.image_paths) {
            unique_id++;

			if((x+"") == '0') {
				continue;
            }

			let item = prompt_data.image_paths[x];
			let dataURL = item.mask.toDataURL();
			let blob = dataURLToBlob(dataURL);
			item.id = unique_id;
			formData.append(unique_id+"", blob);
		}
	}

	prompt_data.component_name = component_name;

	formData.append('mask', blob);
	formData.append('prompt_data', JSON.stringify(prompt_data));

	return formData;
}

function prepare_export_data_layer(formData, layer) {
    let result = {};

    // common
    result.id = layer.id;
    result.is_visible = layer.visibilityCheckbox.checked;

    let dataURL = layer.mask.toDataURL();
    let blob = dataURLToBlob(dataURL);
    formData.append(result.id+"", blob);

    if(layer.prompt_data) {
        // mask mode layer: image, prompt_data, cands
        result.image = image_to_filepath(layer.image);

        result.cands = [];
        for(let i in layer.cands) {
            result.cands.push(image_to_filepath(layer.cands[i]));
        }

        for(let i in layer.prompt_data.image_paths) {
            let item = layer.prompt_data.image_paths[i];
            if(item.is_mask_mode == false) {
                let dataURL = item.mask.toDataURL();
                let blob = dataURLToBlob(dataURL);
                formData.append("draw_"+item.id, blob);
            }
        }

        result.prompt_data = layer.prompt_data;
    }

    return result;
}

function prepare_export_data(component_name, prompt_data, mask_canvas, base_image, layers) {
	const formData = new FormData();

	prompt_data.base_image_path = image_to_filepath(base_image);
	var id = 0;

    let layers_data = [];
	if(layers) {
		for(let x in layers) {
		    let info = prepare_export_data_layer(formData, layers[x]);
		    layers_data.push(info);
		}
	}

	prompt_data.component_name = component_name;

    let data =
        {
            prompt_data: prompt_data,
            layers_data: layers_data
        }

	const dataURL = mask_canvas.toDataURL();
	const blob = dataURLToBlob(dataURL);
	formData.append('mask', blob);
	formData.append('data', JSON.stringify(data));

	return formData;
}

async function generate(component_name, prompt_data, mask_canvas, base_image, layers, images_in_layers) {
	let formData = prepare_generate_data(component_name, prompt_data, mask_canvas, base_image, layers, images_in_layers);

	let response = await fetch('/imagerefiner/generate', {
		method: 'POST',
		body: formData
	}).catch(error => {
		console.error('Error:', error);
	});

	let json = await response.json();
	return json;
}


async function export_work(component_name, prompt_data, mask_canvas, base_image, layers) {
	let formData = prepare_export_data(component_name, prompt_data, mask_canvas, base_image, layers, true);

	fetch('/imagerefiner/get_archive', {
		method: 'POST',
		body: formData,
	})
		.then(response => {
                const contentDisposition = response.headers.get('Content-Disposition');
                const filename = contentDisposition.split('filename=')[1].replace(/"/g, '');

                return { response, filename };
			})
		.then(({ response, filename }) => response.blob().then(blob => ({ blob, filename })))
		.then(({ blob, filename }) => {
			if (navigator.msSaveBlob) {
				navigator.msSaveBlob(blob, filename);
			} else {
				const link = document.createElement('a');
				const url = URL.createObjectURL(blob);
				link.href = url;
				link.download = filename;

				link.click();

				URL.revokeObjectURL(url);
			}
		})
		.catch(error => {
			console.error('File export error:', error);
		});

}


async function save_to_clipspace(base_image, layers) {
	const formData = new FormData();

	let image_paths = [{id:0, image:image_to_filepath(base_image)}];
	var id = 0;
	for(let x in layers) {
		id++;
        if(layers[x].visibilityCheckbox.checked) {
            if(layers[x].image) {
                image_paths.push({id:id, image:image_to_filepath(layers[x].image)});
            }
            else {
                image_paths.push({id:id});
            }

            let dataURL = layers[x].mask.toDataURL();
            let blob = dataURLToBlob(dataURL);
            formData.append(id+"", blob);
        }
    }

	const filename = "imagerefiner-" + performance.now() + ".png";
	const savepath =
		{
			"filename": filename,
			"subfolder": "clipspace",
			"type": "input",
		};

	let save_info = {
			image_paths: image_paths,
			savepath: savepath
		};

	formData.append('save_info', JSON.stringify(save_info));

	let response = await fetch('/imagerefiner/save', {
		method: 'POST',
		body: formData
	}).catch(error => {
		console.error('Error:', error);
	});

	let json = await response.json();

	ComfyApp.clipspace.imgs[ComfyApp.clipspace['selectedIndex']] = new Image();
	ComfyApp.clipspace.imgs[ComfyApp.clipspace['selectedIndex']].src = "/view?" + new URLSearchParams(savepath).toString() + app.getPreviewFormatParam();

	if(ComfyApp.clipspace.images)
		ComfyApp.clipspace.images[ComfyApp.clipspace['selectedIndex']] = savepath;

	if(ComfyApp.clipspace.widgets) {
		const index = ComfyApp.clipspace.widgets.findIndex(obj => obj.name === 'image');

		if(index >= 0)
			ComfyApp.clipspace.widgets[index].value = savepath;
	}

	ClipspaceDialog.invalidatePreview();
}

async function uploadFile(file, updateNode) {
	try {
		const body = new FormData();
		body.append("image", file);
		const resp = await fetch("/upload/image", {
			method: "POST",
			body,
		});

		if (resp.status === 200) {
			const data = await resp.json();
			return `view?filename=${data.name}&subfolder=${data.subfolder}&type=${data.type}&no-cache=${Date.now()}`;
		} else {
			alert(resp.status + " - " + resp.statusText);
		}
	} catch (error) {
		alert(error);
	}
}

async function uploadWork(file) {
	const formData = new FormData();
	formData.append('file', file);

	const response = await fetch('/imagerefiner/upload_archive', {
		method: 'POST',
		body: formData
	});

	if (response.ok) {
		return await response.json();
	} else {
		console.error('Upload failed');
		return null;
	}
}


function prepareRGB(image, backupCanvas, backupCtx) {
	// paste mask data into alpha channel
	backupCtx.drawImage(image, 0, 0, backupCanvas.width, backupCanvas.height);
	const backupData = backupCtx.getImageData(0, 0, backupCanvas.width, backupCanvas.height);

	// refine mask image
	for (let i = 0; i < backupData.data.length; i += 4) {
		if(backupData.data[i+3] == 255)
			backupData.data[i+3] = 0;
		else
			backupData.data[i+3] = 255;

		backupData.data[i] = 0;
		backupData.data[i+1] = 0;
		backupData.data[i+2] = 0;
	}

	backupCtx.globalCompositeOperation = 'source-over';
	backupCtx.putImageData(backupData, 0, 0);
}

function is_available_component(class_def, name, component) {
	var input_image_count = 0;
	var input_latent_count = 0;
	var input_mask_count = 0;

	let inputs = [];
	let outputs = class_def.output;
	for(let name in class_def.input.required) {
		let type = class_def.input.required[name][0];

		if(Array.isArray(type)) {
			inputs.push("COMBO");
		}
		else {
			inputs.push(type);
		}
	}

	for(let x in inputs) {
		let kind = inputs[x];
		switch(kind) {
		case "IMAGE":
			input_image_count++;
			if(input_image_count>1)
				return false;
			break;

		case "MASK":
			input_mask_count++;
			if(input_mask_count>1)
				return false;
			break;

		case "LATENT":
			input_latent_count++;
			if(input_latent_count>1)
				return false;
			break;

		case "BASIC_PIPE":
		case "VAE":
		case "MODEL":
		case "CONDITIONING":
		case "INT":
		case "FLOAT":
		case "STRING":
			break;

		case "CONTROL_NET":
			// yet not support
			return false;

		default:
			if(kind == null) {
				console.log(`component '${name}' has invalid inputs nodes.`);
				return false;
			}

			if(kind == "COMBO" || kind.includes(","))
				continue;

			return false;
		}
	}

	if((input_image_count + input_latent_count) != 1)
		return false;

	if(input_mask_count > 1)
		return false;

	var output_image_count = 0;
	for(let x in outputs) {
		let kind = outputs[x];
		if(kind == "IMAGE" || kind == "LATENT") {
			output_image_count++;
			if(output_image_count>1)
				return false;
		}
	}

	if(output_image_count != 1)
		return false;

	return true;
}

class ImageRefinerDialog extends ComfyDialog {
	static instance = null;

	static getInstance() {
		if(!ImageRefinerDialog.instance) {
			ImageRefinerDialog.instance = new ImageRefinerDialog(app);
		}

		return ImageRefinerDialog.instance;
	}

	is_layout_created = false;

	constructor() {
		super();
		this.element = $el("div.comfy-modal", { parent: document.body }, []);
		this.layer_id = 1;
		this.is_mask_mode = true;
	}

	createButton(name, callback) {
		var button = document.createElement("button");
		button.innerText = name;
		button.addEventListener("click", callback);
		return button;
	}

	createLeftButton(name, callback) {
		var button = this.createButton(name, callback);
		button.style.cssFloat = "left";
		button.style.marginRight = "4px";
		return button;
	}

	createRightButton(name, callback) {
		var button = this.createButton(name, callback);
		button.style.cssFloat = "right";
		button.style.marginLeft = "4px";
		return button;
	}


    createProgressButton(name, callback) {
        var button = this.createRightButton(name, callback);

        var progress = 0;
//        button.style.background = 'black';
        button.style.transition = "background 0.5s";

        button.setProgress = function(newProgress) {
            progress = newProgress;
            let color = `linear-gradient(90deg, #00b300 ${progress}%, red ${progress}%)`;
            button.style.background = color;
        };

        button.stopProgress = () => {
            button.style.removeProperty('background');
            button.style.removeProperty('color');
        }

        return button;
    }


	open_cands_selector(layer) {
		let self = this;

		var modal = document.createElement('div');
		modal.style.position = 'fixed';
		modal.style.top = '0';
		modal.style.left = '0';
		modal.style.width = '100%';
		modal.style.height = '100%';
		modal.style.backgroundColor = 'rgba(0, 0, 0, 0.5)';
		modal.style.display = 'flex';
		modal.style.flexDirection = 'column';
		modal.style.justifyContent = 'center';
		modal.style.alignItems = 'center';
		modal.style.zIndex = '9997';
		modal.id = "ImageRefiner-Candidate-Selector";

		var gallery = document.createElement('div');
		gallery.style.display = 'flex';
		gallery.style.flexWrap = 'wrap';
		gallery.style.maxHeight = '600px';
		gallery.style.overflow = 'auto';
		var selectedImage = null;
		var selectedMaskImage = null;

		layer.cands.forEach(function(cand) {
			var image = document.createElement('img');
			var maxDimension = 500;

			image.style.maxWidth = maxDimension + 'px';
			image.style.maxHeight = maxDimension + 'px';
			image.style.margin = '10px';
			image.style.objectFit = 'cover';
			image.style.cursor = 'pointer';
			modal.style.zIndex = '9000';

			image.onload = function() {
				var canvas = document.createElement('canvas');
				var ctx = canvas.getContext('2d', {willReadFrequently: true });
				var width = image.width;
				var height = image.height;
				canvas.width = image.width;
				canvas.height = image.height;
				ctx.drawImage(image, 0, 0, width, height);
				ctx.globalCompositeOperation = 'destination-out';

				// Find the bounding box of the non-transparent pixels in the mask
				var maskCtx = layer.mask.getContext('2d', {willReadFrequently: true });
				var imageData = maskCtx.getImageData(0, 0, width, height);
				var pixels = imageData.data;
				var minX = width;
				var minY = height;
				var maxX = 0;
				var maxY = 0;

				for (var y = 0; y < height; y++) {
					for (var x = 0; x < width; x++) {
						var alpha = pixels[(y * width + x) * 4 + 3];
						if (alpha == 0) {
							minX = Math.min(minX, x);
							minY = Math.min(minY, y);
							maxX = Math.max(maxX, x);
							maxY = Math.max(maxY, y);
						}
					}
				}

				// Crop the canvas to the bounding box of non-transparent pixels
				var croppedWidth = maxX - minX + 1;
				var croppedHeight = maxY - minY + 1;

				var scaleFactor = 1;
				var width = croppedWidth;
				var height = croppedHeight

				if (width > maxDimension || height > maxDimension) {
					if (width > height) {
						scaleFactor = maxDimension / width;
					} else {
						scaleFactor = maxDimension / height;
					}
					width *= scaleFactor;
					height *= scaleFactor;
				}

				let resizedCanvas = document.createElement('canvas');
				resizedCanvas.width = width;
				resizedCanvas.height = height;
				let resizedCtx = resizedCanvas.getContext('2d', {willReadFrequently: true });

				resizedCtx.clearRect(0, 0, croppedWidth, croppedHeight);
				resizedCtx.drawImage(
					canvas,
					minX, minY, croppedWidth, croppedHeight,
					0, 0, width, height
				);

				let maskedImage = document.createElement('img');
				maskedImage.src = resizedCanvas.toDataURL();
				maskedImage.style.width = resizedCanvas.width + 'px';
				maskedImage.style.height = resizedCanvas.height + 'px';
				maskedImage.style.margin = '10px';
				maskedImage.style.objectFit = 'cover';

				gallery.appendChild(maskedImage);

				maskedImage.addEventListener('click', function() {
					if (selectedMaskImage) {
						selectedMaskImage.style.border = 'none';
					}
					selectedImage = image;
					selectedMaskImage = maskedImage;
					selectedMaskImage.style.border = '2px solid #006699';

					layer.image = cand;
					self.invalidateLayerItem(layer);
				});
			};

			image.src = cand.src;
			image.cand = cand;
		});

		var doneButton = document.createElement('button');
		doneButton.textContent = 'Done';
		doneButton.style.padding = '10px 20px';
		doneButton.style.border = 'none';
		doneButton.style.borderRadius = '5px';
		doneButton.style.fontFamily = 'Arial, sans-serif';
		doneButton.style.fontSize = '16px';
		doneButton.style.fontWeight = 'bold';
		doneButton.style.color = '#fff';
		doneButton.style.background = 'linear-gradient(to bottom, #0070B8, #003D66)';
		doneButton.style.boxShadow = '0 2px 4px rgba(0, 0, 0, 0.4)';

		doneButton.addEventListener('click', function() {
			closeModal();
		});

		modal.appendChild(doneButton);

		var lineBreak = document.createElement('div');
		lineBreak.style.clear = 'both';
		modal.appendChild(lineBreak);

		modal.appendChild(gallery);

		function closeModal() {
			document.body.removeChild(modal);
		}

		document.body.appendChild(modal);
	}

	createRightSlider(self, name, callback) {
		const divElement = document.createElement('div');
		divElement.id = "image-refiner-slider";
		divElement.style.cssFloat = "right";
		divElement.style.fontFamily = "sans-serif";
		divElement.style.marginRight = "4px";
		divElement.style.color = "var(--input-text)";
		divElement.style.backgroundColor = "var(--comfy-input-bg)";
		divElement.style.borderRadius = "8px";
		divElement.style.borderColor = "var(--border-color)";
		divElement.style.borderStyle = "solid";
		divElement.style.fontSize = "15px";
		divElement.style.height = "21px";
		divElement.style.padding = "1px 6px";
		divElement.style.display = "flex";
		divElement.style.position = "relative";
		divElement.style.top = "2px";
		self.brush_slider_input = document.createElement('input');
		self.brush_slider_input.setAttribute('type', 'range');
		self.brush_slider_input.setAttribute('min', '1');
		self.brush_slider_input.setAttribute('max', '100');
		self.brush_slider_input.setAttribute('value', '10');
		self.brush_slider_input.style.width = "70px";
		const labelElement = document.createElement("label");
		labelElement.textContent = name;

		divElement.appendChild(labelElement);
		divElement.appendChild(self.brush_slider_input);

		self.brush_slider_input.addEventListener("change", callback);

		return divElement;
	}

	createNumberPrompt(name, detail) {
		const numberInput = document.createElement("input");
		numberInput.type = "number";

		numberInput.id = `number-${name}`;
		numberInput.value = detail.default;
		numberInput.min = detail.min;
		numberInput.max = detail.max;

		if(!detail.step)
			numberInput.step = 1;
		else
			numberInput.step = detail.step;

		numberInput.style.marginLeft = "1px";
		numberInput.style.width = "190px";
		numberInput.style.borderRadius = "15px";
		numberInput.style.textAlign = "right";
		numberInput.style.paddingRight = "4px";

		const label = document.createElement("label");
		label.style.marginLeft = "5px";
		label.style.color = 'var(--descrip-text)';
		label.style.fontWeight = 'bold';
		label.textContent = `${name}:`;
		label.setAttribute("for", numberInput.id);

		return {label:label, numberInput:numberInput};
	}

	createTextPrompt(placeholder) {
		let multilineTextbox = document.createElement("textarea");
		multilineTextbox.rows = 4;
		multilineTextbox.cols = 30;
		multilineTextbox.placeholder = placeholder;
		multilineTextbox.style.marginLeft = "1px";
		multilineTextbox.style.width = "195px";

		return multilineTextbox;
	}

	createComboPrompt(name, items) {
		let combo = document.createElement("select");

		combo.style.cssFloat = "left";
		combo.style.fontSize = "14px";
		combo.style.padding = "4px";
		combo.style.background = "black";
		combo.style.marginLeft = "2px";
		combo.style.width = "199px";
		combo.id = `combo-${name}`;
		combo.style.borderRadius = "15px";

		items.forEach(item => {
			const option = document.createElement("option");
			option.value = item;
			option.text = item;
			combo.appendChild(option);
		});

		const label = document.createElement("label");
		label.style.marginLeft = "5px";
		label.style.color = 'var(--descrip-text)';
		label.style.fontWeight = 'bold';
		label.textContent = `${name}:`;
		label.setAttribute("for", combo.id);

		return {label:label, combo:combo};
	}

	async createCheckpointPrompt(placeholder, is_first) {
		let combo = document.createElement("select");

		combo.style.cssFloat = "left";
		combo.style.fontSize = "14px";
		combo.style.padding = "4px";
		combo.style.background = "black";
		combo.style.marginLeft = "2px";
		combo.style.width = "199px";
		combo.style.borderRadius = "15px";

		let listItems = [];
		listItems.push({ value: "@none", text: placeholder });

		if(!is_first) {
			listItems.push({ value: "@same", text: "Same with first model" });
		}

		const response = await fetch(`/imagerefiner/get_checkpoints`);
		const data = await response.json();

		for(let x in data.checkpoints) {
			let ckpt_name = data.checkpoints[x];
			listItems.push({value: ckpt_name, text: ckpt_name});
		}

		listItems.forEach(item => {
			const option = document.createElement("option");
			option.value = item.value;
			option.text = item.text;
			combo.appendChild(option);
		});

		if(is_first && listItems.length > 1) {
			combo.value = listItems[1].value;
		}

		return combo;
	}

	createComponentSelectCombo() {
		let combo = document.createElement("select");

		const self = this;
		combo.addEventListener("change", async function() {
			await self.invalidatePromptControls();
		});

		combo.style.cssFloat = "right";
		combo.style.fontSize = "14px";
		combo.style.padding = "4px";
		combo.style.background = "black";
		combo.style.border = "1px solid gray";
		combo.style.marginRight = "4px";

		return combo;
	}

	createSelectCombo(name, default_value, min, max) {
		const combo = document.createElement("input");
		combo.type = "number";

		combo.id = `ir-number-${name}`;
		combo.value = default_value;
		combo.min = min;
		combo.max = max;

		combo.step = 1;

		combo.style.cssFloat = "right";
		combo.style.marginLeft = "3px";
		combo.style.marginRight = "5px";
		combo.style.marginTop = "2px";
		combo.style.width = "50px";
		combo.style.height = "24px";
		combo.style.borderRadius = "10px";
		combo.style.textAlign = "center";

		const label = document.createElement("label");
		label.style.cssFloat = "right";
		label.style.marginLeft = "5px";
		label.style.marginTop = "7px";
		label.style.height = "24px";
		label.style.color = 'var(--descrip-text)';
		label.style.fontWeight = 'bold';
		label.textContent = name;
		label.setAttribute("for", combo.id);

		return {label:label, combo:combo};
	}

	async invalidateLayerItem(item) {
		let maskCanvas = item.mask;
		let outputCanvas = item.canvas;

		let width = item.mask.width;
		let height = item.mask.height;

		var tempCanvas = document.createElement("canvas");
		var tempCtx = tempCanvas.getContext('2d', {willReadFrequently: true });

		tempCanvas.width = width;
		tempCanvas.height = height;

        if(item.prompt_data) {
            tempCtx.drawImage(item.image, 0, 0, width, height);
        }
        else {
            tempCtx.drawImage(item.mask, 0, 0, width, height);
        }

        var maskCtx = maskCanvas.getContext('2d', {willReadFrequently: true });
        var maskImageData = maskCtx.getImageData(0, 0, width, height);
        var maskData = maskImageData.data;

        var imageData = tempCtx.getImageData(0, 0, width, height);
        var pixelData = imageData.data;

        if(item.prompt_data) {
            for (var i = 0; i < pixelData.length; i += 4) {
                pixelData[i + 3] = 255-maskData[i + 3];
            }
        }

        tempCtx.putImageData(imageData, 0, 0);

        var outputCtx = outputCanvas.getContext('2d', {willReadFrequently: true });
        outputCtx.drawImage(tempCanvas, 0, 0, width, height, 0, 0, width, height);
	}

	async invalidateComponentSelectCombo() {
		if(this.componentSelectCombo) {
			let listItems = [];

			let components = JSON.parse(localStorage['loaded_components']);

			let postponed = [];
			for(let name in components) {
				if(is_available_component(this.defs[name], name, components[name]))
					if(name.includes(".ir "))
						listItems.push({ value: name, text: name });
					else
						postponed.push({ value: name, text: name });
			}

			listItems.push(...postponed);

			if(!listItems.length) {
				listItems.push({ value: "none", text: "N/A (.components.json)" });
			}

			listItems.forEach(item => {
				const option = document.createElement("option");
				option.value = item.value;
				option.text = item.text;
				this.componentSelectCombo.appendChild(option);
			});
		}
	}

	async invalidatePromptControls(prompt_data_opt) {
		this.prompts = {};

		while (this.prompt_controls.firstChild) {
			this.prompt_controls.removeChild(this.prompt_controls.firstChild);
		}

		if(this.componentSelectCombo.value != "none") {
			let components = JSON.parse(localStorage['loaded_components']);
			let component = components[this.componentSelectCombo.value];

			let class_def = this.defs[this.componentSelectCombo.value];

			if(!component)
				return;

			// node map
			let node_map = {};
			for(let x in component.nodes) {
				let node = component.nodes[x];
				node_map[node.id] = node;
			}

			// link map
			let link_map = {};
			for(let x in component.links) {
				let link = component.links[x];
				let key = link[0];
				let dest = { id: link[3], slot: link[4] };
				link_map[key] = dest;
			}

			let inputs = [];
			let outputs = [];

			var is_input_pixel = true; // otherwise, LATENT
			var is_output_pixel = true;

			for(let name in class_def.input.required) {
				let type = class_def.input.required[name][0];
				let detail = class_def.input.required[name][1];
				if(Array.isArray(type)) {
					let item = { type: "COMBO", name: name, detail: type };
					inputs.push(item);
				}
				else {
					let item = { type: type, name: name, detail: detail };
					inputs.push(item);

					if(item.type == "LATENT") {
						is_input_pixel = false;
						this.input_image = { LATENT: item.name };
					}
					else if(item.type == "IMAGE") {
						is_input_pixel = true;
						this.input_image = { IMAGE: item.name };
					}
				}
			}

			for(let x in component.nodes) {
				let node = component.nodes[x];

				switch(node.type) {
				case "ComponentOutput":
					{
						let kind = node.inputs[0].type;
						outputs.push(kind);

						if(kind == "LATENT") {
							is_output_pixel = false;
							this.output_image = { LATENT: node.inputs[0].name };
						}
						else if(kind == "IMAGE") {
							is_output_pixel = true;
							this.output_image = { IMAGE: node.inputs[0].name };
						}
					}
					break;
				}
			}

			var checkpoint_added = false;
			this.mask_name = null;
			this.seeds = [];

			for(let x in inputs) {
				let name = inputs[x].name;
				let kind = inputs[x].type;
				switch(kind) {
				case "IMAGE":
				case "LATENT":
					break;

				case "MASK":
					// skip
					this.mask_name = inputs[x].name;
					break;

				case "BASIC_PIPE":
					{
						let checkpoint = await this.createCheckpointPrompt(`checkpoint (${name})`,!checkpoint_added);
						// TODO: VAE loader
						let positive = this.createTextPrompt(`positive prompt (${inputs[x].name})`);
						let negative = this.createTextPrompt(`negative prompt (${inputs[x].name})`);

						this.prompt_controls.appendChild(checkpoint);
						this.prompt_controls.appendChild(positive);
						this.prompt_controls.appendChild(negative);

						checkpoint_added = true;

						let item = {
								BASIC_PIPE:
								{
									checkpoint: checkpoint,
									positive: positive,
									negative: negative,
								}
							};

						this.prompts[name] = item;

						if(prompt_data_opt && prompt_data_opt[name]) {
						    checkpoint.value = prompt_data_opt[name].checkpoint;
						    positive.value = prompt_data_opt[name].positive;
						    negative.value = prompt_data_opt[name].negative;
						}
					}
					break;

				case "VAE":
					{
						let checkpoint = await this.createCheckpointPrompt(!`checkpoint (${name})`, checkpoint_added);
						this.prompt_controls.appendChild(checkpoint);
						checkpoint_added = true;

						let item = { VAE:
										{
											checkpoint: checkpoint
										}
									};

						this.prompts[name] = item;

                        if(prompt_data_opt && prompt_data_opt[name]) {
						    checkpoint.value = prompt_data_opt[name].checkpoint;
						}
					}
					break;

				case "MODEL":
					{
						let checkpoint = await this.createCheckpointPrompt(!`checkpoint (${name})`, checkpoint_added);
						this.prompt_controls.appendChild(checkpoint);
						checkpoint_added = true;

						let item = { MODEL: checkpoint };
						this.prompts[name] = item;

                        if(prompt_data_opt && prompt_data_opt[name]) {
						    checkpoint.value = prompt_data_opt[name].checkpoint;
						}
					}
					break;

				case "CONDITIONING":
					{
						let checkpoint = await this.createCheckpointPrompt(`checkpoint (${name})`, !checkpoint_added);
						let text_prompt = this.createTextPrompt(`prompt (${name})`);
						this.prompt_controls.appendChild(checkpoint);
						this.prompt_controls.appendChild(text_prompt);

						checkpoint_added = true;

						let item = { CONDITIONING:
										{
											checkpoint: checkpoint,
											text_prompt: text_prompt,
										}
									};

						this.prompts[name] = item;

                        if(prompt_data_opt && prompt_data_opt[name]) {
						    checkpoint.value = prompt_data_opt[name].checkpoint;
						    text_prompt.value = prompt_data_opt[name].text_prompt;
						}
					}
					break;
					// pass-through

				case "STRING":
					{
						let control = this.createTextPrompt(name);
						this.prompt_controls.appendChild(control);

						let item = {
								STRING: control,
							};

						this.prompts[name] = item;

                        if(prompt_data_opt && prompt_data_opt[name]) {
						    control.value = prompt_data_opt[name].value;
						}
					}
					break;

				case "INT":
				case "FLOAT":
					{
						let control = this.createNumberPrompt(inputs[x].name, inputs[x].detail);
						this.prompt_controls.appendChild(control.label);
						this.prompt_controls.appendChild(control.numberInput);
						this.prompt_controls.appendChild($el("br", {}, []));

						let item = {};

						if(kind == "INT")
							item.INT = control.numberInput;
						else
							item.FLOAT = control.numberInput;

						if(name.startsWith("seed.") || name == "seed") {
							this.seeds.push(control);
						}

						this.prompts[name] = item;

                        if(prompt_data_opt && prompt_data_opt[name]) {
                            if(item.INT)
						        item.INT.value = prompt_data_opt[name].value;
                            else if(item.FLOAT)
						        item.FLOAT.value = prompt_data_opt[name].value;
						}
					}
					break;

				default:
					{
						let control = this.createComboPrompt(inputs[x].name, inputs[x].detail);
						this.prompt_controls.appendChild(control.label);
						this.prompt_controls.appendChild(control.combo);
						this.prompt_controls.appendChild($el("br", {}, []));

						let item = {
								COMBO: control.combo,
							};

						this.prompts[name] = item;

                        if(prompt_data_opt && prompt_data_opt[name]) {
                            item.COMBO.value = prompt_data_opt[name].value;
                        }
					}
				}
			}

			if(this.seeds.length) {
				this.batchSelectCombo.style.display = "block";
				this.batchSelectLabel.style.display = "block";
			}
			else {
				this.batchSelectCombo.style.display = "none";
				this.batchSelectLabel.style.display = "none";
			}
		}
	}

	getPrompts() {
		let prompts = {};

		for(let name in this.prompts) {
			let item = this.prompts[name];
			var new_item;

			for(let key in item) {
				switch(key) {
				case "BASIC_PIPE":
					new_item =
						{
							type: key,
							checkpoint: item[key].checkpoint.value,
							positive: item[key].positive.value,
							negative: item[key].negative.value
						};
					break;

				case "VAE":
					if(item[key].checkpoint)
						new_item = { type: key, checkpoint: item[key].checkpoint.value }
					else
						new_item = { type: key, vae: item[key].vae.value }
					break;

				case "MODEL":
					new_item = { type: key, checkpoint: item[key].value };
					break;

				case "CONDITIONING":
					new_item =
						{
							type: key,
							checkpoint: item[key].checkpoint.value,
							text_prompt: item[key].text_prompt.value
						};
					break;

				case "INT":
				case "FLOAT":
					new_item = { type:key, value: item[key].value, min: item[key].min, max: item[key].max };
					break;

				case "STRING":
				case "COMBO":
					new_item = { type:key, value: item[key].value };
					break;
				}
			}

			prompts[name] = new_item;
		}

		prompts['@IR_input_image'] = this.input_image;
		prompts['@IR_output_image'] = this.output_image;

		if(this.mask_name)
			prompts['@IR_mask'] = this.mask_name;

		return prompts;
	}

	isCanvasEmpty(canvas) {
		const context = canvas.getContext('2d', {willReadFrequently: true });
		const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
		const data = imageData.data;

		for (let i = 0; i < data.length; i += 4) {
			if (data[i] !== 0 || data[i + 1] !== 0 || data[i + 2] !== 0 || data[i + 3] !== 0) {
				return false;
			}
		}

		return true;
	}

	async loadAndReplaceImage() {
		const fileInput = document.createElement("input");
		Object.assign(fileInput, {
			type: "file",
			accept: "image/jpeg,image/png,image/webp",
			style: "display: none",
			onchange: async () => {
				if (fileInput.files.length) {
					if(confirm("Current results will be lost. Do you want to continue?")) {
						let url = await uploadFile(fileInput.files[0], true);

						ComfyApp.clipspace.imgs[ComfyApp.clipspace['selectedIndex']].src = url;
						this.show();
					}
				}
			},
		});

		fileInput.click();
	}

	async load_imageitem_to_canvas(data, canvas) {
		let path = `view?filename=${data.name}&subfolder=${data.subfolder}&type=${data.type}&no-cache=${Date.now()}`;
		return await load_image_to_canvas(path, canvas);
	}

    async import_work() {
        let self = this;

		const fileInput = document.createElement("input");
		Object.assign(fileInput, {
			type: "file",
			accept: ".imagerefiner",
			style: "display: none",
			onchange: async () => {
				if (fileInput.files.length) {
					if(confirm("Current results will be lost. Do you want to continue?")) {
						let json_data = await uploadWork(fileInput.files[0]);
						let prompt_data = json_data.prompt_data;
						// phase1:  set load base image and initialize state
						if(ComfyApp.clipspace.imgs[ComfyApp.clipspace['selectedIndex']])
						    delete ComfyApp.clipspace.imgs[ComfyApp.clipspace['selectedIndex']].cache;

						ComfyApp.clipspace.imgs[ComfyApp.clipspace['selectedIndex']].src = itemToImagepath(prompt_data.base_image_path);
						await self.show();
						while(!self.image.complete) {
							await (new Promise(resolve => setTimeout(resolve, 100)));
						}

						// phase2: mask, layer, prompt set
						// load base mask
						let base_mask_path = `view?filename=mask_base.png&subfolder=imagerefiner&type=temp&no-cache=${Date.now()}`;
						await load_image_to_canvas(base_mask_path, self.maskCanvas);

						// load layers
						for(let i in json_data.layers_data) {
							let layer = json_data.layers_data[i];
							await self.addLayer_from_import(layer);
						}

						// prompt load
						for (let i = 0; i < self.componentSelectCombo.options.length; i++) {
						  if (self.componentSelectCombo.options[i].value === prompt_data.component_name) {
						    self.componentSelectCombo.value = prompt_data.component_name;
						    await self.invalidatePromptControls(prompt_data);
						    break;
						  }
						}
					}
				}
			},
		});

		fileInput.click();
    }

	async add_draw_to_layer() {
		let mask = getOriginalSizeMaskCanvas(this.maskCanvas, this.image, !this.is_mask_mode);
		let layer = await this.addLayer([], mask, null);
		this.maskCtx.clearRect(0,0,this.maskCanvas.width,this.maskCanvas.height);
		this.invalidateLayerItem(layer);
	}

	async generative_fill() {
		if(!this.is_generating) {
		    var whole_inpaint = false;
			if(this.isCanvasEmpty(this.maskCanvas)) {
			    if(confirm("The current mask is empty. Would you like to inpaint the entire area?")) {
			        whole_inpaint = true;
			    }
			    else
				    return;
			}

			this.is_generating = true;

			this.fillButton.textContent = "Stop";
			this.fillButton.style.backgroundColor = "red";
			this.fillButton.style.Color = "white";

			this.saveButton.disabled = true;

			try {
				if(this.seeds.length == 0 || this.batchSelectCombo.value == 1) {
					let prompt_data = this.getPrompts();
					let mask = getOriginalSizeMaskCanvas(this.maskCanvas, this.image, !this.is_mask_mode, whole_inpaint);
					let generated_image = await generate(this.componentSelectCombo.value, prompt_data, mask, this.image, this.layers);
					await this.addLayer([generated_image], mask, prompt_data);
					this.maskCtx.clearRect(0,0,this.maskCanvas.width,this.maskCanvas.height);
				}
				else {
					let mask = getOriginalSizeMaskCanvas(this.maskCanvas, this.image, !this.is_mask_mode, whole_inpaint);
					let cands = [];

					// increase seed
					var prompt_data;
					for(let i = 0; i<this.batchSelectCombo.value; i++) {
						for(let x in this.seeds) {
							if(this.seeds[x].numberInput) {
								if(this.seeds[x].numberInput.value == this.seeds[x].numberInput.max)
									this.seeds[x].numberInput.value = Number(this.seeds[x].numberInput.min);
								else
									this.seeds[x].numberInput.value = Number(this.seeds[x].numberInput.value) + Number(this.seeds[x].numberInput.step);
							}
						}

						prompt_data = this.getPrompts();

						this.fillButton.setProgress(100*i/this.batchSelectCombo.value);
						let generated_image = await generate(this.componentSelectCombo.value, prompt_data, mask, this.image, this.layers);
						cands.push(generated_image);
					}

					let layer = await this.addLayer(cands, mask, prompt_data); // save last prompt_data
					this.maskCtx.clearRect(0,0,this.maskCanvas.width,this.maskCanvas.height);
					this.open_cands_selector(layer);
				}
			}
			catch(exception) {
				console.log(exception);
			}

			this.fillButton.textContent = "Regenerate";
			this.fillButton.stopProgress();

			this.is_generating = false;
			this.saveButton.disabled = false;
		}
		else {
			api.interrupt();
		}
	}

	setlayout(imgCanvas, maskCanvas) {
		const self = this;

		// Control layout
		this.bottomPanel = document.createElement("div");
		this.bottomPanel.style.height = "50px";
		this.bottomPanel.style.width = "calc(100% - 60px)";
		this.bottomPanel.style.top = "calc(100% - 60px)";
		this.bottomPanel.style.position = "absolute";
		this.bottomPanel.style.alignItems = "center";
		this.bottomPanel.style.marginTop = "17px";
		this.bottomPanel.id = "my-control-div";

		// Title
		this.topPanel = document.createElement("div");
		this.topPanel.style.margin = "0 10px";
		this.topPanel.style.height = "40px";

		const titleLabel = document.createElement("label");
		titleLabel.textContent = 'Image Refiner';
		titleLabel.style.cssFloat = "left";
		titleLabel.style.color = 'white';
		titleLabel.style.fontWeight = 'bold';
		titleLabel.style.fontSize = "20px";
		this.topPanel.appendChild(titleLabel);

		// Left div
		this.leftDiv = document.createElement("div");
		this.leftDiv.id = "my-left-div";
		this.leftDiv.style.width = "calc(100% - 280px)";
		this.leftDiv.style.height = "calc(100% - 120px)";
		this.leftDiv.style.position = "absolute";
		this.leftDiv.style.overflow = "hidden";
//		this.leftDiv.style.background = "black";

		// Right div
		this.rightDiv = document.createElement("div");
		this.rightDiv.id = "my-right-div";
		this.rightDiv.style.width = "223px";
//		this.rightDiv.style.background = "blue";
		this.rightDiv.style.position = "absolute";
		this.rightDiv.style.left = "calc(100% - 250px)";
		this.rightDiv.style.height = "calc(100% - 120px)";
		this.rightDiv.style.overflow = "none";

		// layer control
		this.layers = [];
		this.layer_list = document.createElement("div");
		this.layer_list.classList.add("layer-list");
		this.layer_list.style.width = "100%";
		this.layer_list.style.height = "30%";
		this.layer_list.style.overflowY = "scroll";
		this.layer_list.style.background = "#0F0F0F";

		// prompt controls
		this.prompt_controls = document.createElement("div");
		this.prompt_controls.classList.add("layer-list");
		this.prompt_controls.style.width = "calc(100%-40px)";
		this.prompt_controls.style.height = "70%";
		this.prompt_controls.style.top = "30%";
		this.prompt_controls.style.overflowY = "scroll";
		this.prompt_controls.style.background = "#0F0F0F";

		// Append the elements to the layer control
		this.element.appendChild(this.topPanel);
		this.element.appendChild(this.bottomPanel);
		this.element.appendChild(this.rightDiv);
		this.element.appendChild(this.leftDiv);

		var lineBreak = document.createElement('div');
		lineBreak.style.height = "3px";

		this.rightDiv.appendChild(this.layer_list);
		this.rightDiv.appendChild(lineBreak);
		this.rightDiv.appendChild(this.prompt_controls);

		var brush = document.createElement("div");
		brush.id = "brush";
		brush.style.backgroundColor = "transparent";
		brush.style.outline = "1px dashed black";
		brush.style.boxShadow = "0 0 0 1px white";
		brush.style.borderRadius = "50%";
		brush.style.MozBorderRadius = "50%";
		brush.style.WebkitBorderRadius = "50%";
		brush.style.position = "absolute";
		brush.style.zIndex = 8889;
		brush.style.pointerEvents = "none";
		this.brush = brush;
		document.body.appendChild(brush);

		let brush_size_slider = this.createRightSlider(self, "Thick.", (event) => {
			self.brush_size = event.target.value;
			self.updateBrushPreview(self, null, null);
		});

		// color picker
		var colorPicker = document.createElement('input');

		colorPicker.style.cssFloat = "right";
		colorPicker.style.height = "32px";
		colorPicker.style.marginRight = "5px";
		colorPicker.type = 'color';
		colorPicker.addEventListener('change', function(event) {
			self.selectedColor = event.target.value;
		});

		self.selectedColor = null;
		self.is_mask_mode = true;

		// pen mode change
		var toggleControl = createToggleControl();
		toggleControl.style.cssFloat = "right";
		toggleControl.style.marginRight = "5px";

		toggleControl.addEventListener('change', function(event) {
			var isChecked = event.target.checked;
			var penText = document.querySelector('.pen-text');
			var maskText = document.querySelector('.mask-text');
			if (isChecked) {
				penText.style.opacity = '1';
				maskText.style.opacity = '0';
				self.fillButton.textContent = "Add to layer";
				self.is_mask_mode = false;
			} else {
				penText.style.opacity = '0';
				maskText.style.opacity = '1';
				this.fillButton.textContent = "Regenerate";
				this.fillButton.stopProgress();
				self.is_mask_mode = true;
			}
		});

		let clearButton = this.createRightButton("Clear",
			() => {
				self.maskCtx.clearRect(0, 0, self.maskCanvas.width, self.maskCanvas.height);
				self.backupCtx.clearRect(0, 0, self.backupCanvas.width, self.backupCanvas.height);
			});

		let openImageButton = this.createLeftButton("Show image", async () => {
			let url = await gen_flatten(this.image, this.layers);
			window.open(url, "_blank");
		});

		let loadImageButton = this.createLeftButton("Load image", () => {
			self.loadAndReplaceImage();
		});

		this.bottomPanel.appendChild(openImageButton);
		this.bottomPanel.appendChild(loadImageButton);

		clearButton.style.marginRight = "20px";

		this.fillButton = this.createProgressButton("Regenerate", () => {
				if(self.is_mask_mode)
					self.generative_fill.call(self);
				else
					self.add_draw_to_layer.call(self);
			});
		this.fillButton.style.width = "135px";

		let flattenButton = this.createRightButton("Flatten", async () => {
			if(confirm('Once all layers are merged, it cannot be undone. Do you want to continue?')) {
				let url = await gen_flatten(this.image, this.layers);

				ComfyApp.clipspace.imgs[ComfyApp.clipspace['selectedIndex']].src = url;
				this.show();
			}
		});

		let cancelButton = this.createRightButton("Cancel", () => {
			document.removeEventListener("mouseup", ImageRefinerDialog.handleMouseUp);
			self.close();
            self.is_visible = false;
		});

		this.saveButton = this.createRightButton("Save", async () => {
				self.fillButton.disabled = true;
				this.disabled = true;
				document.removeEventListener("mouseup", ImageRefinerDialog.handleMouseUp);
				await save_to_clipspace(this.image, this.layers);
				ComfyApp.onClipspaceEditorSave();
				self.close();
				this.disabled = false;
				self.fillButton.disabled = false;
				self.is_visible = false;
			});

		let exportButton = this.createRightButton("Export Work", async () => {
				let prompt_data = this.getPrompts();
				await export_work(this.componentSelectCombo.value, prompt_data, this.maskCanvas, this.image, this.layers);
			});

		let importButton = this.createRightButton("Import Work", async () => {
                self.import_work();
			});

		this.componentSelectCombo = this.createComponentSelectCombo();
		let batchSelectCombo = this.createSelectCombo('#cand', 3, 1, 100);
		this.batchSelectCombo = batchSelectCombo.combo;
		this.batchSelectLabel = batchSelectCombo.label;

		let featherSelectCombo = this.createSelectCombo('feather', 3, 0, 100);
		this.featherSelectCombo = featherSelectCombo.combo;

		this.leftDiv.appendChild(imgCanvas);
		this.leftDiv.appendChild(maskCanvas);

		this.topPanel.appendChild(this.saveButton);
		this.topPanel.appendChild(cancelButton);
		this.topPanel.appendChild(importButton);
		this.topPanel.appendChild(exportButton);
		this.topPanel.appendChild(flattenButton);

		this.bottomPanel.appendChild(this.fillButton);
		this.bottomPanel.appendChild(toggleControl);
		this.bottomPanel.appendChild(this.batchSelectCombo);
		this.bottomPanel.appendChild(batchSelectCombo.label);
//		this.bottomPanel.appendChild(featherSelectCombo.label);
//		this.bottomPanel.appendChild(this.featherSelectCombo);

		this.bottomPanel.appendChild(this.componentSelectCombo);

		this.bottomPanel.appendChild(brush_size_slider);
		this.bottomPanel.appendChild(colorPicker);
		this.bottomPanel.appendChild(clearButton);

		imgCanvas.style.position = "absolute";
		imgCanvas.style.top = "0";
		imgCanvas.style.left = "0";

		maskCanvas.style.position = "absolute";
	}

	async addLayer_from_import(layer) {
		let mask_canvas = document.createElement("canvas");
		let mask_path = `view?filename=mask_${layer.id}.png&subfolder=imagerefiner&type=temp&no-cache=${Date.now()}`;
		await load_image_to_canvas(mask_path, mask_canvas);

		// load cands
		var image_paths = [];
		if(layer.cands) {
			image_paths = layer.cands;
		}
		let added_layer = await this.addLayer(image_paths, mask_canvas, layer.prompt_data, layer.is_visible);

        if(added_layer.prompt_data)
            for(let i in added_layer.prompt_data.image_paths) {
                let item = added_layer.prompt_data.image_paths[i];
                if(item.is_mask_mode == false) {
                    let layer_prompt_mask_canvas = document.createElement("canvas");
                    let layer_prompt_mask_path = `view?filename=draw_${item.id}.png&subfolder=imagerefiner&type=temp&no-cache=${Date.now()}`;
                    await load_image_to_canvas(layer_prompt_mask_path, layer_prompt_mask_canvas);
                    item.mask = layer_prompt_mask_canvas;
                }
            }

		if(layer.cands) {
			let selected_index = null;
			layer.cands.forEach((cand, index) => {
				if (cand.filename === layer.image.filename) {
					selected_index = index;
					return;
				}
			});

			added_layer.image = added_layer.cands[selected_index];
		}
		else {
		    // draw restore
            await load_image_to_canvas(mask_path, mask_canvas);
		}

		this.invalidateLayerItem(added_layer);
	}

	async addLayer(image_paths, mask, prompt_data, is_visible) {
		let self = this;
		let image = new Image();

		const layerItem = document.createElement("div");
		const visibilityCheckbox = document.createElement("input");

		const layer = {
			id: this.layer_id,
			canvas: document.createElement("canvas"),
			mask: mask,
			layerItem: layerItem,
			visibilityCheckbox: visibilityCheckbox,
			prompt_data: prompt_data,
			cands: [],
		};
		this.layers.push(layer);
		this.layer_id++;

		layer.canvas.width = this.image.width;
		layer.canvas.height = this.image.height;
		this.invalidatePanZoom(layer.canvas);

		this.element.appendChild(layer.canvas);

		layerItem.classList.add("layer-item");

		visibilityCheckbox.type = "checkbox";
		if(is_visible != null)
		    visibilityCheckbox.checked = is_visible;
		else
		    visibilityCheckbox.checked = true;

        if (visibilityCheckbox.checked) {
            layer.canvas.style.display = "block";
        } else {
            layer.canvas.style.display = "none";
        }

		visibilityCheckbox.addEventListener("change", (event) => {
			const isChecked = event.target.checked;
			if (isChecked) {
				layer.canvas.style.display = "block";
			} else {
				layer.canvas.style.display = "none";
			}
		});

		layerItem.appendChild(visibilityCheckbox);

		const flattenButton = document.createElement("button");
		flattenButton.innerText = "F";
		flattenButton.style.fontSize = "10px";
		flattenButton.style.height = "20px";
		flattenButton.addEventListener("click", () => {
			this.flattenLayer(layer);
			this.removeLayer(layer);
		});

		var regenerateButton;
		if(prompt_data) {
			regenerateButton = document.createElement("button");
			regenerateButton.innerText = "R";
			regenerateButton.title = "Discard the image of this layer and create a new one";
			regenerateButton.style.fontSize = "10px";
			regenerateButton.style.height = "20px";
			regenerateButton.addEventListener("click", () => {
				this.regenerateLayer(layer);
			});
		}

		var reselectButton = null;
		if(image_paths.length > 1) {
			reselectButton = document.createElement("button");
			reselectButton.title = "Re-select the candidate image of this layer";
			reselectButton.innerText = "S";
			reselectButton.style.fontSize = "10px";
			reselectButton.style.height = "20px";
			reselectButton.addEventListener("click", () => {
				this.open_cands_selector(layer);
			});
		}

		const maskButton = document.createElement("button");
		maskButton.title = "Retrieve the mask of this layer";
		maskButton.innerText = "M";
		maskButton.style.fontSize = "10px";
		maskButton.style.height = "20px";
		maskButton.addEventListener("click", () => {
			this.maskRestoreFromLayer(layer);
		});

		const deleteButton = document.createElement("button");
		deleteButton.title = "Discard layer";
		deleteButton.innerText = "X";
		deleteButton.style.fontSize = "10px";
		deleteButton.style.height = "20px";
		deleteButton.addEventListener("click", () => {
			this.removeLayer(layer);
		});

		let label = document.createElement('span');
		label.textContent = `Layer ${layer.id}`;
		label.style.color = 'var(--descrip-text)';
		label.style.display = 'inline-block';
		label.style.width = "90px";

		layerItem.appendChild(label);
//		layerItem.appendChild(flattenButton);

		if(regenerateButton) {
			layerItem.appendChild(regenerateButton);
		}

		if(reselectButton)
			layerItem.appendChild(reselectButton);

		layerItem.appendChild(maskButton);
		layerItem.appendChild(deleteButton);
		const callButton = document.createElement("button");
		callButton.innerText = "Call";

        layerItem.deselect = () => {
                layerItem.style.backgroundColor = '';
                label.style.color = 'var(--descrip-text)';
                self.selectedLayerItem = null;
            };

        layerItem.select = async () => {
		        if(self.selectedLayerItem)
		            self.selectedLayerItem.deselect();
                else {
                    self.non_select_prompt = this.getPrompts();
                    self.non_select_prompt.component_name = self.componentSelectCombo.value;
                }

                self.selectedLayerItem = layerItem;
                layerItem.style.backgroundColor = "#3F3F3F";
                label.style.color = 'white';

                if(layer.prompt_data) {
                    for (let i = 0; i < self.componentSelectCombo.options.length; i++) {
                      if (self.componentSelectCombo.options[i].value === layer.prompt_data.component_name) {
                        self.componentSelectCombo.value = layer.prompt_data.component_name;
                        await self.invalidatePromptControls(layer.prompt_data);
                        break;
                      }
                    }
                }
            };

        layerItem.layer = layer;

		label.onclick = () => {
                if(self.selectedLayerItem != layerItem) {
                    layerItem.select();
		        }
		        else {
                    layerItem.deselect();

                    if(self.non_select_prompt) {
                        for (let i = 0; i < self.componentSelectCombo.options.length; i++) {
                            if (self.componentSelectCombo.options[i].value === self.non_select_prompt.component_name) {
                                self.componentSelectCombo.value = self.non_select_prompt.component_name;
                                self.invalidatePromptControls(self.non_select_prompt);
                                break;
                            }
                        }
                    }
		        }
		    };

		await this.resolve_image_for_image(layer, image_paths);

		layer.canvas.style.position = "absolute";
		layer.canvas.id = `imagerefine-layer-${layer.id}`;
		this.leftDiv.insertBefore(layer.canvas, this.maskCanvas);
		this.layer_list.appendChild(layerItem);

		return layer;
	}

	removeLayer(item) {
		const layerIndex = this.layers.findIndex((layer) => layer.id === item.id);
		if (layerIndex !== -1) {
			const layer = this.layers[layerIndex];
			this.layer_list.removeChild(item.layerItem);
			this.leftDiv.removeChild(layer.canvas);
			this.layers.splice(layerIndex, 1);
		}
	}

	flattenLayer(item) {

	}

	async resolve_image_for_image(layer, image_paths) {
		let self = this;
		for(let i in image_paths) {
			let image_path = image_paths[i];
		    let url = `view?filename=${image_path.filename}&subfolder=${image_path.subfolder}&type=${image_path.type}${app.getPreviewFormatParam()}&no-cache=${Date.now()}`

            let image = await loadImage(url);

			if(i == 0) {
				layer.image = image;
                self.invalidateLayerItem(layer);
			}

			layer.cands.push(image);
		}
	}

	async regenerateLayer(layer) {
		if(!this.is_generating) {
			this.is_generating = true;
			this.saveButton.disabled = true;

			this.fillButton.textContent = "Stop";
			this.fillButton.style.backgroundColor = "red";
			this.fillButton.style.Color = "white";

			let mask = layer.mask;
			let cands = [];

			const new_prompt = Object.assign({}, layer.prompt_data);

			// increase seed
			let regen_count = this.batchSelectCombo.value;
			if(this.batchSelectCombo.style.display == "none") {
				regen_count = 1;
			}

			for(let i = 0; i<regen_count; i++) {
				for(let name in new_prompt) {
					if(name == "seed" || name.startsWith("seed.")) {
						let seed = new_prompt[name];
						const min = parseFloat(seed.min);
						const max = parseFloat(seed.max);
						seed.value =  Math.floor(Math.random() * (max - min + 1)) + min;
					}
				}

				let prompt_data = this.getPrompts();

                this.fillButton.setProgress(100*i/regen_count);
				let generated_image = await generate(this.componentSelectCombo.value, new_prompt, mask, this.image, null, layer.prompt_data.image_paths);
				cands.push(generated_image);
			}

			layer.cands = []; // remove prev result
			await this.resolve_image_for_image(layer, cands);

			if(regen_count > 1)
				this.open_cands_selector(layer);

			this.fillButton.textContent = "Regenerate";
			this.fillButton.stopProgress();

			this.is_generating = false;
			this.saveButton.disabled = false;
		}
	}

	maskRestoreFromLayer(item) {
		let maskCtx = this.maskCanvas.getContext('2d', {willReadFrequently: true });
		maskCtx.clearRect(0, 0, this.maskCanvas.width, this.maskCanvas.height);

		// Create a temporary canvas for modifying the alpha channel
		let tempCanvas = document.createElement('canvas');
		let tempCtx = tempCanvas.getContext('2d', {willReadFrequently: true });

		// Set the dimensions of the temporary canvas
		tempCanvas.width = item.mask.width;
		tempCanvas.height = item.mask.height;

		// Draw the original item.mask onto the temporary canvas
		tempCtx.drawImage(item.mask, 0, 0);

		// Get the image data of the temporary canvas
		let imageData = tempCtx.getImageData(0, 0, tempCanvas.width, tempCanvas.height);
		let data = imageData.data;

		if(item.prompt_data) {
			// Invert the alpha channel
			for (let i = 0; i < data.length; i += 4) {
				data[i + 3] = 255 - data[i + 3]; // Invert alpha channel
			}
		}

		// Put the modified image data back onto the temporary canvas
		tempCtx.putImageData(imageData, 0, 0);

		// Draw the modified temporary canvas onto the maskCanvas
		maskCtx.drawImage(tempCanvas, 0, 0, this.maskCanvas.width, this.maskCanvas.height);
	}

	clearLayers() {
		if(this.leftDiv) {
			while (this.leftDiv.firstChild) {
				this.leftDiv.removeChild(this.leftDiv.firstChild);
			}

			while (this.layer_list.firstChild) {
				this.layer_list.removeChild(this.layer_list.firstChild);
			}

			this.layers = [];

			if(this.imgCanvas) {
				this.leftDiv.append(this.imgCanvas);
			}

			if(this.maskCanvas) {
				this.leftDiv.append(this.maskCanvas);
			}
		}
	}

	async show() {
		this.zoom_ratio = 1.0;
		this.pan_x = 0;
		this.pan_y = 0;

		this.clearLayers();
		this.defs = await api.getNodeDefs();

		if(!this.is_layout_created) {
			// layout
			const imgCanvas = document.createElement('canvas');
			const maskCanvas = document.createElement('canvas');
			const backupCanvas = document.createElement('canvas');

			imgCanvas.id = "imageCanvas";
			maskCanvas.id = "maskCanvas";
			backupCanvas.id = "backupCanvas";

			this.setlayout(imgCanvas, maskCanvas);
			this.invalidateComponentSelectCombo();
			this.invalidatePromptControls();

			// prepare content
			this.imgCanvas = imgCanvas;
			this.maskCanvas = maskCanvas;
			this.backupCanvas = backupCanvas;
			this.maskCtx = maskCanvas.getContext('2d', {willReadFrequently: true });
			this.backupCtx = backupCanvas.getContext('2d', {willReadFrequently: true });

			this.setEventHandler(maskCanvas);

			this.is_layout_created = true;

			// replacement of onClose hook since close is not real close
			const self = this;
			const observer = new MutationObserver(function(mutations) {
			mutations.forEach(function(mutation) {
					if (mutation.type === 'attributes' && mutation.attributeName === 'style') {
						if(self.last_display_style && self.last_display_style != 'none' && self.element.style.display == 'none') {
                            document.removeEventListener("mouseup", ImageRefinerDialog.handleMouseUp);
                            self.brush.style.display = "none";
                            ComfyApp.onClipspaceEditorClosed();
						}

						self.last_display_style = self.element.style.display;
					}
				});
			});

			const config = { attributes: true };
			observer.observe(this.element, config);
		}

		if(ComfyApp.clipspace_return_node) {
			this.saveButton.innerText = "Save to node";
		}
		else {
			this.saveButton.innerText = "Save";
		}
		this.saveButton.disabled = false;

		this.element.style.display = "block";
		this.element.style.width = "85%";
		this.element.style.margin = "0 7.5%";
		this.element.style.height = "100vh";
		this.element.style.top = "50%";
		this.element.style.left = "42%";
		this.element.style.zIndex = 8888; // NOTE: alert dialog must be high priority.

		await this.setImages(this.imgCanvas, this.backupCanvas);

	    this.is_visible = true;
	}

	isOpened() {
		return this.element.style.display == "block";
	}

	invalidateCanvas(orig_image) {
		this.imgCanvas.width = orig_image.width;
		this.imgCanvas.height = orig_image.height;

		this.maskCanvas.width = orig_image.width;
		this.maskCanvas.height = orig_image.height;

		let imgCtx = this.imgCanvas.getContext('2d', {willReadFrequently: true });
		let maskCtx = this.maskCanvas.getContext('2d', {willReadFrequently: true });

		imgCtx.drawImage(orig_image, 0, 0, orig_image.width, orig_image.height);
		maskCtx.clearRect(0, 0, orig_image.width, orig_image.height);

		for (const layer of this.layers) {
			this.invalidateLayerItem(layer);
		}
	}

	async setImages(imgCanvas, backupCanvas) {
		let self = this;

		const imgCtx = imgCanvas.getContext('2d', {willReadFrequently: true });
		const backupCtx = backupCanvas.getContext('2d', {willReadFrequently: true });
		const maskCtx = this.maskCtx;
		const maskCanvas = this.maskCanvas;

		backupCtx.clearRect(0,0,this.backupCanvas.width,this.backupCanvas.height);
		imgCtx.clearRect(0,0,this.imgCanvas.width,this.imgCanvas.height);
		maskCtx.clearRect(0,0,this.maskCanvas.width,this.maskCanvas.height);

		// image load
//		window.addEventListener("resize", () => this.onResize.call(this, orig_image) );
		const filepath = ComfyApp.clipspace.images;

		const alpha_url = new URL(ComfyApp.clipspace.imgs[ComfyApp.clipspace['selectedIndex']].src)
		alpha_url.searchParams.delete('channel');
		alpha_url.searchParams.delete('preview');
		alpha_url.searchParams.set('channel', 'a');
		let touched_image = await loadImage(alpha_url);

        backupCanvas.width = touched_image.width;
        backupCanvas.height = touched_image.height;

        prepareRGB(touched_image, backupCanvas, backupCtx);

		// original image load
		const rgb_url = new URL(ComfyApp.clipspace.imgs[ComfyApp.clipspace['selectedIndex']].src);
		rgb_url.searchParams.delete('channel');
		rgb_url.searchParams.set('channel', 'rgb');
		this.image = await loadImage(rgb_url);

        this.invalidateCanvas(this.image);
        this.initializeCanvasPanZoom();
	}

	initializeCanvasPanZoom() {
		// set initialize
		let drawWidth = this.image.width;
		let drawHeight = this.image.height;

		let width = this.leftDiv.clientWidth;
		let height = this.leftDiv.clientHeight;

		if (this.image.width > width) {
			drawWidth = width;
			drawHeight = (drawWidth / this.image.width) * this.image.height;
		}

		if (drawHeight > height) {
			drawHeight = height;
			drawWidth = (drawHeight / this.image.height) * this.image.width;
		}

		this.zoom_ratio = drawWidth/this.image.width;

		const canvasX = (width - drawWidth) / 2;
		const canvasY = (height - drawHeight) / 2;
		this.pan_x = canvasX;
		this.pan_y = canvasY;

		this.invalidatePanZoom();
	}

	// canvas == null -> invalidate all
	invalidatePanZoom(canvas) {
		let raw_width = this.image.width * this.zoom_ratio;
		let raw_height = this.image.height * this.zoom_ratio;

		if(this.pan_x + raw_width < 10) {
			this.pan_x = 10 - raw_width;
		}

		if(this.pan_y + raw_height < 10) {
			this.pan_y = 10 - raw_height;
		}

		let width = `${raw_width}px`;
		let height = `${raw_height}px`;

		let left = `${this.pan_x}px`;
		let top = `${this.pan_y}px`;

		if(canvas) {
			canvas.style.width = width;
			canvas.style.height = height;
			canvas.style.left = left;
			canvas.style.top = top;
		}
		else {
			this.imgCanvas.style.width = width;
			this.imgCanvas.style.height = height;
			this.imgCanvas.style.left = left;
			this.imgCanvas.style.top = top;

			this.maskCanvas.style.width = width;
			this.maskCanvas.style.height = height;
			this.maskCanvas.style.left = left;
			this.maskCanvas.style.top = top;

			for(let x in this.layers) {
				let canvas = this.layers[x].canvas;
				canvas.style.width = width;
				canvas.style.height = height;
				canvas.style.left = left;
				canvas.style.top = top;
			}
		}
	}

	setEventHandler(maskCanvas) {
		const self = this;

		if(!this.handler_registered) {
			maskCanvas.addEventListener("contextmenu", (event) => {
				event.preventDefault();
			});

			this.element.addEventListener('wheel', (event) => this.handleWheelEvent.call(self,event));
			this.element.addEventListener('pointermove', (event) => this.pointMoveEvent(self,event));
			this.element.addEventListener('touchmove', (event) => this.pointMoveEvent(self,event));

			this.element.addEventListener('dragstart', (event) => {
				if(event.ctrlKey) {
					event.preventDefault();
				}
			});

			maskCanvas.addEventListener('pointerdown', (event) => this.handlePointerDown(self,event));
			maskCanvas.addEventListener('pointermove', (event) => this.draw_move(self,event));
			maskCanvas.addEventListener('touchmove', (event) => this.draw_move(self,event));
			maskCanvas.addEventListener('pointerover', (event) => { this.brush.style.display = "block"; });
			maskCanvas.addEventListener('pointerleave', (event) => { this.brush.style.display = "none"; });

            document.addEventListener('pointerup', ImageRefinerDialog.handlePointerUp);
            document.addEventListener('keydown', ImageRefinerDialog.handleKeyDown);

			this.handler_registered = true;
		}
	}

	brush_size = 10;
	drawing_mode = false;
	lastx = -1;
	lasty = -1;
	lasttime = 0;

	static handleKeyDown(event) {
		const self = ImageRefinerDialog.instance;

	    if(!self.is_visible)
	        return;

		if (event.key === ']') {
			self.brush_size = Math.min(self.brush_size+2, 100);
		} else if (event.key === '[') {
			self.brush_size = Math.max(self.brush_size-2, 1);
		}
		else if(event.key === 'Escape') {
            if(confirm("All current work will be lost. Are you sure you want to close it?")) {
                self.close();
            }
            else {
		        self.element.style.display = "block";
            }
		}

		self.updateBrushPreview(self);
	}

	static handlePointerUp(event) {
		event.preventDefault();

		this.mousedown_x = null;
		this.mousedown_y = null;

		ImageRefinerDialog.instance.drawing_mode = false;
	}

	updateBrushPreview(self) {
		const brush = self.brush;

		var centerX = self.cursorX;
		var centerY = self.cursorY;

		brush.style.width = self.brush_size * 2 * this.zoom_ratio + "px";
		brush.style.height = self.brush_size * 2 * this.zoom_ratio + "px";
		brush.style.left = (centerX - self.brush_size * this.zoom_ratio) + "px";
		brush.style.top = (centerY - self.brush_size * this.zoom_ratio) + "px";
	}

	handleWheelEvent(event) {
		event.preventDefault();

		if(event.ctrlKey) {
			// zoom canvas
			if(event.deltaY < 0) {
				this.zoom_ratio = Math.min(10.0, this.zoom_ratio+0.2);
			}
			else {
				this.zoom_ratio = Math.max(0.2, this.zoom_ratio-0.2);
			}

			this.invalidatePanZoom();
		}
		else {
			// adjust brush size
			if(event.deltaY < 0)
				this.brush_size = Math.min(this.brush_size+2, 100);
			else
				this.brush_size = Math.max(this.brush_size-2, 1);

			this.brush_slider_input.value = this.brush_size;

			this.updateBrushPreview(this);
		}
	}

	pointMoveEvent(self, event) {
		this.cursorX = event.pageX;
		this.cursorY = event.pageY;

		self.updateBrushPreview(self);

		if(event.ctrlKey) {
			event.preventDefault();
			self.pan_move(self, event);
		}
	}

	pan_move(self, event) {
		if(event.buttons == 1) {
			if(this.mousedown_x) {
				let deltaX = this.mousedown_x - event.clientX;
				let deltaY = this.mousedown_y - event.clientY;

				self.pan_x = this.mousedown_pan_x - deltaX;
				self.pan_y = this.mousedown_pan_y - deltaY;

				self.invalidatePanZoom();
			}
		}
	}

    edit_layer(layer, is_drawing, x, y, brush_sze) {
        // todo
    }

    edit_layer_cont(layer, is_drawing, directionX, directionY, distance, brush_sze) {
        // todo
    }

	draw_move(self, event) {
	    var layer_draw_mode = false;

		if(event.ctrlKey) {
			return;
		}

		if(event.altKey) {
		    if(self.selectedLayerItem) {
		        layer_draw_mode = true;
		    }
		}

		if (window.TouchEvent && event instanceof TouchEvent || event.buttons == 1) {
			var diff = performance.now() - self.lasttime;

			const maskRect = self.maskCanvas.getBoundingClientRect();

			var x = event.offsetX;
			var y = event.offsetY

			if(event.offsetX == null) {
				x = event.targetTouches[0].clientX - maskRect.left;
			}

			if(event.offsetY == null) {
				y = event.targetTouches[0].clientY - maskRect.top;
			}

			x /= self.zoom_ratio;
			y /= self.zoom_ratio;

			var brush_size = this.brush_size;
			if(event instanceof PointerEvent && event.pointerType == 'pen') {
				brush_size *= event.pressure;
				this.last_pressure = event.pressure;
			}
			else if(window.TouchEvent && event instanceof TouchEvent && diff < 20){
				// The firing interval of PointerEvents in Pen is unreliable, so it is supplemented by TouchEvents.
				brush_size *= this.last_pressure;
			}
			else {
				brush_size = this.brush_size;
			}

			var color;
			if(self.selectedColor) {
				color = self.selectedColor;
			}
			else {
				color = "rgb(0,0,0)";
			}

			if(diff > 20 && !this.drawing_mode)
				requestAnimationFrame(() => {
				    if(layer_draw_mode) {
				        self.edit_layer(self.selectedLayerItem.layer, true, x, y, brush_size);
				    }
				    else {
                        self.maskCtx.beginPath();
                        self.maskCtx.fillStyle = color;
                        self.maskCtx.fillStyle = self.selectedColor;
                        self.maskCtx.globalCompositeOperation = "source-over";
                        self.maskCtx.arc(x, y, brush_size, 0, Math.PI * 2, false);
                        self.maskCtx.fill();
					}

                    self.lastx = x;
                    self.lasty = y;
				});
			else
				requestAnimationFrame(() => {
                    var dx = x - self.lastx;
                    var dy = y - self.lasty;

                    var distance = Math.sqrt(dx * dx + dy * dy);
                    var directionX = dx / distance;
                    var directionY = dy / distance;

				    if(layer_draw_mode) {
				        self.edit_layer_cont(self.selectedLayerItem.layer, true, directionX, directionY, distance, brush_size);
				    }
				    else {
                        self.maskCtx.beginPath();
                        self.maskCtx.fillStyle = color;
                        self.maskCtx.globalCompositeOperation = "source-over";

                        for (var i = 0; i < distance; i+=5) {
                            var px = self.lastx + (directionX * i);
                            var py = self.lasty + (directionY * i);
                            self.maskCtx.arc(px, py, brush_size, 0, Math.PI * 2, false);
                            self.maskCtx.fill();
                        }
                    }

                    self.lastx = x;
                    self.lasty = y;
				});

			self.lasttime = performance.now();
		}
		else if(event.buttons == 2 || event.buttons == 5 || event.buttons == 32) {
			const maskRect = self.maskCanvas.getBoundingClientRect();
			const x = (event.offsetX || event.targetTouches[0].clientX - maskRect.left) / self.zoom_ratio;
			const y = (event.offsetY || event.targetTouches[0].clientY - maskRect.top) / self.zoom_ratio;

			var brush_size = this.brush_size;
			if(event instanceof PointerEvent && event.pointerType == 'pen') {
				brush_size *= event.pressure;
				this.last_pressure = event.pressure;
			}
			else if(window.TouchEvent && event instanceof TouchEvent && diff < 20){
				brush_size *= this.last_pressure;
			}
			else {
				brush_size = this.brush_size;
			}

			if(diff > 20 && !drawing_mode) // cannot tracking drawing_mode for touch event
				requestAnimationFrame(() => {
				    if(layer_draw_mode) {
				        self.edit_layer(self.selectedLayerItem.layer, false, x, y, brush_size);
				    }
				    else {
                        self.maskCtx.beginPath();
                        self.maskCtx.globalCompositeOperation = "destination-out";
                        self.maskCtx.arc(x, y, brush_size, 0, Math.PI * 2, false);
                        self.maskCtx.fill();
                        self.lastx = x;
                        self.lasty = y;
					}
				});
			else
				requestAnimationFrame(() => {
                    var dx = x - self.lastx;
                    var dy = y - self.lasty;

                    var distance = Math.sqrt(dx * dx + dy * dy);
                    var directionX = dx / distance;
                    var directionY = dy / distance;

				    if(layer_draw_mode) {
				        self.edit_layer_cont(self.selectedLayerItem.layer, false, directionX, directionY, distance, brush_size);
				    }
				    else {
                        self.maskCtx.beginPath();
                        self.maskCtx.globalCompositeOperation = "destination-out";

                        for (var i = 0; i < distance; i+=5) {
                            var px = self.lastx + (directionX * i);
                            var py = self.lasty + (directionY * i);
                            self.maskCtx.arc(px, py, brush_size, 0, Math.PI * 2, false);
                            self.maskCtx.fill();
                        }
                    }

					self.lastx = x;
					self.lasty = y;
				});

				self.lasttime = performance.now();
		}
	}

	handlePointerDown(self, event) {
		if(event.ctrlKey) {
			if (event.buttons == 1) {
				this.mousedown_x = event.clientX;
				this.mousedown_y = event.clientY;

				this.mousedown_pan_x = this.pan_x;
				this.mousedown_pan_y = this.pan_y;
			}
			return;
		}

		var brush_size = this.brush_size;
		if(event instanceof PointerEvent && event.pointerType == 'pen') {
			brush_size *= event.pressure;
			this.last_pressure = event.pressure;
		}

		if ([0, 2, 5].includes(event.button)) {
			self.drawing_mode = true;

			event.preventDefault();
			const maskRect = self.maskCanvas.getBoundingClientRect();
			const x = (event.offsetX || event.targetTouches[0].clientX - maskRect.left) / self.zoom_ratio;
			const y = (event.offsetY || event.targetTouches[0].clientY - maskRect.top) / self.zoom_ratio;

			self.maskCtx.beginPath();

			var color;
			if(self.selectedColor) {
				color = self.selectedColor;
			}
			else {
				color = "rgb(0,0,0)";
			}

			if (event.button == 0) {
				self.maskCtx.fillStyle = color;
				self.maskCtx.globalCompositeOperation = "source-over";
			} else {
				self.maskCtx.globalCompositeOperation = "destination-out";
			}
			self.maskCtx.arc(x, y, brush_size, 0, Math.PI * 2, false);
			self.maskCtx.fill();
			self.lastx = x;
			self.lasty = y;
			self.lasttime = performance.now();
		}
	}
}

app.registerExtension({
	name: "Comfy.WorkflowComponent.ImageRefiner",
	init(app) {
		ComfyApp.open_image_refiner =
			function () {
				const dlg = ImageRefinerDialog.getInstance();
				if(!dlg.isOpened()) {
					dlg.show();
				}
			};

		const context_predicate = () => ComfyApp.clipspace && ComfyApp.clipspace.imgs && ComfyApp.clipspace.imgs.length > 0
		ClipspaceDialog.registerButton("Image Refiner", context_predicate, ComfyApp.open_image_refiner);
	},

	async beforeRegisterNodeDef(nodeType, nodeData, app) {
		if (nodeData.output.includes("IMAGE")) {
			addMenuHandler(nodeType, function (_, options) {
				options.unshift({
					content: "Open in Image Refiner",
					callback: () => {
						ComfyApp.copyToClipspace(this);
						ComfyApp.clipspace_return_node = this;

						let dlg = ImageRefinerDialog.getInstance();
						dlg.show();
					},
				});
			});
		}
	}
});
