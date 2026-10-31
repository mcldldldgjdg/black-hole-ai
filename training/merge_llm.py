from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE = Path("/work/data/models/qwen2.5-3b-instruct")
OUT = Path("/work/data/out/llm")


def main():
    model = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.float16, device_map={"": "cpu"})
    model = PeftModel.from_pretrained(model, OUT / "adapter").merge_and_unload()
    model.save_pretrained(OUT / "merged", safe_serialization=True)
    AutoTokenizer.from_pretrained(BASE).save_pretrained(OUT / "merged")


if __name__ == "__main__":
    main()
