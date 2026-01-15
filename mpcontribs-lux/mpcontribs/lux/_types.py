"""Define a few custom types for use in schemas."""

from typing import Annotated

from pydantic import BeforeValidator

_complex_type_validator = BeforeValidator(
    lambda x: (x.real, x.imag) if isinstance(x, complex) else x
)

ComplexType = Annotated[tuple[float, float], _complex_type_validator]
"""Type annotation for complex numbers which are required fields."""

NullableComplexType = Annotated[tuple[float, float] | None, _complex_type_validator]
"""Type annotation for complex numbers which are nullable fields."""