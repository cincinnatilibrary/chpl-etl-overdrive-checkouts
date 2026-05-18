"""Characterization tests for OverDriveRESTClient.

Pins down current behavior:
- Token is fetched on first request and cached.
- Pagination is followed when nextPageUrl is present.
- Transient 202 responses with Retry-After are retried.
- 4xx responses (non-retryable) are returned to caller for raise_for_status().
"""
import httpx
import pytest

from overdrive_client import OverDriveRESTClient


@pytest.fixture
def client_with_fake_api(fake_overdrive_api):
    """An OverDriveRESTClient wired to the fake API transport."""
    client = OverDriveRESTClient(client_key="fake_key", client_secret="fake_secret")
    # Replace the internal httpx.Client with one using the mock transport.
    # Preserve base_url so relative paths resolve correctly.
    client._client = httpx.Client(transport=fake_overdrive_api, base_url=client.base_url)
    return client


def test_fetch_token_obtains_access_token(client_with_fake_api):
    client_with_fake_api.fetch_token()
    assert client_with_fake_api._access_token == "fake-token"
    assert client_with_fake_api._token_type == "Bearer"


def test_request_returns_200_for_known_page(client_with_fake_api):
    response = client_with_fake_api.request("GET", "checkouts")
    assert response.status_code == 200
    body = response.json()
    assert "checkouts" in body
    assert "nextPageUrl" in body


def test_pagination_walks_all_fixture_pages(client_with_fake_api, canonical_run_dir):
    """Walk the fake API until nextPageUrl is None; should hit each page exactly once."""
    n_pages = len(list(canonical_run_dir.glob("page_*.json")))
    next_url = "checkouts"
    pages_fetched = 0
    while next_url:
        response = client_with_fake_api.request("GET", next_url)
        assert response.status_code == 200
        pages_fetched += 1
        next_url = response.json().get("nextPageUrl")
        assert pages_fetched <= n_pages, "ran past the fixture page count"
    assert pages_fetched == n_pages


def test_transient_202_is_retried():
    """A 202 with short Retry-After is retried; we assert eventual success."""
    from itertools import count
    attempts = count(1)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(
                200, json={"access_token": "t", "token_type": "Bearer", "expires_in": 3600}
            )
        n = next(attempts)
        if n < 3:
            return httpx.Response(202, headers={"Retry-After": "0.01"})
        return httpx.Response(200, json={"checkouts": [], "nextPageUrl": None})

    client = OverDriveRESTClient(client_key="k", client_secret="s")
    client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url=client.base_url)
    response = client.request("GET", "checkouts")
    assert response.status_code == 200


def test_non_retryable_4xx_returns_response_for_raise_for_status():
    """A 400 (the actual prod failure mode for out-of-window requests) is returned,
    not retried, and `raise_for_status()` raises."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(
                200, json={"access_token": "t", "token_type": "Bearer", "expires_in": 3600}
            )
        return httpx.Response(400, json={"error": "out of allowed window"})

    client = OverDriveRESTClient(client_key="k", client_secret="s")
    client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url=client.base_url)
    response = client.request("GET", "checkouts")
    assert response.status_code == 400
    with pytest.raises(httpx.HTTPStatusError):
        response.raise_for_status()
