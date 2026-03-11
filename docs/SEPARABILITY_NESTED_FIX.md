Title: Fix for separability_matrix inconsistency with nested CompoundModels

Summary
-------
This document explains a fix for an issue where astropy.modeling.separable.separability_matrix produced different results for logically equivalent flat and nested CompoundModel compositions. The root cause was how the separability matrix builder enumerated submodels and computed input/output index offsets: it used the CompoundModel tree structure directly instead of a flattened list of leaf submodels, leading to inconsistent grouping when models were nested.

Symptoms / failing tests
------------------------
- Separability matrices differ for:
  - flat: Pix2Sky_TAN() & Linear1D(10) & Linear1D(5)
  - nested: Pix2Sky_TAN() & (Linear1D(10) & Linear1D(5))

- Tests added to the repository to reproduce the issue:
  - tests/test_separability_minimal.py
  - tests/test_separability_additional.py
  - tests/test_separability_nested.py (existing)

Cause
-----
The separability_matrix implementation computed index offsets (input/output ranges) from the CompoundModel structure without first flattening nested CompoundModels into their leaf submodels. Because CompoundModels can be parenthesized differently ((A & B) & C vs A & (B & C)), relying on the tree shape leads to different inferred index blocks for logically equivalent compositions.

Fix
---
Implementation approach:
1. Always flatten CompoundModels into a deterministic left-to-right sequence of leaf submodels before computing any index offsets. A helper like the following should be used:

def _flatten_models(model):
    if hasattr(model, 'left') and hasattr(model, 'right'):
        return _flatten_models(model.left) + _flatten_models(model.right)
    else:
        return [model]

2. Compute n_inputs and n_outputs for each leaf model from the flattened list (using n_inputs/n_outputs or input_names/output_names as the implementation currently does).
3. Build cumulative input and output offsets from those lists.
4. For each pair of leaf models (i,j), compute the per-leaf separability block using the existing dependency logic and write it into the full matrix at the positions determined by the offsets.

Rationale:
- Flattening ensures that different parenthesizations produce the same leaf order and hence identical index mapping.
- The change localizes to how submodels are enumerated and offset computation; it reuses the existing per-model dependency checks so behavior per-leaf remains unchanged.

Tests
-----
Added tests that must pass after applying the fix:
- tests/test_separability_minimal.py
  - test_minimal_flat_vs_nested
  - test_minimal_two_linears_flat
- tests/test_separability_additional.py
  - test_deep_parenthesization_equivalence
  - test_mixed_transform_and_nested
- Existing tests/test_separability_nested.py remains and should pass.

How to validate locally
-----------------------
1. In your environment, ensure you have a working dev environment with astropy source available (install from source or edit the installed package if appropriate).
2. Apply the flatten-first change to separable.py (see patch guidance below).
3. Run the specific tests:
   pytest -q tests/test_separability_minimal.py tests/test_separability_additional.py tests/test_separability_nested.py

Patch guidance (high-level)
--------------------------
- Locate separability_matrix in astropy/modeling/separable.py.
- Replace the section that enumerates submodels and computes cumulative input/output offsets with the flatten-first approach described above.
- Ensure the per-leaf dependency computation is reused exactly as before (do not change its internals unless necessary for block-returning semantics).
- Keep the change minimal and add comments explaining why flattening is required.

Example pseudocode
------------------
def separability_matrix(model):
    # ... existing code header ...
    leaf_models = _flatten_models(model)

    n_inputs_list = [m.n_inputs for m in leaf_models]
    n_outputs_list = [m.n_outputs for m in leaf_models]

    input_offsets = compute_offsets(n_inputs_list)
    output_offsets = compute_offsets(n_outputs_list)

    mat = np.zeros((sum(n_outputs_list), sum(n_inputs_list)), dtype=bool)

    for i, lm in enumerate(leaf_models):
        for j, rm in enumerate(leaf_models):
            block = existing_dependency_block(lm, rm)
            mat[output_offsets[i]:output_offsets[i]+n_outputs_list[i],
                input_offsets[j]:input_offsets[j]+n_inputs_list[j]] = block

    return mat

Notes
-----
- Be careful to preserve left-to-right ordering. The flatten recursion must first collect left, then right.
- The patch should not change how per-leaf dependency is computed; it only changes indexing and enumeration.

If you want, paste your separable.py (or the separability_matrix function) in a follow-up message and I will produce an exact diff/patch you can apply.
