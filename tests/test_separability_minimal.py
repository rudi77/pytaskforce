import numpy as np
from astropy.modeling import models as m
from astropy.modeling.separable import separability_matrix


def test_minimal_flat_vs_nested():
    a = m.Linear1D(10)
    b = m.Linear1D(5)
    # flat composition
    flat = m.Pix2Sky_TAN() & a & b
    # nested composition
    nested = m.Pix2Sky_TAN() & (a & b)

    mat_flat = separability_matrix(flat)
    mat_nested = separability_matrix(nested)

    assert mat_flat.shape == mat_nested.shape
    assert np.array_equal(mat_flat, mat_nested), (
        "Separability matrix differs for flat vs nested composition.\n"
        f"Flat:\n{mat_flat}\n\nNested:\n{mat_nested}"
    )


def test_minimal_two_linears_flat():
    flat = m.Linear1D(10) & m.Linear1D(5)
    mat = separability_matrix(flat)
    expected = np.array([[ True, False], [False, True]])
    assert mat.shape == (2, 2)
    assert np.array_equal(mat, expected)
