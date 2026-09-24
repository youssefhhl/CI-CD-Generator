"""HTTP API layer for the CI/CD Workflow Generator.

This layer exposes the stack detection business logic over HTTP. It must
not contain detection logic itself; it only adapts requests/responses to
and from :mod:`src.detector`.
"""
