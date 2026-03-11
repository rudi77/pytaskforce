"""Debug: check what metadata is available in SWE-bench samples."""
from inspect_evals.swe_bench import swe_bench as _swe_bench

task = _swe_bench(dataset="princeton-nlp/SWE-bench_Verified", split="test[:1]")
sample = task.dataset[0]
print("metadata keys:", list(sample.metadata.keys()) if sample.metadata else "None")
ftp = sample.metadata.get("FAIL_TO_PASS", "MISSING") if sample.metadata else "NO_META"
print(f"FAIL_TO_PASS type: {type(ftp).__name__}")
print(f"FAIL_TO_PASS value: {str(ftp)[:300]}")
