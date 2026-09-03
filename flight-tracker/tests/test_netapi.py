"""Tests for the OpenSky client: URLs, credit accounting and tokens.

    pytest tests

Nothing here goes near the network - `requests` is only imported inside
netapi._request, which these tests replace.
"""

import pytest

import geo
import netapi


class TestStatesUrl:
    def test_builds_a_bounding_box_query(self):
        url = netapi.states_url("https://opensky-network.org/api", 53.3548, -1.4839, 30)
        assert url == (
            "https://opensky-network.org/api/states/all"
            "?lamin=52.8548&lomin=-2.3316&lamax=53.8548&lomax=-0.6362"
        )

    def test_trailing_slash_on_the_base(self):
        assert netapi.states_url("http://x/", 0.0, 0.0, 60).startswith("http://x/states/all?")

    def test_radius_is_clamped(self):
        wide = netapi.states_url("http://x", 0.0, 0.0, 9999)
        # 250 NM either side of the equator is a little over 4 degrees.
        assert "lamin=-4.1667" in wide and "lamax=4.1667" in wide

    def test_the_box_contains_the_circle(self):
        lamin, lomin, lamax, lomax = geo.bounding_box(53.3548, -1.4839, 30)
        for bearing in range(0, 360, 15):
            latitude, longitude = geo.project(53.3548, -1.4839, bearing, 30)
            assert lamin <= latitude <= lamax
            assert lomin <= longitude <= lomax


class TestCredits:
    @pytest.mark.parametrize(
        "area,cost", [(0.0, 1), (1.7, 1), (25.0, 1), (25.1, 2), (100.0, 2),
                      (100.1, 3), (400.0, 3), (400.1, 4), (64800.0, 4)],
    )
    def test_cost_bands(self, area, cost):
        assert netapi.credit_cost(area) == cost

    def test_a_thirty_mile_circle_is_one_credit(self):
        box = geo.bounding_box(53.3548, -1.4839, 30)
        assert netapi.credit_cost(geo.box_area(box)) == 1

    @pytest.mark.parametrize("name", ["x-rate-limit-remaining", "X-Rate-Limit-Remaining"])
    def test_header_is_read_whatever_its_case(self, name):
        assert netapi.credits_remaining({name: "398"}) == 398

    def test_missing_or_unparsable_header(self):
        assert netapi.credits_remaining({}) is None
        assert netapi.credits_remaining(None) is None
        assert netapi.credits_remaining({"x-rate-limit-remaining": "lots"}) is None


class TestStatusMessage:
    @pytest.mark.parametrize(
        "status,fragment",
        [(401, "credentials"), (403, "not permitted"), (429, "out of credits"),
         (503, "feed unavailable"), (418, "HTTP 418")],
    )
    def test_messages_say_what_to_do(self, status, fragment):
        assert fragment in netapi.status_message(status)


class TestTokenSource:
    def test_anonymous_by_default(self):
        tokens = netapi.TokenSource("http://auth", "", "")
        assert not tokens.enabled
        assert tokens.headers(0) == {}
        assert tokens.daily_credits == netapi.ANONYMOUS_DAILY_CREDITS

    def test_credentials_raise_the_allowance(self):
        tokens = netapi.TokenSource("http://auth", "id", "secret")
        assert tokens.enabled
        assert tokens.daily_credits == netapi.REGISTERED_DAILY_CREDITS

    def _stub(self, monkeypatch, calls, expires_in=1800):
        def fake_request(url, headers=None, timeout=10, data=None):  # noqa: ARG001
            calls.append((url, headers, data))
            return {"access_token": "tok{}".format(len(calls)),
                    "expires_in": expires_in}, {}

        monkeypatch.setattr(netapi, "_request", fake_request)

    def test_fetches_and_caches_a_token(self, monkeypatch):
        calls = []
        self._stub(monkeypatch, calls)
        tokens = netapi.TokenSource("http://auth", "id", "secret")

        assert tokens.headers(0) == {"Authorization": "Bearer tok1"}
        assert tokens.headers(1000) == {"Authorization": "Bearer tok1"}
        assert len(calls) == 1

    def test_posts_client_credentials_form_encoded(self, monkeypatch):
        calls = []
        self._stub(monkeypatch, calls)
        netapi.TokenSource("http://auth", "id", "secret").headers(0)

        url, headers, data = calls[0]
        assert url == "http://auth"
        assert headers["Content-Type"] == "application/x-www-form-urlencoded"
        assert "grant_type=client_credentials" in data
        assert "client_id=id" in data and "client_secret=secret" in data

    def test_renews_before_the_token_expires(self, monkeypatch):
        calls = []
        self._stub(monkeypatch, calls, expires_in=1800)
        tokens = netapi.TokenSource("http://auth", "id", "secret", margin_ms=60000)

        tokens.headers(0)
        # Good until 1800s less the 60s safety margin.
        assert tokens.headers(1_739_000) == {"Authorization": "Bearer tok1"}
        assert len(calls) == 1
        assert tokens.headers(1_741_000) == {"Authorization": "Bearer tok2"}
        assert len(calls) == 2

    def test_forget_drops_the_cached_token(self, monkeypatch):
        calls = []
        self._stub(monkeypatch, calls)
        tokens = netapi.TokenSource("http://auth", "id", "secret")

        tokens.headers(0)
        tokens.forget()
        assert tokens.headers(0) == {"Authorization": "Bearer tok2"}

    def test_a_response_with_no_token_is_an_error(self, monkeypatch):
        monkeypatch.setattr(
            netapi, "_request", lambda *a, **k: ({"oops": 1}, {})  # noqa: ARG005
        )
        tokens = netapi.TokenSource("http://auth", "id", "secret")
        with pytest.raises(netapi.ApiError):
            tokens.headers(0)


class TestFetchStates:
    def test_returns_the_payload_and_the_credits(self, monkeypatch):
        def fake_request(url, headers=None, timeout=10, data=None):  # noqa: ARG001
            assert "states/all" in url
            return ({"time": 1, "states": []}, {"x-rate-limit-remaining": "397"})

        monkeypatch.setattr(netapi, "_request", fake_request)
        payload, credits = netapi.fetch_states("http://x", 53.0, -1.0, 30)
        assert payload["time"] == 1
        assert credits == 397
