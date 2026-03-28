"""
Fine-tune a small language model with Unsloth + LoRA for caibinet.

The script trains on prompt→JSON completion pairs produced by generate_dataset.py,
then exports the adapter as a quantized GGUF file ready to load into Ollama.

Prerequisites
-------------
  pip install "unsloth[cu124-torch250] @ git+https://github.com/unslothai/unsloth.git"
  # OR, for CPU-only (very slow, testing only):
  pip install unsloth

Recommended base models (pick one):
  - unsloth/Qwen2.5-1.5B-Instruct   (~1 GB VRAM after 4-bit quant)
  - unsloth/Qwen2.5-3B-Instruct      (~2 GB VRAM after 4-bit quant)
  - unsloth/SmolLM2-1.7B-Instruct   (~1 GB VRAM after 4-bit quant)

Usage
-----
  # From the repo root with the project venv active:
  python finetune/train.py

  # To change the base model:
  python finetune/train.py --base-model unsloth/Qwen2.5-3B-Instruct

  # CPU-only debug run (very small dataset, 1 epoch):
  python finetune/train.py --cpu-debug
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration — edit these defaults to suit your hardware
# ---------------------------------------------------------------------------
DEFAULT_BASE_MODEL = "unsloth/Qwen2.5-1.5B-Instruct"
DEFAULT_DATASET = Path("finetune/dataset.jsonl")
DEFAULT_OUTPUT_DIR = Path("finetune/output/")
DEFAULT_EPOCHS = 3
DEFAULT_BATCH_SIZE = 4
DEFAULT_GRAD_ACCUM = 4
DEFAULT_MAX_SEQ_LEN = 2048
DEFAULT_LORA_R = 16
DEFAULT_LORA_ALPHA = 16
DEFAULT_LEARNING_RATE = 2e-4
GGUF_QUANTIZATION = "q4_k_m"         # good balance of quality vs. size


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def format_sample(record: dict, tokenizer) -> str:
    """Format one JSONL record into the chat template the base model expects."""
    # We treat each record as a single-turn conversation:
    #   user  → the rendered caibinet prompt
    #   model → the JSON completion
    messages = [
        {"role": "user", "content": record["prompt"]},
        {"role": "assistant", "content": record["completion"]},
    ]
    return tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=False,
    )


# ---------------------------------------------------------------------------
# Main training routine
# ---------------------------------------------------------------------------

def train(args: argparse.Namespace) -> None:
    # ----- Lazy imports so the module is importable on machines w/o GPU ----
    try:
        from unsloth import FastLanguageModel  # type: ignore
    except ImportError:
        print(
            "Unsloth is not installed.\n"
            "Run:  pip install 'unsloth[cu124-torch250] @ "
            "git+https://github.com/unslothai/unsloth.git'"
        )
        raise

    from trl import SFTTrainer, SFTConfig  # type: ignore
    from datasets import Dataset  # type: ignore

    # ------------------------------------------------------------------
    # 1. Load base model in 4-bit
    # ------------------------------------------------------------------
    print(f"\n=== Loading base model: {args.base_model} ===\n")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base_model,
        max_seq_length=args.max_seq_len,
        dtype=None,             # auto-detect float16 / bfloat16
        load_in_4bit=not args.cpu_debug,
    )

    # ------------------------------------------------------------------
    # 2. Attach LoRA adapters
    # ------------------------------------------------------------------
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_dropout=0.0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    # ------------------------------------------------------------------
    # 3. Build dataset
    # ------------------------------------------------------------------
    print(f"\n=== Loading dataset from {args.dataset} ===\n")
    records = load_jsonl(args.dataset)

    if args.cpu_debug:
        print("CPU debug mode: using only first 8 records, 1 epoch.")
        records = records[:8]
        args.epochs = 1

    texts = [format_sample(r, tokenizer) for r in records]

    # 90/10 split
    split = max(1, int(len(texts) * 0.9))
    train_texts, eval_texts = texts[:split], texts[split:]
    train_ds = Dataset.from_dict({"text": train_texts})
    eval_ds = Dataset.from_dict({"text": eval_texts})

    print(f"Train examples: {len(train_ds)},  Eval examples: {len(eval_ds)}")

    # ------------------------------------------------------------------
    # 4. Train
    # ------------------------------------------------------------------
    output_dir = str(args.output_dir)
    sft_config = SFTConfig(
        output_dir=output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        warmup_ratio=0.05,
        learning_rate=args.lr,
        weight_decay=0.01,
        lr_scheduler_type="cosine",
        fp16=not args.cpu_debug,
        bf16=False,
        logging_steps=1,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        save_total_limit=2,
        dataset_text_field="text",
        max_seq_length=args.max_seq_len,
        packing=False,
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        args=sft_config,
    )

    print("\n=== Starting training ===\n")
    trainer.train()

    # ------------------------------------------------------------------
    # 5. Save LoRA adapter
    # ------------------------------------------------------------------
    adapter_dir = args.output_dir / "lora_adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    print(f"\nLoRA adapter saved to {adapter_dir}")

    # ------------------------------------------------------------------
    # 6. Export quantized GGUF
    # ------------------------------------------------------------------
    if not args.skip_gguf:
        gguf_path = args.output_dir / f"caibinet-{GGUF_QUANTIZATION}.gguf"
        print(f"\n=== Exporting GGUF ({GGUF_QUANTIZATION}) to {gguf_path} ===\n")
        model.save_pretrained_gguf(
            str(args.output_dir),
            tokenizer,
            quantization_method=GGUF_QUANTIZATION,
        )
        # Unsloth writes <output_dir>/model-<quant>.gguf; rename to our target
        candidates = sorted(args.output_dir.glob("*.gguf"))
        if candidates:
            latest = candidates[-1]
            if latest != gguf_path:
                latest.rename(gguf_path)
        print(f"GGUF written to {gguf_path}")
        print(
            f"\nNext step — register with Ollama:\n"
            f"  ollama create caibinet -f finetune/Modelfile"
        )
    else:
        print("Skipped GGUF export (--skip-gguf flag set).")

    print("\n=== Training complete ===\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune caibinet file classifier")
    parser.add_argument("--base-model", default=DEFAULT_BASE_MODEL)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--grad-accum", type=int, default=DEFAULT_GRAD_ACCUM)
    parser.add_argument("--max-seq-len", type=int, default=DEFAULT_MAX_SEQ_LEN)
    parser.add_argument("--lora-r", type=int, default=DEFAULT_LORA_R)
    parser.add_argument("--lora-alpha", type=int, default=DEFAULT_LORA_ALPHA)
    parser.add_argument("--lr", type=float, default=DEFAULT_LEARNING_RATE)
    parser.add_argument(
        "--skip-gguf",
        action="store_true",
        help="Skip GGUF export (useful if you only want the LoRA adapter)",
    )
    parser.add_argument(
        "--cpu-debug",
        action="store_true",
        help="Run a tiny 8-sample test on CPU (no GPU required, very slow)",
    )
    args = parser.parse_args()

    train(args)


if __name__ == "__main__":
    main()
