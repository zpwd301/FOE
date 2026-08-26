from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path

from sync_foe_treasury import (
    Config,
    FoeClient,
    GoodsCatalog,
    SyncError,
    extract_forge_hx_config,
    extract_gateway_h,
    extract_startup_goods,
    find_forge_hx_bundle_candidates,
    fetch_contribution_logs,
    read_env_file,
    transform_contribution_logs,
    write_treasury_snapshot,
)


class CredentialFileTests(unittest.TestCase):
    def test_reads_values_without_shell_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.foe"
            path.write_text(
                'FOE_USERNAME="member@example.com"\n'
                "FOE_PASSWORD='literal $value = still literal'\n"
                "FOE_WORLD=us24\n",
                encoding="utf-8",
            )
            os.chmod(path, 0o600)
            values = read_env_file(path)
            self.assertEqual(values["FOE_USERNAME"], "member@example.com")
            self.assertEqual(values["FOE_PASSWORD"], "literal $value = still literal")

    @unittest.skipUnless(os.name == "posix", "POSIX permission check")
    def test_rejects_group_or_world_readable_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.foe"
            path.write_text("FOE_USERNAME=x\nFOE_PASSWORD=y\n", encoding="utf-8")
            os.chmod(path, 0o644)
            with self.assertRaisesRegex(SyncError, "chmod 600"):
                read_env_file(path)


class LoginParsingTests(unittest.TestCase):
    def test_extracts_gateway_token_from_url_or_html(self) -> None:
        expected = "abcDEF_1234567890"
        self.assertEqual(
            extract_gateway_h([f"https://us24.forgeofempires.com/game/json?h={expected}"]),
            expected,
        )
        self.assertEqual(
            extract_gateway_h([f'<script>window.gatewayH="{expected}"</script>']),
            expected,
        )

    def test_extracts_current_forge_hx_client_configuration(self) -> None:
        bundle = (
            'a.requestHeaders=["version=1.341","requiredVersion=1.341"];'
            'return hash(this._signatureHash+"public-bundle-secret=="+a),1,10)'
        )
        self.assertEqual(
            extract_forge_hx_config(bundle),
            ("1.341", "public-bundle-secret=="),
        )

    def test_rejects_unparseable_forge_hx_configuration(self) -> None:
        with self.assertRaisesRegex(SyncError, "no game API request was sent"):
            extract_forge_hx_config("bundle format changed")


class GatewayRequestTests(unittest.TestCase):
    def test_request_ids_start_at_one_and_increment_for_every_call(self) -> None:
        class RecordingClient(FoeClient):
            def __init__(self) -> None:
                super().__init__(
                    Config(
                        username="member",
                        password="secret",
                        world="us24",
                        market="us",
                        timeout=30,
                        contribution_lookback_days=3,
                        log_page_size=100,
                        request_delay_seconds=0,
                        h_value="gateway-token",
                        client_version="1.333",
                        signature_secret="signature-secret",
                    )
                )
                self.sent_request_ids: list[int] = []

            def _request(self, url: str, **kwargs: object) -> tuple[str, str]:
                body = json.loads(bytes(kwargs["data"]).decode("utf-8"))
                request_id = int(body[0]["requestId"])
                self.sent_request_ids.append(request_id)
                response = [
                    {
                        "__class__": "ServerResponse",
                        "requestId": request_id,
                        "requestClass": body[0]["requestClass"],
                        "requestMethod": body[0]["requestMethod"],
                        "responseData": {"accepted": True},
                    }
                ]
                return url, json.dumps(response)

        client = RecordingClient()
        self.assertEqual(client.call("ClanService", "getTreasuryBag", []), {"accepted": True})
        self.assertEqual(client.call("ClanService", "getTreasuryLogs", []), {"accepted": True})
        self.assertEqual(client.sent_request_ids, [1, 2])

    def test_initializes_startup_and_clan_before_treasury(self) -> None:
        class RecordingClient(FoeClient):
            def __init__(self) -> None:
                super().__init__(
                    Config(
                        username="member",
                        password="secret",
                        world="us24",
                        market="us",
                        timeout=30,
                        contribution_lookback_days=3,
                        log_page_size=100,
                        request_delay_seconds=0,
                        h_value="gateway-token",
                        client_version="1.341",
                        signature_secret="signature-secret",
                    )
                )
                self.sent_requests: list[tuple[int, str, str]] = []

            def _request(self, url: str, **kwargs: object) -> tuple[str, str]:
                body = json.loads(bytes(kwargs["data"]).decode("utf-8"))
                request = body[0]
                self.sent_requests.append(
                    (
                        int(request["requestId"]),
                        str(request["requestClass"]),
                        str(request["requestMethod"]),
                    )
                )
                response_data = (
                    {"goodsList": [{"id": "lumber", "name": "Lumber"}]}
                    if request["requestMethod"] == "getData"
                    else {}
                )
                response = [{"requestId": request["requestId"], "responseData": response_data}]
                response[0]["requestClass"] = request["requestClass"]
                response[0]["requestMethod"] = request["requestMethod"]
                return url, json.dumps(response)

        client = RecordingClient()
        client.initialize_gateway()
        client.call("ClanService", "getTreasuryBag", [])
        self.assertEqual(
            client.sent_requests,
            [
                (1, "StartupService", "getData"),
                (2, "ClanService", "getOwnClanData"),
                (3, "ClanService", "getTreasuryBag"),
            ],
        )

    def test_refuses_to_repeat_failed_gateway_initialization(self) -> None:
        class FailingClient(FoeClient):
            def call(self, request_class: str, request_method: str, request_data: list[object]):
                raise SyncError("first request failed")

        client = FailingClient(
            Config(
                username="member",
                password="secret",
                world="us24",
                market="us",
                timeout=30,
                contribution_lookback_days=3,
                log_page_size=100,
                request_delay_seconds=0,
            )
        )
        with self.assertRaisesRegex(SyncError, "first request failed"):
            client.initialize_gateway()
        with self.assertRaisesRegex(SyncError, "refusing to repeat"):
            client.initialize_gateway()

    def test_matches_response_by_id_class_and_method(self) -> None:
        class MultiplexedClient(FoeClient):
            def _request(self, url: str, **kwargs: object) -> tuple[str, str]:
                request = json.loads(bytes(kwargs["data"]).decode("utf-8"))[0]
                request_id = request["requestId"]
                response = [
                    {
                        "requestId": request_id,
                        "requestClass": "MessageService",
                        "requestMethod": "newMessage",
                        "responseData": True,
                    },
                    {
                        "requestId": request_id,
                        "requestClass": request["requestClass"],
                        "requestMethod": request["requestMethod"],
                        "responseData": {"resources": {"good": 123}},
                    },
                ]
                return url, json.dumps(response)

        client = MultiplexedClient(
            Config(
                username="member",
                password="secret",
                world="us24",
                market="us",
                timeout=30,
                contribution_lookback_days=3,
                log_page_size=100,
                request_delay_seconds=0,
                h_value="gateway-token",
                client_version="1.341",
                signature_secret="signature-secret",
            )
        )
        response = client.call("ClanService", "getTreasuryBag", [])
        self.assertEqual(response, {"resources": {"good": 123}})


class ClientConfigurationTests(unittest.TestCase):
    BUNDLE = (
        'headers=["version=1.341","requiredVersion=1.341"];'
        'hash(this._signatureHash+"live-secret=="+a),1,10)'
    )
    INDEX = (
        '<script src="https://foeus.innogamescdn.com/cache/'
        'ForgeHX-current.js"></script>'
    )

    @staticmethod
    def config(*, version: str = "auto", secret: str = "") -> Config:
        return Config(
            username="member",
            password="secret",
            world="us24",
            market="us",
            timeout=30,
            contribution_lookback_days=3,
            log_page_size=100,
            request_delay_seconds=0,
            client_version=version,
            signature_secret=secret,
        )

    def test_always_uses_configuration_from_live_bundle(self) -> None:
        class BundleClient(FoeClient):
            def _request(self, url: str, **kwargs: object) -> tuple[str, str]:
                return url, ClientConfigurationTests.BUNDLE

        client = BundleClient(self.config())
        client._discover_client_config(self.INDEX, "https://us24.example/game/index?")
        self.assertEqual(client.client_version, "1.341")
        self.assertEqual(client.signature_secret, "live-secret==")

    def test_stale_manual_configuration_fails_closed(self) -> None:
        class BundleClient(FoeClient):
            def _request(self, url: str, **kwargs: object) -> tuple[str, str]:
                return url, ClientConfigurationTests.BUNDLE

        client = BundleClient(self.config(version="1.333", secret="stale-secret"))
        with self.assertRaisesRegex(SyncError, "does not match.*no game API request was sent"):
            client._discover_client_config(self.INDEX, "https://us24.example/game/index?")

    def test_rejects_placeholder_and_selects_market_bundle(self) -> None:
        html = (
            '<script src="https://foezz.innogamescdn.com/cache/'
            'ForgeHX-openfl7.1.1-a1b2c3d4.js"></script>'
            '<script src="https://foeus.innogamescdn.com/cache/'
            'ForgeHX-openfl7.1.1-33f51c8e.js"></script>'
        )
        candidates, selected = find_forge_hx_bundle_candidates(
            html, "https://us24.forgeofempires.com/game/index?", "us"
        )
        self.assertEqual(len(candidates), 2)
        self.assertEqual(
            selected,
            "https://foeus.innogamescdn.com/cache/ForgeHX-openfl7.1.1-33f51c8e.js",
        )

    def test_fails_closed_when_only_placeholder_bundle_exists(self) -> None:
        html = (
            '<script src="https://foezz.innogamescdn.com/cache/'
            'ForgeHX-openfl7.1.1-a1b2c3d4.js"></script>'
        )
        with self.assertRaisesRegex(SyncError, "exactly one.*no game API request was sent"):
            find_forge_hx_bundle_candidates(
                html, "https://us24.forgeofempires.com/game/index?", "us"
            )


class TreasurySnapshotTests(unittest.TestCase):
    def test_extracts_game_goods_from_startup_data(self) -> None:
        goods = extract_startup_goods(
            {"goodsList": [{"id": "fine_lumber", "name": "Lumber", "era": "BronzeAge"}]}
        )
        self.assertEqual(goods[0]["id"], "fine_lumber")

    def test_maps_legacy_full_schema_before_stellar_age(self) -> None:
        goods = [f"Good {index}" for index in range(110)]
        catalog = GoodsCatalog(goods)
        self.assertEqual(catalog.by_display_name[goods[0]].era_name, "Bronze Age")
        self.assertEqual(
            catalog.by_display_name[goods[-1]].era_name,
            "Space Age Space Hub",
        )
        self.assertEqual(catalog.by_display_name[goods[-1]].era_id, 23)

    def test_writes_an_idempotent_daily_snapshot(self) -> None:
        goods = [f"Good {index}" for index in range(10)]
        resources = {f"good_{index}": 1000 + index for index in range(10)}
        game_goods = [
            {"id": f"good_{index}", "name": good}
            for index, good in enumerate(goods)
        ]
        existing = [
            (
                dt.date(2026, 8, 16),
                {good: index for index, good in enumerate(goods)},
            )
        ]
        with tempfile.TemporaryDirectory() as directory:
            path, count = write_treasury_snapshot(
                output_dir=Path(directory),
                goods=goods,
                rows=existing,
                resources=resources,
                snapshot_date=dt.date(2026, 8, 17),
                game_goods=game_goods,
            )
            self.assertEqual(count, 2)
            self.assertEqual(path.name, "stats-2026-08-17.csv")
            text = path.read_text(encoding="utf-8")
            self.assertIn('"2026-08-17 00:00:00";1000;1001', text)

    def test_uses_game_resource_ids_and_zero_fills_omitted_goods(self) -> None:
        goods = [f"Good {index}" for index in range(10)]
        game_goods = [
            {"id": f"internal_resource_{index}", "name": good}
            for index, good in enumerate(goods)
        ]
        resources = {
            "internal_resource_0": 123,
            "internal_resource_9": 999,
        }
        with tempfile.TemporaryDirectory() as directory:
            path, _count = write_treasury_snapshot(
                output_dir=Path(directory),
                goods=goods,
                rows=[],
                resources=resources,
                snapshot_date=dt.date(2026, 8, 17),
                game_goods=game_goods,
            )
            row = path.read_text(encoding="utf-8").splitlines()[1]
            self.assertEqual(
                row,
                '"2026-08-17 00:00:00";123;0;0;0;0;0;0;0;0;999',
            )


class ContributionTests(unittest.TestCase):
    def test_fetch_stops_after_overlap_cutoff(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.calls: list[list[object]] = []

            def call(self, request_class: str, request_method: str, request_data: list[object]):
                self.calls.append(request_data)
                offset = int(request_data[1])
                pages = {
                    0: [
                        {"createdAt": "2026-08-17T10:00:00"},
                        {"createdAt": "2026-08-17T09:00:00"},
                    ],
                    2: [
                        {"createdAt": "2026-08-16T23:00:00"},
                        {"createdAt": "2026-08-15T22:00:00"},
                    ],
                }
                return {"count": 20, "logs": pages.get(offset, [])}

        client = FakeClient()
        rows, total, pages = fetch_contribution_logs(
            client,  # type: ignore[arg-type]
            cutoff=dt.datetime(2026, 8, 16, 0, 0),
            page_size=2,
            delay_seconds=0,
        )
        self.assertEqual(len(rows), 4)
        self.assertEqual(total, 20)
        self.assertEqual(pages, 2)

    def test_transforms_game_log_to_dashboard_schema(self) -> None:
        catalog = GoodsCatalog([f"Good {index}" for index in range(10)])
        rows = transform_contribution_logs(
            [
                {
                    "createdAt": "2026-08-17T10:00:00",
                    "resource": "good_7",
                    "amount": 50,
                    "action": "Building production",
                    "player": {"player_id": 123, "name": "Member"},
                }
            ],
            catalog=catalog,
            cutoff=dt.datetime(2026, 8, 16),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["good"], "Good 7")
        self.assertEqual(rows[0]["era"], "24 - Stellar Age: Discovery")
        self.assertEqual(rows[0]["amount"], 50)


if __name__ == "__main__":
    unittest.main()
