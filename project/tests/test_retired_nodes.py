import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch


class RetiredNodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "bot" / "bot.py"
        spec = importlib.util.spec_from_file_location("bot_under_test", path)
        cls.bot = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {"BOT_TOKEN": "test-only"}):
            spec.loader.exec_module(cls.bot)

    def test_buttons_only_for_enabled_nodes(self):
        bot = self.bot
        for uk, tr in (("", ""), ("uk.example", ""), ("", "tr.example")):
            with self.subTest(uk=uk, tr=tr), patch.object(bot, "UK_HOST", uk), patch.object(bot, "TR_HOST", tr):
                callbacks = {b["callback_data"] for row in bot.kb_admin_service()["inline_keyboard"] for b in row}
                self.assertEqual(bot.CB_ADMIN_DIAG_TR in callbacks, bool(tr))
                self.assertEqual(bot.CB_ADMIN_RESTART_TR in callbacks, bool(tr))
                self.assertEqual(bot.CB_ADMIN_DIAG_UK in callbacks, bool(uk))

    def test_old_disabled_buttons_never_execute_operations(self):
        bot = self.bot
        actions = (bot.CB_ADMIN_DIAG_TR, bot.CB_ADMIN_RESTART_TR, bot.CB_CONFIRM_RESTART_TR)
        msg = {"chat": {"id": 1}, "from": {"id": 1}}
        for action in actions:
            for admin in (True, False):
                with self.subTest(action=action, admin=admin), patch.object(bot, "TR_HOST", ""), \
                        patch.object(bot, "is_admin_user", return_value=admin), \
                        patch.object(bot, "clear_admin_state") as clear, \
                        patch.object(bot, "send_message") as send, \
                        patch.object(bot, "get_admin_state") as state, \
                        patch.object(bot, "run_cmd") as run:
                    bot.dispatch_action(None, msg, action)
                    run.assert_not_called()
                    state.assert_not_called()
                    self.assertEqual(clear.call_count, int(admin))
                    self.assertEqual(send.call_count, int(admin))


if __name__ == "__main__":
    unittest.main()
