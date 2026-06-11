import pytest

from mpcontribs_api.exceptions import (
    AppError,
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionError,
    ValidationError,
    _error_body,
)


class TestErrorBody:
    def test_minimal_body(self):
        body = _error_body("not_found", "Resource not found")
        assert body == {"error": {"code": "not_found", "message": "Resource not found"}}

    def test_body_with_context(self):
        body = _error_body("not_found", "Resource not found", resource_id="abc", resource_type="project")
        assert body["error"]["code"] == "not_found"
        assert body["error"]["message"] == "Resource not found"
        assert body["error"]["detail"] == {"resource_id": "abc", "resource_type": "project"}

    def test_no_detail_key_without_context(self):
        body = _error_body("conflict", "Duplicate id")
        assert "detail" not in body["error"]

    def test_detail_present_with_context(self):
        body = _error_body("conflict", "Duplicate id", existing_id="xyz")
        assert "detail" in body["error"]


class TestAppError:
    def test_default_status_and_code(self):
        err = AppError()
        assert err.status_code == 500
        assert err.error_code == "internal_error"

    def test_default_message_is_class_name(self):
        err = AppError()
        assert err.message == "AppError"

    def test_custom_message(self):
        err = AppError("something went wrong")
        assert err.message == "something went wrong"

    def test_context_stored(self):
        err = AppError("msg", user="alice", action="delete")
        assert err.context == {"user": "alice", "action": "delete"}

    def test_is_exception(self):
        err = AppError("oops")
        assert isinstance(err, Exception)

    def test_str_is_message(self):
        err = AppError("oops")
        assert str(err) == "oops"


class TestNotFoundError:
    def test_status_code(self):
        assert NotFoundError.status_code == 404

    def test_error_code(self):
        assert NotFoundError.error_code == "not_found"

    def test_message_defaults_to_class_name(self):
        err = NotFoundError()
        assert err.message == "NotFoundError"

    def test_custom_message(self):
        err = NotFoundError("project 'foo' not found")
        assert err.message == "project 'foo' not found"

    def test_is_app_error(self):
        assert issubclass(NotFoundError, AppError)


class TestConflictError:
    def test_status_code(self):
        assert ConflictError.status_code == 409

    def test_error_code(self):
        assert ConflictError.error_code == "conflict"

    def test_is_app_error(self):
        assert issubclass(ConflictError, AppError)


class TestValidationError:
    def test_status_code(self):
        assert ValidationError.status_code == 422

    def test_error_code(self):
        assert ValidationError.error_code == "validation_error"

    def test_is_app_error(self):
        assert issubclass(ValidationError, AppError)


class TestPermissionError:
    def test_status_code(self):
        assert PermissionError.status_code == 403

    def test_error_code(self):
        assert PermissionError.error_code == "permission_denied"

    def test_context_kwargs(self):
        err = PermissionError(required_role="admin")
        assert err.context == {"required_role": "admin"}

    def test_is_app_error(self):
        assert issubclass(PermissionError, AppError)


class TestAuthenticationError:
    def test_status_code(self):
        assert AuthenticationError.status_code == 401

    def test_error_code(self):
        assert AuthenticationError.error_code == "authentication_error"

    def test_is_app_error(self):
        assert issubclass(AuthenticationError, AppError)


class TestExceptionRaising:
    def test_not_found_can_be_raised_and_caught(self):
        with pytest.raises(NotFoundError) as exc_info:
            raise NotFoundError("project not found")
        assert exc_info.value.message == "project not found"
        assert exc_info.value.status_code == 404

    def test_app_error_catches_subclasses(self):
        with pytest.raises(AppError):
            raise ConflictError("duplicate")

    def test_context_available_after_raise(self):
        with pytest.raises(ValidationError) as exc_info:
            raise ValidationError("bad field", field="email", value="oops")
        assert exc_info.value.context == {"field": "email", "value": "oops"}
