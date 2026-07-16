"""
Summary: Smoke-tests the installed OMYM2 package through its HTTP surface.
Why: Proves bundled Vite assets and Bootstrap work without source-tree imports.
"""
# ruff: noqa: INP001, T201 -- Standalone smoke script reports concise CLI results.

from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
from html.parser import HTMLParser
from typing import TYPE_CHECKING, cast, override
from urllib.parse import urljoin, urlsplit

from omym2.config import (
    WEB_CONTENT_SECURITY_POLICY,
    WEB_CONTENT_TYPE_OPTIONS_HEADER_NAME,
    WEB_CONTENT_TYPE_OPTIONS_VALUE,
    WEB_CORRELATION_HEADER_NAME,
    WEB_CSP_HEADER_NAME,
    WEB_REFERRER_POLICY,
    WEB_REFERRER_POLICY_HEADER_NAME,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

DEFAULT_BASE_URL_ENVIRONMENT_VARIABLE = "OMYM2_PACKAGE_BASE_URL"
ROOT_ROUTE = "/"
DEEP_ROUTE = "/plans/01912345-6789-7abc-8def-0123456789ab"
BOOTSTRAP_ROUTE = "/api/bootstrap"
HTTP_TIMEOUT_SECONDS = 10.0
SUCCESS_STATUS_CODE = 200
HTML_ACCEPT_HEADER = "text/html"
JSON_ACCEPT_HEADER = "application/json"
EXPECTED_HTML_CACHE_CONTROL = "no-cache"
EXPECTED_ASSET_CACHE_CONTROL_PARTS = ("public", "max-age=31536000", "immutable")
EXPECTED_SECURITY_HEADERS = {
    WEB_CSP_HEADER_NAME.lower(): WEB_CONTENT_SECURITY_POLICY,
    WEB_CONTENT_TYPE_OPTIONS_HEADER_NAME.lower(): WEB_CONTENT_TYPE_OPTIONS_VALUE,
    WEB_REFERRER_POLICY_HEADER_NAME.lower(): WEB_REFERRER_POLICY,
}
CORRELATION_HEADER_NAME = WEB_CORRELATION_HEADER_NAME.lower()


class PackageSmokeError(RuntimeError):
    """Raised when the installed Web package fails an observable smoke check."""


class ParsedArgs(argparse.Namespace):
    """Typed command-line arguments for installed-package smoke."""

    def __init__(self, base_url: str | None) -> None:
        super().__init__()
        self.base_url: str | None = base_url


class _AssetReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script" and attributes.get("src"):
            self.references.append(attributes["src"] or "")
        elif tag == "link" and attributes.get("href"):
            self.references.append(attributes["href"] or "")


def smoke_web_package(base_url: str) -> None:
    """Retrieve the installed root, deep route, hashed asset, and Bootstrap."""
    _validate_base_url(base_url)
    root_body, root_headers = _request(base_url, ROOT_ROUTE, HTML_ACCEPT_HEADER)
    _require_content_type(ROOT_ROUTE, root_headers, "text/html")
    if root_headers.get("cache-control") != EXPECTED_HTML_CACHE_CONTROL:
        msg = f"{ROOT_ROUTE} must use Cache-Control: {EXPECTED_HTML_CACHE_CONTROL}."
        raise PackageSmokeError(msg)
    _require_common_headers(ROOT_ROUTE, root_headers)

    deep_body, deep_headers = _request(base_url, DEEP_ROUTE, HTML_ACCEPT_HEADER)
    _require_content_type(DEEP_ROUTE, deep_headers, "text/html")
    _require_common_headers(DEEP_ROUTE, deep_headers)
    if deep_body != root_body:
        msg = "Deep HTML route did not return the installed SPA entry document."
        raise PackageSmokeError(msg)

    asset_reference = _first_asset_reference(root_body)
    _asset_body, asset_headers = _request_bytes(base_url, asset_reference, "*/*")
    cache_control = asset_headers.get("cache-control", "")
    if not all(part in cache_control for part in EXPECTED_ASSET_CACHE_CONTROL_PARTS):
        msg = f"Hashed asset has unexpected Cache-Control: {cache_control!r}"
        raise PackageSmokeError(msg)
    _require_common_headers(asset_reference, asset_headers)

    bootstrap_body, bootstrap_headers = _request(base_url, BOOTSTRAP_ROUTE, JSON_ACCEPT_HEADER)
    _require_content_type(BOOTSTRAP_ROUTE, bootstrap_headers, "application/json")
    _require_common_headers(BOOTSTRAP_ROUTE, bootstrap_headers)
    try:
        payload = cast("object", json.loads(bootstrap_body))
    except json.JSONDecodeError as exc:
        msg = "Bootstrap did not return valid JSON."
        raise PackageSmokeError(msg) from exc
    if not isinstance(payload, dict) or "data" not in payload or "errors" not in payload:
        msg = "Bootstrap did not return the typed API envelope."
        raise PackageSmokeError(msg)


def _request(base_url: str, route: str, accept: str) -> tuple[str, Mapping[str, str]]:
    body, headers = _request_bytes(base_url, route, accept)
    try:
        return body.decode("utf-8"), headers
    except UnicodeDecodeError as exc:
        msg = f"{route} did not return UTF-8 text."
        raise PackageSmokeError(msg) from exc


def _request_bytes(base_url: str, route: str, accept: str) -> tuple[bytes, Mapping[str, str]]:
    request_url = urljoin(f"{base_url.rstrip('/')}/", route)
    base_url_parts = urlsplit(base_url)
    parsed_url = urlsplit(request_url)
    if (
        parsed_url.scheme,
        parsed_url.hostname,
        parsed_url.port,
    ) != (
        base_url_parts.scheme,
        base_url_parts.hostname,
        base_url_parts.port,
    ):
        msg = f"Refusing cross-origin package smoke request for {route!r}."
        raise PackageSmokeError(msg)
    host = parsed_url.hostname
    if host is None:
        msg = f"Unable to determine the loopback host for {route}."
        raise PackageSmokeError(msg)
    request_path = parsed_url.path or "/"
    if parsed_url.query:
        request_path = f"{request_path}?{parsed_url.query}"
    connection = http.client.HTTPConnection(host, parsed_url.port, timeout=HTTP_TIMEOUT_SECONDS)
    try:
        connection.request("GET", request_path, headers={"Accept": accept})
        response = connection.getresponse()
        if response.status != SUCCESS_STATUS_CODE:
            msg = f"{route} returned HTTP {response.status}."
            raise PackageSmokeError(msg)
        headers = {key.lower(): value for key, value in response.getheaders()}
        return response.read(), headers
    except (OSError, http.client.HTTPException, TimeoutError) as exc:
        msg = f"Unable to retrieve {route}: {exc}"
        raise PackageSmokeError(msg) from exc
    finally:
        connection.close()


def _first_asset_reference(index_html: str) -> str:
    parser = _AssetReferenceParser()
    parser.feed(index_html)
    for reference in parser.references:
        parsed_reference = urlsplit(reference)
        if parsed_reference.scheme or parsed_reference.netloc:
            msg = f"Installed index.html contains a non-package-relative asset reference: {reference!r}"
            raise PackageSmokeError(msg)
        if parsed_reference.path.startswith("/assets/") or parsed_reference.path.startswith("assets/"):
            return reference
    msg = "Installed index.html does not reference a hashed /assets/ file."
    raise PackageSmokeError(msg)


def _require_content_type(route: str, headers: Mapping[str, str], expected: str) -> None:
    content_type = headers.get("content-type", "")
    if not content_type.startswith(expected):
        msg = f"{route} returned unexpected Content-Type: {content_type!r}"
        raise PackageSmokeError(msg)


def _require_common_headers(route: str, headers: Mapping[str, str]) -> None:
    missing = [header for header in EXPECTED_SECURITY_HEADERS if not headers.get(header)]
    if missing:
        msg = f"{route} is missing security headers: {missing}"
        raise PackageSmokeError(msg)
    mismatched = {
        header: {"expected": expected, "actual": headers.get(header)}
        for header, expected in EXPECTED_SECURITY_HEADERS.items()
        if headers.get(header) != expected
    }
    if mismatched:
        msg = f"{route} has unexpected security headers: {mismatched}"
        raise PackageSmokeError(msg)
    if not headers.get(CORRELATION_HEADER_NAME):
        msg = f"{route} is missing {CORRELATION_HEADER_NAME}."
        raise PackageSmokeError(msg)


def _validate_base_url(base_url: str) -> None:
    parsed_url = urlsplit(base_url)
    if parsed_url.scheme != "http" or parsed_url.hostname not in {"127.0.0.1", "localhost"}:
        msg = "base URL must be loopback HTTP"
        raise PackageSmokeError(msg)


def _parse_args(argv: Sequence[str] | None) -> ParsedArgs:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--base-url", default=os.environ.get(DEFAULT_BASE_URL_ENVIRONMENT_VARIABLE))
    return parser.parse_args(
        argv,
        namespace=ParsedArgs(os.environ.get(DEFAULT_BASE_URL_ENVIRONMENT_VARIABLE)),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run installed-package HTTP checks and report a concise result."""
    args = _parse_args(argv)
    if args.base_url is None:
        print(
            f"package smoke failed: --base-url or {DEFAULT_BASE_URL_ENVIRONMENT_VARIABLE} is required",
            file=sys.stderr,
        )
        return 1
    try:
        smoke_web_package(args.base_url)
    except PackageSmokeError as exc:
        print(f"package smoke failed: {exc}", file=sys.stderr)
        return 1
    print(f"package smoke passed: {args.base_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
