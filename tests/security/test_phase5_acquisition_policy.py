from collections.abc import Sequence

import pytest

from jarvis.research import PublicResearchUrlPolicy, ResearchUrlDenied


async def resolver(*addresses: str) -> Sequence[str]:
    return addresses


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/",
        "file:///etc/passwd",
        "https://user:secret@example.com/",
        "https://localhost/",
        "https://metadata.internal/",
        "https://example.local/",
        "https://127.0.0.1/",
        "https://[::1]/",
        "https://%31%32%37.0.0.1/",
        "https://example.com:8443/",
        "https://example.com/\r\nX-Test: injected",
    ],
)
def test_url_syntax_denies_unsafe_targets(url: str) -> None:
    with pytest.raises(ResearchUrlDenied):
        PublicResearchUrlPolicy().validate_syntax(url)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "224.0.0.1",
        "::1",
        "fc00::1",
        "fe80::1",
    ],
)
async def test_resolved_non_public_addresses_are_denied(address: str) -> None:
    async def fake_resolver(_hostname: str, _port: int) -> Sequence[str]:
        return await resolver(address)

    with pytest.raises(ResearchUrlDenied, match="non-public"):
        await PublicResearchUrlPolicy().validate(
            "https://example.com/source", resolver=fake_resolver
        )


async def test_mixed_public_private_dns_answers_fail_closed() -> None:
    async def fake_resolver(_hostname: str, _port: int) -> Sequence[str]:
        return await resolver("93.184.216.34", "127.0.0.1")

    with pytest.raises(ResearchUrlDenied, match="non-public"):
        await PublicResearchUrlPolicy().validate(
            "https://example.com/source", resolver=fake_resolver
        )


async def test_public_url_is_normalized_and_fragment_removed() -> None:
    async def fake_resolver(_hostname: str, _port: int) -> Sequence[str]:
        return await resolver("93.184.216.34")

    result = await PublicResearchUrlPolicy().validate(
        " HTTPS://Example.COM./source?q=1#private-fragment ", resolver=fake_resolver
    )
    assert result.url == "https://example.com/source?q=1"
    assert result.hostname == "example.com"
    assert result.port == 443
    assert result.resolved_addresses == ("93.184.216.34",)


async def test_allowed_domain_accepts_subdomain_and_denies_suffix_trick() -> None:
    async def fake_resolver(_hostname: str, _port: int) -> Sequence[str]:
        return await resolver("93.184.216.34")

    accepted = await PublicResearchUrlPolicy().validate(
        "https://docs.example.com/source",
        allowed_domains=("example.com",),
        resolver=fake_resolver,
    )
    assert accepted.hostname == "docs.example.com"
    with pytest.raises(ResearchUrlDenied):
        await PublicResearchUrlPolicy().validate(
            "https://example.com.attacker.invalid/source",
            allowed_domains=("example.com",),
            resolver=fake_resolver,
        )
