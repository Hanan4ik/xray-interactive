import unittest

from xray_interactive.render import layout_action_lines


class ActionLayoutTests(unittest.TestCase):
    def test_actions_wrap_instead_of_being_truncated(self):
        labels = [
            "+ VLESS inbound",
            "+ Tunnel inbound",
            "+ SOCKS inbound",
            "+ HTTP inbound",
        ]
        lines = layout_action_lines(labels, selected_index=0, width=24, max_lines=10)

        self.assertGreater(len(lines), 1)
        rendered = "\n".join(lines)
        for label in labels:
            self.assertIn(label, rendered)
        self.assertTrue(all(len(line) <= 24 for line in lines))

    def test_selected_action_remains_visible_in_short_terminal(self):
        labels = [f"action {i}" for i in range(8)]
        lines = layout_action_lines(labels, selected_index=7, width=12, max_lines=2)

        self.assertLessEqual(len(lines), 2)
        self.assertIn("▶ action 7", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
