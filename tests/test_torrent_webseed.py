import os
import unittest

from tools import torrent_webseed as tw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://plgames-wow.ru/launcher/client/PLGames_Wow3.3.5.rar"


def sample():
    return tw.bencode({b"announce": b"udp://t.example:1337/announce",
                       b"info": {b"name": b"c.rar", b"length": 10, b"piece length": 4, b"pieces": b"x" * 60}})


class WebSeedTests(unittest.TestCase):
    def test_adds_url_list_and_keeps_info_hash(self):
        before = sample()
        after = tw.add_webseeds(before, [URL])
        self.assertEqual(tw.info_hash(after), tw.info_hash(before))
        t, _ = tw.bdecode(after)
        self.assertEqual(t[b"url-list"], [URL.encode()])
        self.assertEqual(t[b"announce"], b"udp://t.example:1337/announce")

    def test_repeated_run_does_not_duplicate(self):
        once = tw.add_webseeds(sample(), [URL])
        self.assertEqual(tw.add_webseeds(once, [URL]), once)

    def test_rejects_non_http_links(self):
        with self.assertRaises(ValueError):
            tw.add_webseeds(sample(), ["file:///C:/x.rar"])

    def test_client_torrent_in_repo(self):
        data = open(os.path.join(ROOT, "PLGames_Wow3.3.5.torrent"), "rb").read()
        t, _ = tw.bdecode(data)
        self.assertEqual(t[b"info"][b"name"], b"PLGames_Wow3.3.5.rar")
        self.assertIn(URL.encode(), t.get(b"url-list", []))
        self.assertEqual(tw.info_hash(tw.add_webseeds(data, [URL])), tw.info_hash(data))
