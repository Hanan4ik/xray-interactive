import unittest

from xray_interactive.importer import parse_vless_link


class ImporterTests(unittest.TestCase):
    def test_import_reality_raw_link(self):
        link = (
            "vless://12345678-1234-1234-1234-123456789abc@1.2.3.4:443"
            "?type=tcp&security=reality&encryption=none&flow=xtls-rprx-vision"
            "&fp=chrome&sni=example.com&sid=&pbk=AbCdEfGhIjKlMnOpQrStUvWxYz1234567890abcd"
            "#Example_VPN"
        )
        result = parse_vless_link(link, {"inbounds": [], "outbounds": []})
        out = result.outbound
        self.assertEqual(out["protocol"], "vless")
        self.assertEqual(out["settings"]["address"], "1.2.3.4")
        self.assertEqual(out["settings"]["port"], 443)
        self.assertEqual(out["streamSettings"]["method"], "raw")
        self.assertEqual(out["streamSettings"]["security"], "reality")
        self.assertEqual(
            out["streamSettings"]["realitySettings"]["password"],
            "AbCdEfGhIjKlMnOpQrStUvWxYz1234567890abcd",
        )
        self.assertEqual(out["tag"], "Example_VPN")

    def test_import_xhttp(self):
        link = (
            "vless://abc@example.com:443?type=xhttp&security=reality&"
            "path=%2Fsecret&mode=auto&sni=example.com&fp=chrome&pbk=xyz#xhttp"
        )
        out = parse_vless_link(link, {"inbounds": [], "outbounds": []}).outbound
        self.assertEqual(out["streamSettings"]["method"], "xhttp")
        self.assertEqual(out["streamSettings"]["xhttpSettings"]["path"], "/secret")

    def test_unique_tag(self):
        cfg = {"inbounds": [], "outbounds": [{"tag": "vpn"}]}
        out = parse_vless_link("vless://abc@example.com:443#vpn", cfg).outbound
        self.assertEqual(out["tag"], "vpn-2")


if __name__ == "__main__":
    unittest.main()
