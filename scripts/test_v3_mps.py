"""
DictaLM 3.0 Nemotron-12B via PyTorch MPS (Apple Silicon, no MLX).
Downloads model from HuggingFace, runs same test cases as v2 eval.

Usage:
    uv run --extra local python scripts/test_v3_mps.py
    uv run --extra local python scripts/test_v3_mps.py --model-path /path/to/local  # skip download

Results written to scripts/test_v3_mps_results.json
"""

import argparse
import json
import time
from pathlib import Path

HF_MODEL = "dicta-il/DictaLM-3.0-Nemotron-12B-Instruct"
RESULTS_FILE = Path(__file__).parent / "test_v3_mps_results.json"

# Same test cases used in the bot + the bad examples from the user
TEST_CASES = [
    "good morning",
    "thank you very much",
    "I want water",
    "many people sitting in a scary room",
    "and nearby",
    "why did he start speaking in capital letters in English",
    "where is the bathroom",
    "I love you",
    "excuse me, do you speak Russian",
    "the meeting is tomorrow at ten",
    "I am learning Hebrew",
    "what time is it",
    "please help me",
    "beautiful city",
    "how are you",
]

SYSTEM_PROMPT = (
    'You are a Hebrew translator. For each input, output JSON: {"he":"<Hebrew text>","pron":"<reading guide>"}\n'
    'pron rule: ONE syllable per word in UPPERCASE = stressed. All other letters lowercase. No apostrophes ever.\n'
    'sh=ש kh=כ/ח ts=צ v=ו/ב(v) b=ב(b) k=ק/כ y=י s=ס t=ת h=ה. Stress usually on LAST syllable.\n'
    '\n'
    'Input: good morning\n'
    'Output: {"he":"בוקר טוב","pron":"BOker TOV"}\n'
    '\n'
    'Input: thank you very much\n'
    'Output: {"he":"תודה רבה מאוד","pron":"toDA raBA meOD"}\n'
    '\n'
    'Input: many people sitting in a scary room\n'
    'Output: {"he":"הרבה אנשים יושבים בחדר מפחיד","pron":"harBE anaSHIM yoshVIM bakhaDAR mafHID"}\n'
    '\n'
    'Input: and nearby\n'
    'Output: {"he":"ובסמוך","pron":"vesamUKH"}\n'
    '\n'
    'Input: why did he start speaking in capital letters in English\n'
    'Output: {"he":"למה הוא התחיל לדבר באותיות גדולות באנגלית","pron":"laMA hu hitKHIL ledaBER beotiyOT gdoLOT beangLIT"}\n'
)


def build_messages(text: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Input: {text}\nOutput:"},
    ]


def run_test(model, tokenizer, device: str, text: str) -> dict:
    import torch

    messages = build_messages(text)
    inputs = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=False,  # already have "Output:" in user turn
        return_tensors="pt",
    ).to(device)

    t0 = time.perf_counter()
    with torch.no_grad():
        out = model.generate(
            inputs,
            max_new_tokens=80,
            do_sample=False,
            temperature=1.0,
            pad_token_id=tokenizer.eos_token_id,
        )
    elapsed = time.perf_counter() - t0

    new_tokens = out[0][inputs.shape[1]:]
    n_tokens = len(new_tokens)
    raw = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

    try:
        # strip trailing noise after closing brace
        brace = raw.rfind("}")
        clean = raw[: brace + 1] if brace != -1 else raw
        data = json.loads(clean)
        valid = True
    except json.JSONDecodeError:
        data = {}
        valid = False

    return {
        "input": text,
        "raw": raw,
        "he": data.get("he", ""),
        "pron": data.get("pron", ""),
        "valid_json": valid,
        "tokens": n_tokens,
        "seconds": round(elapsed, 2),
        "tok_per_sec": round(n_tokens / elapsed, 1) if elapsed > 0 else 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", default=HF_MODEL,
                        help="HF repo ID or local path (default: %(default)s)")
    parser.add_argument("--device", default="mps", choices=["mps", "cpu"],
                        help="PyTorch device (default: mps)")
    parser.add_argument("--n", type=int, default=len(TEST_CASES),
                        help="Number of test cases to run")
    args = parser.parse_args()

    print(f"Loading {args.model_path} on {args.device} ...")
    print("This may download ~24GB on first run. Progress shown by HuggingFace.")

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    t_load = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        torch_dtype=torch.float16,
        device_map=args.device,
        trust_remote_code=True,
    )
    model.eval()
    load_time = time.perf_counter() - t_load
    print(f"Model loaded in {load_time:.1f}s\n")

    results = []
    cases = TEST_CASES[: args.n]
    for i, text in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {text!r}")
        r = run_test(model, tokenizer, args.device, text)
        results.append(r)
        status = "OK" if r["valid_json"] else "INVALID"
        print(f"  he:   {r['he']}")
        print(f"  pron: {r['pron']}")
        print(f"  {r['tok_per_sec']} tok/s  {r['seconds']}s  [{status}]")
        if not r["valid_json"]:
            print(f"  raw:  {r['raw']!r}")
        print()

    valid = sum(1 for r in results if r["valid_json"])
    avg_speed = sum(r["tok_per_sec"] for r in results) / len(results) if results else 0
    avg_sec = sum(r["seconds"] for r in results) / len(results) if results else 0

    print(f"Summary: {valid}/{len(results)} valid JSON  |  {avg_speed:.1f} tok/s avg  |  {avg_sec:.1f}s avg")

    payload = {
        "model": args.model_path,
        "device": args.device,
        "load_seconds": round(load_time, 1),
        "results": results,
        "summary": {"valid": valid, "total": len(results), "avg_tok_per_sec": round(avg_speed, 1), "avg_seconds": round(avg_sec, 1)},
    }
    RESULTS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\nResults saved to {RESULTS_FILE}")


if __name__ == "__main__":
    main()
