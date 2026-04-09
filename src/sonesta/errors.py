from __future__ import annotations


class SonestaError(Exception):
    code = "sonesta_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UsageError(SonestaError):
    code = "usage_error"


class IoError(SonestaError):
    code = "io_error"


class SchemaError(SonestaError):
    code = "schema_error"


class ValidationError(SonestaError):
    code = "validation_error"


class RenderError(SonestaError):
    code = "render_error"
