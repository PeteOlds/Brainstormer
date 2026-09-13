"""API response helpers."""

from flask import jsonify


def api_ok(data=None, message=None, status_code=200):
    """Return a successful API response."""
    response = {"success": True}
    if data is not None:
        response["data"] = data
    if message:
        response["message"] = message
    return jsonify(response), status_code


def api_error(message: str, status_code=400, errors=None, error_code=None):
    """Return an error API response."""
    response = {"success": False, "error": True, "message": message}
    if errors:
        response["details"] = errors
    if error_code:
        response["error_code"] = error_code
    return jsonify(response), status_code


def api_created(data=None, message="Created"):
    """Return a 201 Created response."""
    return api_ok(data, message, 201)


def api_accepted(data=None, message="Accepted"):
    """Return a 202 Accepted response."""
    return api_ok(data, message, 202)


def api_no_content(message=None):
    """Return a 204 No Content response."""
    return api_ok(None, message, 204)