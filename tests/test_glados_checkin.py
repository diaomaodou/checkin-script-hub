import hashlib
import io
import os
import unittest
from contextlib import ExitStack, redirect_stdout
from unittest.mock import Mock, patch

import requests

import glados_checkin as glados


def response(payload=None, status=200):
    result = Mock()
    result.status_code = status
    result.json.return_value = payload
    return result


class CheckinTests(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        session_patch = patch.object(glados.requests, "Session")
        self.session = session_patch.start().return_value
        self.addCleanup(session_patch.stop)
        self.client = glados.Glados("gld:sess=fake; gld:sess.sig=fake", 1)
        sleep_patch = patch.object(glados.time, "sleep")
        self.sleep = sleep_patch.start()
        self.addCleanup(sleep_patch.stop)
        env_patch = patch.dict(
            os.environ, {"GLADOS_MAX_ATTEMPTS": "3", "GLADOS_RETRY_DELAY_SECONDS": "60"}
        )
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def challenge(self):
        return response({"code": 0, "nonce": "test-nonce", "ttl": 300000})

    def test_challenge_wait_proof_and_same_origin_submission(self):
        self.session.get.return_value = self.challenge()
        self.session.post.return_value = response(
            {"code": 0, "message": "Checkin! Got 20 Points"}
        )
        events = []
        self.session.get.side_effect = lambda *a, **kw: (
            events.append("challenge") or self.challenge()
        )
        self.sleep.side_effect = lambda seconds: events.append(("wait", seconds))
        self.session.post.side_effect = lambda *a, **kw: (
            events.append("submit") or response({"code": 0})
        )
        self.assertEqual(self.client._checkin()["code"], 0)
        self.assertEqual(events, ["challenge", ("wait", 2.7), "submit"])
        self.session.get.assert_called_once_with(
            "https://glados.cloud/api/user/checkin/challenge",
            timeout=15,
            allow_redirects=False,
        )
        self.session.post.assert_called_once_with(
            "https://glados.cloud/api/user/checkin",
            json={
                "token": "glados.cloud",
                "nonce": "test-nonce",
                "proof": hashlib.sha256(b"test-nonce.glados-observe-v1").hexdigest(),
            },
            timeout=15,
            allow_redirects=False,
        )

    def test_invalid_challenge_never_posts(self):
        for payload in (
            {"code": 1},
            {"code": 0, "nonce": ""},
            {"code": 0, "nonce": "x" * 4097},
            {"code": 0, "nonce": "x", "ttl": 2700},
            {"code": 0, "nonce": "x", "ttl": True},
            {"code": 0, "nonce": "x", "ttl": "300000"},
            {"code": 0, "nonce": "x", "ttl": float("nan")},
            {"code": 0, "nonce": "x", "ttl": float("inf")},
        ):
            with self.subTest(payload=payload):
                self.session.get.return_value = response(payload)
                result = self.client._checkin()
                self.assertTrue(result.get("request_failed"))
                self.session.post.assert_not_called()
        self.sleep.assert_not_called()

    def test_expired_challenge_never_posts(self):
        self.session.get.return_value = self.challenge()
        with patch.object(glados.time, "monotonic", side_effect=[0, 301]):
            result = self.client._checkin()
        self.assertTrue(result.get("request_failed"))
        self.session.post.assert_not_called()

    def test_timeout_retries_with_fresh_challenge(self):
        self.session.get.side_effect = [
            response({"code": 0, "nonce": "first", "ttl": 300000}),
            response({"code": 0, "nonce": "second", "ttl": 300000}),
            response(
                {"code": 0, "data": {"email": "tester@example.org", "leftDays": "42.9"}}
            ),
            response({"points": "120.9"}),
        ]
        self.session.post.side_effect = [
            requests.Timeout("secret"),
            response({"code": 0}),
        ]
        message, ok = self.client.main()
        self.assertTrue(ok)
        self.assertIn("120", message)
        self.assertEqual(
            [call[1]["json"]["nonce"] for call in self.session.post.call_args_list],
            ["first", "second"],
        )
        self.sleep.assert_any_call(60)

    def test_transport_failure_exhausts_three_attempts_and_skips_info(self):
        self.session.get.side_effect = requests.Timeout("secret-cookie")
        message, ok = self.client.main()
        self.assertFalse(ok)
        self.assertEqual(self.session.get.call_count, 3)
        self.session.post.assert_not_called()
        self.assertNotIn("secret-cookie", message)
        self.assertIn("未知", message)

    def test_auth_rejection_stops_all_followup_requests(self):
        for rejected in (
            response({"code": -2, "message": "没有权限"}),
            response({"code": 1, "reason": "device-mismatch"}),
            response({"code": 0, "message": "Automated check-in detected"}),
            response({}, 401),
            response({}, 403),
        ):
            with self.subTest(rejected=rejected):
                self.session.reset_mock()
                self.session.get.side_effect = None
                self.session.get.return_value = self.challenge()
                self.session.post.return_value = rejected
                message, ok = self.client.main()
                self.assertFalse(ok)
                self.assertEqual(self.session.get.call_count, 1)
                self.assertEqual(self.session.post.call_count, 1)

    def test_challenge_auth_failure_does_not_submit_or_retry(self):
        self.session.get.return_value = response({}, 403)
        _, ok = self.client.main()
        self.assertFalse(ok)
        self.session.get.assert_called_once()
        self.session.post.assert_not_called()
        self.sleep.assert_not_called()

    def test_success_markers_inside_failure_messages_are_not_success(self):
        for message in (
            "Today's observation logged is unavailable; please try again later",
            "Error: Checkin! Got no Points",
            "Not Checkin Repeats! Please Try Tomorrow",
        ):
            with self.subTest(message=message):
                self.session.reset_mock()
                self.session.get.return_value = self.challenge()
                self.session.post.return_value = response(
                    {"code": 1, "message": message}
                )
                _, ok = self.client.main()
                self.assertFalse(ok)
                self.session.post.assert_called_once()
                self.session.get.assert_called_once()

    def test_failed_points_response_keeps_checkin_balance(self):
        self.session.get.side_effect = [
            self.challenge(),
            response({"code": 0, "data": {}}),
            response({"code": 1, "message": "temporarily unavailable", "points": 0}),
        ]
        self.session.post.return_value = response(
            {"code": 0, "list": [{"balance": "99"}]}
        )
        message, ok = self.client.main()
        self.assertTrue(ok)
        self.assertIn("当前积分: 99", message)
        self.assertIn("积分未刷新", message)

    def test_unknown_code_one_is_not_already_checked_in(self):
        self.session.get.return_value = self.challenge()
        self.session.post.return_value = response(
            {"code": 1, "message": "please checkin via another site"}
        )
        message, ok = self.client.main()
        self.assertFalse(ok)
        self.assertNotIn("今日已签到", message)
        self.session.post.assert_called_once()

    def test_success_queries_latest_status_and_points(self):
        for payload in (
            {"code": 0, "message": "Checkin! Got 1 Points"},
            {"code": 1, "message": "Checkin! Got 20 Points"},
            {"code": 1, "message": "Checkin Repeats! Please Try Tomorrow"},
            {"code": 1, "message": "Today's observation logged. See you tomorrow"},
        ):
            with self.subTest(payload=payload):
                self.session.reset_mock()
                self.session.get.side_effect = [
                    self.challenge(),
                    response(
                        {
                            "code": 0,
                            "data": {"email": "tester@example.org", "leftDays": "42.9"},
                        }
                    ),
                    response({"points": "120.9"}),
                ]
                self.session.post.return_value = response(payload)
                message, ok = self.client.main()
                self.assertTrue(ok)
                self.assertIn("120", message)
                self.assertIn("42 天", message)
                self.assertIn("te***@example.org", message)
                self.assertEqual(
                    [call[0][0] for call in self.session.get.call_args_list],
                    [
                        "https://glados.cloud/api/user/checkin/challenge",
                        "https://glados.cloud/api/user/status",
                        "https://glados.cloud/api/user/points",
                    ],
                )
                self.session.post.assert_called_once()

    def test_info_query_failures_do_not_undo_confirmed_checkin(self):
        self.session.get.side_effect = [
            self.challenge(),
            requests.Timeout(),
            requests.Timeout(),
        ]
        self.session.post.return_value = response(
            {"code": 0, "list": [{"balance": "99.9"}]}
        )
        message, ok = self.client.main()
        self.assertTrue(ok)
        self.assertIn("99", message)
        self.assertIn("未", message)
        self.session.post.assert_called_once()

    def test_status_auth_rejection_skips_points_query(self):
        self.session.get.side_effect = [self.challenge(), response({}, 403)]
        self.session.post.return_value = response({"code": 0})
        _, ok = self.client.main()
        self.assertTrue(ok)
        self.assertEqual(self.session.get.call_count, 2)

    def test_server_error_retries(self):
        self.session.get.side_effect = [
            response({}, 503),
            self.challenge(),
            response({"code": 0, "data": {}}),
            response({"points": 0}),
        ]
        self.session.post.return_value = response({"code": 0})
        _, ok = self.client.main()
        self.assertTrue(ok)
        self.sleep.assert_any_call(60)

    def test_invalid_response_is_retried_without_legacy_submission(self):
        for invalid in (response([]), response(None)):
            with self.subTest(invalid=invalid):
                self.session.reset_mock()
                self.session.get.return_value = invalid
                _, ok = self.client.main()
                self.assertFalse(ok)
                self.assertEqual(self.session.get.call_count, 3)
                self.session.post.assert_not_called()

    def test_redirect_is_not_retried_or_followed(self):
        self.session.get.return_value = response({}, 302)
        _, ok = self.client.main()
        self.assertFalse(ok)
        self.session.get.assert_called_once_with(
            "https://glados.cloud/api/user/checkin/challenge",
            timeout=15,
            allow_redirects=False,
        )
        self.session.post.assert_not_called()

    def test_sensitive_request_exception_is_not_exposed(self):
        self.session.get.side_effect = requests.exceptions.InvalidHeader(
            "gld:sess=secret-value"
        )
        message, ok = self.client.main()
        self.assertFalse(ok)
        self.assertNotIn("secret-value", message)
        self.session.get.assert_called_once()


class MainTests(unittest.TestCase):
    def setUp(self):
        output = redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def test_exit_code_aggregates_accounts_and_keeps_notifications(self):
        for outcomes, expected in (([True, True], 0), ([False, True], 1)):
            with ExitStack() as stack:
                stack.enter_context(self.subTest(outcomes=outcomes))
                stack.enter_context(
                    patch.object(
                        glados, "get_accounts", return_value=["fake1", "fake2"]
                    )
                )
                stack.enter_context(patch.object(glados, "random_signin", False))
                stack.enter_context(patch.object(glados.time, "sleep"))
                notify = stack.enter_context(patch.object(glados, "notify_user"))
                stack.enter_context(
                    patch.object(
                        glados.Glados,
                        "main",
                        side_effect=[("result", ok) for ok in outcomes],
                    )
                )
                self.assertEqual(glados.main(), expected)
                self.assertEqual(notify.call_count, 3)

    def test_missing_cookie_fails_without_delay(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(glados, "get_accounts", return_value=[]))
            stack.enter_context(patch.object(glados, "notify_user"))
            sleep = stack.enter_context(patch.object(glados.time, "sleep"))
            self.assertEqual(glados.main(), 1)
            sleep.assert_not_called()

    def test_unexpected_error_does_not_leak_secret_or_skip_other_accounts(self):
        with ExitStack() as stack:
            stack.enter_context(
                patch.object(glados, "get_accounts", return_value=["fake1", "fake2"])
            )
            stack.enter_context(patch.object(glados, "random_signin", False))
            stack.enter_context(patch.object(glados.time, "sleep"))
            notify = stack.enter_context(patch.object(glados, "notify_user"))
            run = stack.enter_context(
                patch.object(
                    glados.Glados,
                    "main",
                    side_effect=[ValueError("secret-value"), ("ok", True)],
                )
            )
            self.assertEqual(glados.main(), 1)
            self.assertEqual(run.call_count, 2)
            self.assertNotIn("secret-value", str(notify.call_args_list))


if __name__ == "__main__":
    unittest.main()
