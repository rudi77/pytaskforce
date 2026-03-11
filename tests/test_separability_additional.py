import numpy as np
from astropy.modeling import models as m
from astropy.modeling.separable import separability_matrix


def test_deep_parenthesization_equivalence():
    a = m.Linear1D(1)
    b = m.Linear1D(2)
    c = m.Linear1D(3)

    nested1 = (a & b) & c
    nested2 = a & (b & c)

    mat1 = separability_matrix(nested1)
    mat2 = separability_matrix(nested2)

    assert mat1.shape == mat2.shape
    assert np.array_equal(mat1, mat2), (
        "Separability differs for different parenthesization of same composition.\n"
        f"nested1:\n{mat1}\n\nnested2:\n{mat2}"
    )


def test_mixed_transform_and_nested():
    # Mix transform that changes dimensionality with nested leaf composition
    a = m.Pix2Sky_TAN()
    b = m.Linear1D(4)
    c = m.Linear1D(5)

    flat = a & b & c
    nested = a & (b & c)

    mat_flat = separability_matrix(flat)
    mat_nested = separability_matrix(nested)

    assert mat_flat.shape == mat_nested.shape
    assert np.array_equal(mat_flat, mat_nested), (
        "Separability differs for flat vs nested when mixing transforms.\n"
        f"flat:\n{mat_flat}\n\nnested:\n{mat_nested}"
    )
