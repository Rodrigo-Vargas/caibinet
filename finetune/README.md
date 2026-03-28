# Fine-tuning a dedicated file-classifier for caibinet

This guide walks you through creating a custom small LLM that is laser-focused
on the caibinet file-classification task.  The fine-tuned model replaces the
generic Ollama model in caibinet's Settings and should produce consistent,
valid JSON every time.

---

## Why fine-tune?

| Approach | Pros | Cons |
|---|---|---|
| Generic small model (2-3 B) | Already installed | Drifts off JSON, needs complex prompting |
| Generic large model (7 B+) | Great accuracy | Too slow on CPU / consumer GPU |
| **Fine-tuned small model** | Fast + consistent JSON | Requires one-time training run |

---

## Hardware requirements

| Situation | Requirement |
|---|---|
| Training (GPU, recommended) | 6 GB+ VRAM (RTX 3060 or better; 4-bit quant) |
| Training (CPU only) | Possible but takes hours — use `--cpu-debug` to validate setup |
| Inference after training | Same as current Ollama usage (<2 GB RAM) |

---

## Step 1 — Set up the Python environment

```bash
# From the caibinet repo root
cd /path/to/caibinet

# Install Unsloth (CUDA 12.4, PyTorch 2.5 — adjust if different)
pip install "unsloth[cu124-torch250] @ git+https://github.com/unslothai/unsloth.git"

# Install TRL and HuggingFace datasets
pip install trl datasets

# Optional – only needed if you want to use a cloud model as teacher labeler
pip install openai
```

> **CPU-only machines**: Replace the Unsloth install with:
> ```bash
> pip install unsloth
> ```
> Training will succeed but will take hours for even a small dataset.  Use
> `python finetune/train.py --cpu-debug` to verify the setup before committing.

---

## Step 2 — Generate the training dataset

The training data is `(prompt, JSON completion)` pairs.  Two modes are
available:

### 2a. Manual labels (fast, no API needed — recommended to start)

Hardcoded ground-truth labels for the ~40 fixture files ship in the script:

```bash
python finetune/generate_dataset.py --mode manual --out finetune/dataset.jsonl
```

This produces `finetune/dataset.jsonl` (~40 examples).

### 2b. LLM-teacher labels (scales to many files, uses an API)

This mode sends each file through `render_prompt()` and asks a cloud model
(default `gpt-4o-mini`) to label it.  It lets you label your own real files
to complement the fixtures:

```bash
export OPENAI_API_KEY=sk-...
python finetune/generate_dataset.py \
    --mode llm \
    --fixtures /path/to/your/real/files \
    --out finetune/dataset.jsonl
```

### Combining both

Run manual first, then append LLM-labeled real files:

```bash
python finetune/generate_dataset.py --mode manual --out finetune/dataset.jsonl
python finetune/generate_dataset.py --mode llm \
    --fixtures ~/Documents \
    --out finetune/real_data.jsonl
cat finetune/real_data.jsonl >> finetune/dataset.jsonl
```

> The more diverse your dataset (different file types, sizes, names), the
> better the model generalizes.  Aim for at least 200 examples.

---

## Step 3 — Train

```bash
python finetune/train.py
```

Default settings (edit the constants at the top of `train.py` to change):

| Setting | Default | Notes |
|---|---|---|
| Base model | `unsloth/Qwen2.5-1.5B-Instruct` | ~1 GB VRAM |
| LoRA rank | 16 | Higher = more capacity, more VRAM |
| Epochs | 3 | Increase to 5 if eval loss is still falling |
| Batch size | 4 | Reduce to 2 if OOM |

Alternative base models:

```bash
# 3B model — better quality, needs ~2 GB VRAM
python finetune/train.py --base-model unsloth/Qwen2.5-3B-Instruct

# Alternative architecture
python finetune/train.py --base-model unsloth/SmolLM2-1.7B-Instruct
```

### What the script produces

```
finetune/output/
├── lora_adapter/          ← HuggingFace LoRA checkpoint
│   ├── adapter_config.json
│   ├── adapter_model.safetensors
│   └── ...
└── caibinet-q4_k_m.gguf   ← quantized model ready for Ollama
```

---

## Step 4 — Register the model with Ollama

```bash
# Run from the repo root so the relative path in the Modelfile resolves
ollama create caibinet -f finetune/Modelfile
```

Verify it works:

```bash
ollama run caibinet "Classify this file: invoice_2024_q3.pdf (PDF, 45 KB)"
```

You should receive a clean JSON object immediately, with no preamble.

---

## Step 5 — Update caibinet to use the new model

1. Open caibinet → **Settings**.
2. Change the **Model** field from `qwen3.5:2b` to `caibinet`.
3. Click **Save**.

Alternatively, edit `~/.config/caibinet/config.json` (or the path shown in
Settings) and set `"model": "caibinet"`.

---

## Tips for improving accuracy

### Quick win — add Ollama structured output (no training needed)

Even before fine-tuning, you can eliminate most JSON parse errors by telling
Ollama to enforce a JSON schema.  Edit `core/ai/ollama.py`:

```python
# In generate(), add a format field to the request body:
payload = {
    "model": self.model,
    "prompt": prompt,
    "stream": False,
    "format": {
        "type": "object",
        "properties": {
            "filename":   {"type": "string"},
            "category":   {"type": "string", "enum": ["Finance","Work","Personal","Media","Code","Other"]},
            "path":       {"type": "string"},
            "confidence": {"type": "number"},
            "reasoning":  {"type": "string"}
        },
        "required": ["filename","category","path","confidence","reasoning"]
    }
}
```

This works with any Ollama model ≥ 0.4.0.

### Expand your dataset

- Point `--fixtures` at your actual `~/Documents`, `~/Downloads`, or any folder
  with real files.
- Aim for 50+ examples per category.

### Evaluate before deploying

Check the eval loss shown during training.  If it is not decreasing, increase
`--epochs`.  If it diverges, reduce `--lr` to `1e-4`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `CUDA out of memory` | Add `--batch-size 2 --grad-accum 8` |
| `unsloth` not found | Re-run the pip install command from Step 1 |
| GGUF file not created | Check that `llama-cpp-python` or the Unsloth GGUF exporter installed; see Unsloth docs |
| `ollama create` fails | Ensure the GGUF path in `Modelfile` is correct relative to where you run the command |
| Model still returns non-JSON | Add the structured output fix from the "Tips" section above |
