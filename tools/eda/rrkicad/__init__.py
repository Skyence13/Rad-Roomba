"""rrkicad - scripted, headless KiCad 9 flow for the Rad Roomba boards.

Board definitions import the API from here::

    from rrkicad import Board, Pad, SymPin, Rules
"""
from .model import Board, Group, Part, Rules, Pad, SymPin, DefinitionError  # noqa: F401

__version__ = "0.1.0"
