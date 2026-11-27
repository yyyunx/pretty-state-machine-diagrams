"""Generate UML state machine diagrams from an SMD Model or a converter adapter."""

from .pipeline import GenerationResult, InputError, generate, load_json, prepare_model
from src.layout.engine import LayoutOptions
from src.model import ConverterAdapter, MockConverterAdapter

__version__ = "0.1.0"

__all__ = [
    "ConverterAdapter", "GenerationResult", "InputError", "LayoutOptions",
    "MockConverterAdapter", "generate", "load_json", "prepare_model",
]
