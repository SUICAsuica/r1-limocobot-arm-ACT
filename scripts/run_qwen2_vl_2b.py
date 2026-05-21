#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

import torch
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
from qwen_vl_utils import process_vision_info


DEFAULT_MODEL = Path.home() / "models" / "Qwen2-VL-2B-Instruct"


def build_messages(image_path: str, prompt: str):
    return [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image_path},
                {"type": "text", "text": prompt},
            ],
        }
    ]


def load_model(model_name: str):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device == "cuda" else torch.float32

    model = Qwen2VLForConditionalGeneration.from_pretrained(
        model_name,
        torch_dtype=dtype,
        device_map="auto" if device == "cuda" else None,
    )
    if device != "cuda":
        model = model.to(device)

    processor = AutoProcessor.from_pretrained(model_name)
    return model, processor


def run_inference(model, processor, image: str, prompt: str, max_new_tokens: int) -> str:
    messages = build_messages(image, prompt)
    text = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = processor(
        text=[text],
        images=image_inputs,
        videos=video_inputs,
        padding=True,
        return_tensors="pt",
    )
    inputs = inputs.to(model.device)

    generated_ids = model.generate(**inputs, max_new_tokens=max_new_tokens)
    trimmed_ids = [
        output_ids[len(input_ids):]
        for input_ids, output_ids in zip(inputs.input_ids, generated_ids)
    ]
    output_text = processor.batch_decode(
        trimmed_ids,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )
    return output_text[0]


def run_interactive(model, processor, default_max_new_tokens: int) -> None:
    print(
        "ready: send one JSON object per line, "
        'e.g. {"image": "/path/to/image.jpg", "prompt": "describe this"}',
        file=sys.stderr,
        flush=True,
    )
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            image = request["image"]
            prompt = request["prompt"]
            max_new_tokens = int(request.get("max_new_tokens", default_max_new_tokens))
            result = run_inference(model, processor, image, prompt, max_new_tokens)
            print(json.dumps({"ok": True, "text": result}, ensure_ascii=False), flush=True)
        except Exception as exc:
            print(
                json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False),
                flush=True,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Qwen2-VL-2B-Instruct on images.")
    parser.add_argument("image", nargs="?", help="Input image path")
    parser.add_argument("prompt", nargs="?", help="Prompt text")
    parser.add_argument(
        "--model",
        default=str(DEFAULT_MODEL),
        help="Model directory or Hugging Face model id",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=256,
        help="Maximum tokens to generate",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Load the model once and read JSON-line requests from stdin.",
    )
    args = parser.parse_args()

    if not args.interactive and (not args.image or not args.prompt):
        parser.error("image and prompt are required unless --interactive is used")

    model, processor = load_model(args.model)

    if args.interactive:
        run_interactive(model, processor, args.max_new_tokens)
    else:
        print(run_inference(model, processor, args.image, args.prompt, args.max_new_tokens))


if __name__ == "__main__":
    main()
