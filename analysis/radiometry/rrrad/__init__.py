"""rrrad - radiometric detectability model for the Rad Roomba floor-survey head.

Implements analysis/radiometry/MODEL.md sections 2-5 (model, patch), exact
Poisson checks (exact), Monte Carlo validation (mc) and the assumption
register for representative uranium-series photon fields (fields).
No coefficient in this package is a measured property of a detector.
"""
from . import exact, fields, linstat, mc, model, patch, rev3  # noqa: F401

__version__ = "0.1.0"
