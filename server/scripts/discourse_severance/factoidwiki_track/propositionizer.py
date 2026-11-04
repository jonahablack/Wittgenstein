"""Shared helpers for loading Chen et al.'s Propositionizer checkpoint and
running it on source paragraphs.

Used by Task 3 (resolve_prompt_format.py) and Task 4
(measure_throughput.py). Task 5's classifier (relation_classifier.py) is
a separate, independent GPT-4o-mini zero-shot classifier and never
touches this module or this model.

MODEL: chentong00/propositionizer-wiki-flan-t5-large (confirmed by a
prior research pass, per this pilot's task spec: public, ungated,
Apache-2.0, ~3.1GB safetensors, a FLAN-T5-large fine-tune, 783M params,
T5ForConditionalGeneration). First call to load_model_and_tokenizer()
triggers the real download via transformers' HF-hub caching
(~/.cache/huggingface by default); later calls load from that cache.

KNOWN GOTCHA (confirmed by prior research pass, load-bearing for every
call site here): generation_config.json does NOT set max_new_tokens, so
output silently truncates unless the caller passes max_new_tokens=512
explicitly to generate(). Enforced here as a required arg with no
default (fail loud, not silent), per this project's conventions.

No CUDA on this project's hardware (Apple Silicon, CPU + possibly MPS).
Device is always an explicit caller-supplied string ("cpu" or "mps"),
never auto-detected/defaulted here, so a script's device choice is
always visible in its own output/logs.
"""

import json
import time

MODEL_NAME = "chentong00/propositionizer-wiki-flan-t5-large"


def load_model_and_tokenizer(device):
    """Loads tokenizer + model and moves the model to `device`. Returns
    (model, tokenizer). Raises whatever transformers/huggingface_hub
    raises on a real failure (no network, bad repo id, etc.) -- no
    fallback to a smaller/mock model.
    """
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    print(f"[propositionizer] loading tokenizer for {MODEL_NAME} ...", flush=True)
    t0 = time.time()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    print(f"[propositionizer]   tokenizer ready in {time.time() - t0:.1f}s", flush=True)

    print(f"[propositionizer] loading model {MODEL_NAME} "
          f"(first run downloads ~3.1GB; cached under ~/.cache/huggingface after) ...",
          flush=True)
    t0 = time.time()
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
    model.to(device)
    model.eval()
    print(f"[propositionizer]   model ready in {time.time() - t0:.1f}s on device={device!r}",
          flush=True)
    return model, tokenizer


def move_model_to_device(model, device):
    """Moves an already-loaded model to a different device in place
    (cheap relative to a fresh from_pretrained load) -- used by Task 4 to
    compare CPU vs MPS without downloading/loading the checkpoint twice.
    """
    t0 = time.time()
    model.to(device)
    print(f"[propositionizer] moved model to device={device!r} in {time.time() - t0:.2f}s",
          flush=True)
    return model


def build_prompt(title, section, content, with_content_label):
    """Builds one of the two candidate inference prompts from clean
    (title, section, content) fields (see download_data.py's
    _split_sources). `with_content_label=True` is the MODEL README's
    documented format; False is the dataset card's PROSE-documented
    format (which, per Task 3's empirical finding, does not match the
    dataset's own actual data -- see README.md).
    """
    if with_content_label:
        return f"Title: {title}. Section: {section}. Content: {content}"
    return f"Title: {title}. Section: {section}. {content}"


def generate_propositions(model, tokenizer, prompt_text, device, max_new_tokens):
    """Runs ONE generate() call for `prompt_text` on `device`.

    Returns a dict:
      decoded: str, the raw decoded generation (skip_special_tokens=True)
      parsed: list[str] or None (None if decode didn't parse as a JSON list)
      parse_error: str or None, set iff parsed is None
      elapsed_seconds: float, wall-clock time for tokenize+generate+decode
        (generate() dominates; tokenize/decode are ~microseconds by
        comparison, but timing wraps all three since that is the real
        per-paragraph cost a full-scale run would pay)

    max_new_tokens has NO default and must be truthy: silently defaulting
    it here would be exactly the documented gotcha (generation_config.json
    has no max_new_tokens set) this module exists to guard against.
    """
    if not max_new_tokens:
        raise ValueError(
            "FATAL: max_new_tokens must be passed explicitly and be truthy "
            "(documented gotcha: generation_config.json sets no "
            "max_new_tokens, so output silently truncates otherwise)."
        )

    t0 = time.time()
    inputs = tokenizer(prompt_text, return_tensors="pt", truncation=True, max_length=1024)
    inputs = {k: v.to(device) for k, v in inputs.items()}

    import torch
    with torch.no_grad():
        output_ids = model.generate(**inputs, max_new_tokens=max_new_tokens)
    decoded = tokenizer.decode(output_ids[0], skip_special_tokens=True)
    elapsed = time.time() - t0

    parsed, parse_error = None, None
    try:
        candidate = json.loads(decoded)
        if isinstance(candidate, list) and all(isinstance(x, str) for x in candidate):
            parsed = candidate
        else:
            parse_error = f"parsed_but_not_a_list_of_str:{type(candidate).__name__}"
    except json.JSONDecodeError as e:
        parse_error = f"json_decode_error:{e}"

    return {
        "decoded": decoded,
        "parsed": parsed,
        "parse_error": parse_error,
        "elapsed_seconds": elapsed,
    }


if __name__ == "__main__":
    # Standalone trigger: `venv/bin/python propositionizer.py` just loads
    # the model+tokenizer (forcing the ~3.1GB download if not cached yet)
    # and runs one throwaway generation, so the download can be kicked
    # off/verified independently of Task 3/4's scripts.
    model, tokenizer = load_model_and_tokenizer("cpu")
    result = generate_propositions(
        model, tokenizer,
        "Title: Test. Section: Test. Content: The sky is blue. Water is wet.",
        device="cpu", max_new_tokens=512,
    )
    print("\nSanity-check generation:")
    print("  decoded:", result["decoded"])
    print("  parsed:", result["parsed"])
    print("  parse_error:", result["parse_error"])
    print(f"  elapsed: {result['elapsed_seconds']:.2f}s")
