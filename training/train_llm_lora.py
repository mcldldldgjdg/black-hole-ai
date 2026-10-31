import json
import os
from pathlib import Path

import torch
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, Trainer, TrainingArguments

BASE = Path("/work/data/models/qwen2.5-3b-instruct")
DATA = Path("/work/data/llm")
OUT = Path("/work/data/out/llm")
MAX_LEN = 2048
EPOCHS = float(os.getenv("EPOCHS", "2"))


def load(name):
    return [json.loads(line) for line in (DATA / f"{name}.jsonl").open(encoding="utf-8")]


def encode(tok, example):
    prompt = tok.apply_chat_template(example["messages"][:-1], tokenize=False, add_generation_prompt=True)
    answer = example["messages"][-1]["content"] + "<|im_end|>\n"
    p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
    a_ids = tok(answer, add_special_tokens=False)["input_ids"]
    ids = (p_ids + a_ids)[:MAX_LEN]
    labels = ([-100] * len(p_ids) + a_ids)[:MAX_LEN]
    return {"input_ids": ids, "labels": labels}


class Collator:
    def __init__(self, pad_id):
        self.pad_id = pad_id

    def __call__(self, batch):
        n = max(len(b["input_ids"]) for b in batch)
        ids = torch.full((len(batch), n), self.pad_id)
        labels = torch.full((len(batch), n), -100)
        mask = torch.zeros((len(batch), n), dtype=torch.long)
        for i, b in enumerate(batch):
            k = len(b["input_ids"])
            ids[i, :k] = torch.tensor(b["input_ids"])
            labels[i, :k] = torch.tensor(b["labels"])
            mask[i, :k] = 1
        return {"input_ids": ids, "labels": labels, "attention_mask": mask}


def main():
    tok = AutoTokenizer.from_pretrained(BASE)
    train = [encode(tok, e) for e in load("train")]
    val = [encode(tok, e) for e in load("val")]
    print(f"train {len(train)}, val {len(val)}, max len {max(len(x['input_ids']) for x in train)}")

    model = AutoModelForCausalLM.from_pretrained(
        BASE,
        quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                               bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True),
        torch_dtype=torch.bfloat16,
        device_map={"": 0},
    )
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model = get_peft_model(model, LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    ))
    model.print_trainable_parameters()

    trainer = Trainer(
        model=model,
        train_dataset=train,
        eval_dataset=val,
        data_collator=Collator(tok.pad_token_id),
        args=TrainingArguments(
            output_dir=str(OUT / "checkpoints"),
            num_train_epochs=EPOCHS,
            per_device_train_batch_size=1,
            per_device_eval_batch_size=1,
            gradient_accumulation_steps=8,
            learning_rate=2e-4,
            lr_scheduler_type="cosine",
            warmup_ratio=0.05,
            logging_steps=5,
            eval_strategy="epoch",
            save_strategy="no",
            bf16=True,
            gradient_checkpointing=True,
            optim="paged_adamw_8bit",
            report_to="none",
        ),
    )
    before = trainer.evaluate()["eval_loss"]
    trainer.train()
    after = trainer.evaluate()["eval_loss"]
    model.save_pretrained(OUT / "adapter")
    tok.save_pretrained(OUT / "adapter")
    metrics = {"eval_loss_before": before, "eval_loss_after": after, "train_examples": len(train), "val_examples": len(val), "epochs": EPOCHS}
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(metrics)


if __name__ == "__main__":
    main()
