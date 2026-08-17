import unittest

from xray_interactive.model import new_config
from xray_interactive.schema import actions_for, template_for


class InboundSchemaTests(unittest.TestCase):
    def test_inbound_picker_includes_socks_and_http(self):
        cfg = new_config()
        templates = [action.default for action in actions_for(cfg, ("inbounds",))]
        self.assertEqual(templates, ["vless", "tunnel", "socks", "http"])

    def test_socks_template_and_guided_users(self):
        cfg = new_config()
        inbound = template_for(cfg, "socks")
        cfg["inbounds"].append(inbound)

        self.assertEqual(inbound["protocol"], "socks")
        self.assertEqual(inbound["settings"]["auth"], "noauth")
        self.assertFalse(inbound["settings"]["udp"])
        actions = actions_for(cfg, ("inbounds", 0, "settings", "users"))
        self.assertEqual(actions[0].default, "proxy-user")

        inbound["settings"]["users"].append({})
        fields = actions_for(cfg, ("inbounds", 0, "settings", "users", 0))
        self.assertEqual([action.key for action in fields], ["user", "pass"])

    def test_http_template(self):
        cfg = new_config()
        inbound = template_for(cfg, "http")
        cfg["inbounds"].append(inbound)

        self.assertEqual(inbound["protocol"], "http")
        self.assertEqual(inbound["port"], 8080)
        self.assertEqual(
            inbound["settings"],
            {"users": [], "allowTransparent": False, "userLevel": 0},
        )
        self.assertEqual(template_for(cfg, "proxy-user"), {"user": "", "pass": ""})


if __name__ == "__main__":
    unittest.main()
