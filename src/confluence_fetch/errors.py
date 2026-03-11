from __future__ import annotations


class AppError(Exception):
    exit_code = 1


class UsageError(AppError):
    exit_code = 2


class AuthError(AppError):
    exit_code = 10


class NotFoundError(AppError):
    exit_code = 20


class RateLimitError(AppError):
    exit_code = 30
