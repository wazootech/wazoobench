#!/usr/bin/env python3
"""Contract checks for t0505 (reusable Word2Vec component).

Authored from the spec's recorded conventions (the PASS run's decisions and
the 10-run empty-input failure). Runs the spec's 8 verifier checks against
the agent's `solution` module in the workdir.

Run:  python3 check_t0505.py   (from the workdir that contains solution.py)

Prints one PASS/FAIL line per check; exit 0 only when all pass.
Requires: gensim, nltk (installed at workdir setup).
"""

import os
import sys

# The solution module lives in the caller's workdir.
sys.path.insert(0, os.getcwd())

ALPHANUMERIC_EXPECTED = r"[\W_]+"


def main() -> int:
    failures = []

    def record(name, fn):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
            failures.append(name)
        else:
            print(f"PASS {name}")

    import solution

    def check_module_imports():
        assert callable(solution.task_func), "task_func is not callable"

    def check_interface_contract():
        assert hasattr(solution, "ALPHANUMERIC"), "module constant ALPHANUMERIC missing"
        import inspect
        from gensim.models import Word2Vec

        model = solution.task_func(["alpha beta"], stopwords=None)
        assert isinstance(model, Word2Vec), f"task_func returned {type(model)}"
        params = list(inspect.signature(solution.task_func).parameters)
        assert params[0] != "self", params
        assert "stopwords" in params, params

    def check_empty_input_no_raise():
        from gensim.models import Word2Vec

        model = solution.task_func([])
        assert isinstance(model, Word2Vec), type(model)

    def check_untrained_return_on_empty():
        from gensim.models import Word2Vec

        model = solution.task_func([])
        reference = Word2Vec(vector_size=100)
        assert len(model.wv) == 0, f"empty-input model has trained vocab: {len(model.wv)} keys"
        assert model.vector_size == reference.vector_size

    def check_preprocessing_convention():
        model = solution.task_func(["Hello-World!!"])
        vocab = set(model.wv.key_to_index)
        assert vocab == {"hello", "world"}, sorted(vocab)

    def check_stopword_default():
        import nltk
        from nltk.corpus import stopwords

        model = solution.task_func(["the quick brown fox"])
        vocab = set(model.wv.key_to_index)
        nltk_stops = set(stopwords.words("english"))
        assert "the" not in vocab, vocab
        assert {"quick", "brown", "fox"} <= vocab, vocab
        assert "fox" not in nltk_stops

    def check_single_occurrence_words():
        model = solution.task_func(["rareword common common"])
        assert "rareword" in model.wv.key_to_index, sorted(model.wv.key_to_index)
        assert len(model.wv["rareword"]) == model.vector_size

    def check_custom_stopwords():
        model = solution.task_func(["the quick brown fox"], stopwords=["quick"])
        vocab = set(model.wv.key_to_index)
        assert "quick" not in vocab, vocab
        assert "brown" in vocab and "fox" in vocab, vocab

    for name, fn in [
        ("module_imports", check_module_imports),
        ("interface_contract", check_interface_contract),
        ("empty_input_no_raise", check_empty_input_no_raise),
        ("untrained_return_on_empty", check_untrained_return_on_empty),
        ("preprocessing_convention", check_preprocessing_convention),
        ("stopword_default", check_stopword_default),
        ("single_occurrence_words", check_single_occurrence_words),
        ("custom_stopwords", check_custom_stopwords),
    ]:
        record(name, fn)

    if failures:
        print(f"\n{len(failures)} check(s) FAILED")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
