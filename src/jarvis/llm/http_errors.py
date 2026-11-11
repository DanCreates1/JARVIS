"""Shared cloud-provider HTTP error mapping."""

import httpx

from .base import (
    ProviderAuthenticationError,
    ProviderModelUnavailableError,
    ProviderProtocolError,
    ProviderQuotaError,
    ProviderUnavailableError,
)


def _raise_status(response: httpx.Response, provider: str) -> None:
    if response.is_success:
        return
    status = response.status_code
    detail = response.text.strip()[:300] or "no response detail"
    if status in {401, 403}:
        raise ProviderAuthenticationError(
            f"{provider} rejected credentials: {detail}", status_code=status
        )
    if status == 429:
        raise ProviderQuotaError(
            f"{provider} free-tier quota exhausted: {detail}", status_code=status
        )
    if status == 404:
        raise ProviderModelUnavailableError(
            f"{provider} model unavailable: {detail}", status_code=status
        )
    if status >= 500:
        raise ProviderUnavailableError(
            f"{provider} unavailable (HTTP {status}): {detail}", status_code=status
        )
    raise ProviderProtocolError(f"{provider} returned HTTP {status}: {detail}", status_code=status)
