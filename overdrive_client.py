import httpx
import time
import random

class OverDriveRESTClient:
    """
    A simple synchronous client (thin httpx wrapper) for accessing OverDrive
    API resources.

    Use example:

    client = OverDriveRESTClient(
        client_key="CLIENT_KEY_HERE",
        client_secret = "CLIENT_SECRET_HERE
    )

    response = client.request('GET', 'checkouts')
    try:
        response.raise_for_error()
    except Exception as e:
        print(e)
    """

    def __init__(
        self,
        client_key = None,
        client_secret = None,
        token_url = "https://oauth.overdrive.com/token",
        base_url = "https://reports.api.overdrive.com/v1/",
        timeout: float = 30.0,
        max_retries = 5,  # max number retry based on transient HTTP responses
        default_headers = None,
    ):
        if not client_key or not client_secret:
            raise ValueError("client_key and client_secret are required.")

        self.client_key = client_key
        self.client_secret = client_secret
        self.token_url = token_url
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.max_retries = max_retries
        self.default_headers = default_headers or {}

        # httpx client
        self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)

        # token state
        self._access_token = None
        self._token_type: str = "Bearer"
        self._token_expires_at: float = 0.0  # epoch seconds

    def fetch_token(self) -> None:
        data = {"grant_type": "client_credentials"}
        headers = {"Accept": "application/json", **self.default_headers}

        try:
            response = self._client.post(
                self.token_url,
                data=data,
                auth=(self.client_key, self.client_secret),
                headers=headers
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise Exception(f"OverDrive token request failed: {e}")

        payload = response.json()
        access_token = payload.get("access_token", None)
        token_type = payload.get("token_type", "Bearer")
        expires_in = int(payload.get("expires_in", 3600))

        if not access_token:
            raise Exception("Token response missing 'access_token'")

        self._access_token = access_token
        self._token_type = token_type
        self._token_expires_at = time.time() + max(0, expires_in - 60)

    def _ensure_token(self) -> None:
        if not self._access_token or time.time() >= self._token_expires_at:
            self.fetch_token()

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """
        Sends a request and retries on transient issues:
        - 202 (honors Retry-After), 408, 425, 429, 500, 502, 503, 504
        - Transport/timeouts (Connect/Read/Protocol/Write)
        Exponential backoff with small jitter is applied when Retry-After is absent.
        """
        method = method.upper()
        # Absolute URL bypasses base_url (httpx behavior)
        url = path if path.startswith(("http://", "https://")) else path.lstrip("/")

        # small local helper parse the number
        def _parse_retry_after(value):
            if not value:
                return None
            v = value.strip()
            return float(v) if v.isdigit() else None

        # retryable statuses per RFC + common service patterns
        retry_statuses = {202, 408, 425, 429, 500, 502, 503, 504}

        last_exc = None
        last_response = None

        # We rebuild headers each attempt to keep Authorization fresh
        # Avoid mutating caller's kwargs: copy and strip any user headers
        base_kwargs = dict(kwargs)
        user_headers = base_kwargs.pop("headers", {}) or {}

        for attempt in range(0, self.max_retries + 1):
            self._ensure_token()

            merged_headers = {
                "Accept": "application/json",
                **self.default_headers,
                **user_headers,
                "Authorization": f"{self._token_type} {self._access_token}",
            }

            try:
                response = self._client.request(
                    method, url, headers=merged_headers, **base_kwargs
                )
                last_response = response

                # If not retryable, return immediately
                if response.status_code not in retry_statuses:
                    return response

                # Compute delay: prefer Retry-After if present for 202/429/etc.
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                if retry_after is None:
                    # simple exponential backoff: 1, 2, 4, 8, 16, ... (capped)
                    retry_after = min(60.0, 2 ** max(0, attempt))
                    # small jitter to prevent stampedes
                    retry_after += random.uniform(0.0, 0.5)

            except (
                httpx.ConnectError,
                httpx.ReadTimeout,
                httpx.RemoteProtocolError,
                httpx.WriteError,
            ) as e:
                last_exc = e
                # backoff for transport errors
                retry_after = min(60.0, 2 ** max(0, attempt)) + random.uniform(0.0, 0.5)

            # Out of retries? Return last response if we have it; else raise last exception.
            if attempt == self.max_retries:
                if last_response is not None:
                    return last_response
                if last_exc is not None:
                    raise last_exc
                raise Exception("Out of retries and no response/exception captured.")

            # Sleep then try again
            time.sleep(max(0.0, retry_after))

        # Should not reach here, but ...
        assert last_response is not None
        return last_response

if __name__ == "__main__":
    # perform a quick test of the transiet 202s

    import httpx
    import time
    from itertools import count
    # import OverDriveRESTClient

    # mock handler: 2 transient 202s, then 200 OK
    attempts = count(1)

    def mock_handler(request: httpx.Request) -> httpx.Response:
        n = next(attempts)
        if n < 3:
            print(f"Simulating transient 202 (attempt {n})")
            return httpx.Response(202, headers={"Retry-After": "0.1"})
        print(f"Simulating success 200 (attempt {n})")
        return httpx.Response(200, json={"ok": True, "attempt": n})


    # setup client and inject mock transport
    mock_transport = httpx.MockTransport(mock_handler)

    client = OverDriveRESTClient(
        client_key="fake_key",
        client_secret="fake_secret"
    )

    # Pre-seed a fake token so fetch_token() never runs
    client._access_token = "TEST_TOKEN"
    client._token_type = "Bearer"
    client._token_expires_at = time.time() + 3600  # 1 hour from now

    # Replace underlying httpx.Client with our mock one
    client._client = httpx.Client(transport=mock_transport, base_url=client.base_url)


    # --- run the test request ---
    response = client.request("GET", "checkouts")

    print("Final status:", response.status_code)
    print("Body:", response.json())
