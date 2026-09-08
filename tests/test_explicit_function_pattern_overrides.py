"""Explicit function overrides survive projection of normally hidden parameters."""

from objectstate import ObjectState
from python_introspect import parameter_exclusions, set_parameter_exclusions

from pyqt_reactive.services.function_pattern_code_document import (
    EditableFunctionPatternCallable,
    FunctionPatternCodeDocumentService,
)


def test_explicit_override_is_editable_without_exposing_other_runtime_parameters():
    def process(image, *, policy: float = 1.0, runtime_context=None):
        return image

    set_parameter_exclusions(process, ("policy", "runtime_context"))
    kwargs = {"policy": 2.0}
    editable = EditableFunctionPatternCallable.for_entry(process, kwargs)
    assert parameter_exclusions(editable) == frozenset({"runtime_context"})
    state = ObjectState(
        object_instance=editable,
        scope_id="explicit-function-override",
        exclude_params=FunctionPatternCodeDocumentService.reserved_parameter_names(editable),
        initial_values=kwargs,
    )
    assert FunctionPatternCodeDocumentService.reconstruct_kwargs_from_state(state) == kwargs
    assert EditableFunctionPatternCallable.for_entry(process, {}) is process
    assert parameter_exclusions(process) == frozenset({"policy", "runtime_context"})
