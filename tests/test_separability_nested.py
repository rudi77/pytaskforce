import numpy as np
import pytest
from astropy.modeling import models as m
from astropy.modeling.separable import separability_matrix


def test_flat_two_linears():
    # Flat composition of two Linear1D models
    flat = m.Linear1D(10) & m.Linear1D(5)
    mat_flat = separability_matrix(flat)

    # Explicit expectation: two independent blocks (diagonal)
    expected = np.array([[ True, False],
                         [False,  True]])
    assert mat_flat.shape == (2, 2)
    assert np.array_equal(mat_flat, expected), f"Unexpected separability for flat two-linears:\n{mat_flat}"


def test_flat_vs_nested_with_pix2sky():
    # Flat composition: Pix2Sky_TAN & Linear1D & Linear1D
    flat = m.Pix2Sky_TAN() & m.Linear1D(10) & m.Linear1D(5)
    mat_flat = separability_matrix(flat)

    # Nested composition: Pix2Sky_TAN & (Linear1D & Linear1D)
    nested = m.Pix2Sky_TAN() & (m.Linear1D(10) & m.Linear1D(5))
    mat_nested = separability_matrix(nested)

    # These must be identical regardless of nesting
    assert mat_flat.shape == mat_nested.shape, "Shape mismatch between flat and nested models"
    assert np.array_equal(mat_flat, mat_nested), (
        "Separability matrices differ for flat vs nested composition.\n"
        f"Flat:\n{mat_flat}\n\nNested:\n{mat_nested}"
    )


def test_deeply_nested_equivalence():
    # Construct deeper nesting to ensure recursion/flattening is correct
    a = m.Linear1D(1)
    b = m.Linear1D(2)
    c = m.Linear1D(3)
    # nested1: ((a & b) & c)
    nested1 = (a & b) & c
    # nested2: (a & (b & c))
    nested2 = a & (b & c)
    mat1 = separability_matrix(nested1)
    mat2 = separability_matrix(nested2)
    assert mat1.shape == mat2.shape
    assert np.array_equal(mat1, mat2), (
        "Separability differs for different parenthesization of same composition.\n"
        f"((a & b) & c):\n{mat1}\n\n(a & (b & c)):\n{mat2}"
    )
