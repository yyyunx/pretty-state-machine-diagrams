"""Run the prepared P0/P1 acceptance cases against the prototype."""

from src.model import MockConverterAdapter, ModelError, build_model, serialize_model, transform_model

from tests.model.experimental_acceptance import acceptance_suite


def as_test_result(operation, draft):
    try:
        return serialize_model(operation(draft)), ()
    except ModelError as error:
        return None, tuple((item.code, item.path) for item in error.diagnostics)


def load_tests(loader, tests, pattern):
    def build(draft):
        return as_test_result(build_model, draft)

    def transform(source):
        return as_test_result(lambda value: transform_model(value, MockConverterAdapter()), source)

    return acceptance_suite(build, transform)
