from ipforge_client.exceptions import (
    IPForgeError, APIError, AuthError, ValidationError, ServerError,
)


def test_api_error_carries_status_and_detail():
    e = ValidationError(status=422, detail={"msg": "bad"})
    assert e.status == 422
    assert e.detail == {"msg": "bad"}
    assert "422" in str(e)


def test_subclass_hierarchy():
    assert issubclass(AuthError, APIError)
    assert issubclass(APIError, IPForgeError)
    assert issubclass(ServerError, APIError)
