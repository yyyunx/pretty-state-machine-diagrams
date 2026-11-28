"""Generate UML state machine diagrams from an SMD Model or a converter adapter."""

from .pipeline import GenerationResult, InputError, generate, load_json, prepare_model
from src.layout.advanced import OptimizationResult, optimize
from src.layout.budget import BudgetExceeded
from src.layout.hybrid import analyze_graph, optimize_hybrid
from src.layout.engine import LayoutOptions
from src.model import ConverterAdapter, MockConverterAdapter

__version__ = "0.3.0"

__all__ = [
    "ConverterAdapter", "GenerationResult", "InputError", "LayoutOptions",
    "MockConverterAdapter", "generate", "load_json", "prepare_model",
    "BudgetExceeded", "OptimizationResult", "optimize",
    "analyze_graph", "optimize_hybrid",
]
