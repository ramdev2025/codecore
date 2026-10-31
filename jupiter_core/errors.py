"""The one error type every layer here understands.

Ported from jupiter-code's lib/errors.ts. Every route/tool that surfaces an
error to a client renders it as ``{"detail": "<message>"}`` with the given
HTTP status.
"""

from __future__ import annotations


class JupiterError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def bad_request(detail: str) -> JupiterError:
    return JupiterError(400, detail)


def unauthorized(detail: str) -> JupiterError:
    return JupiterError(401, detail)


def forbidden(detail: str) -> JupiterError:
    return JupiterError(403, detail)


def not_found(detail: str) -> JupiterError:
    return JupiterError(404, detail)


def conflict(detail: str) -> JupiterError:
    return JupiterError(409, detail)


def unprocessable(detail: str) -> JupiterError:
    return JupiterError(422, detail)


def payment_required(detail: str) -> JupiterError:
    return JupiterError(402, detail)
