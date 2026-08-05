import os
import unittest


PORTAL_BASE_URL = os.environ.get("PORTAL_BASE_URL", "http://10.17.7.88:8866").rstrip("/")
PORTAL_RELEASE_ID = os.environ.get("PORTAL_RELEASE_ID", "release_20260805_002")
TARGET_MOLECULE_ID = "EN300-5962644_30111"

SMILES_QUERY = "O=C1C=CC=CN1"
SMARTS_QUERY = "[#8]=[#6]1:[#6]:[#6]:[#6]:[#6]:[#7]:1"
NO_MATCH_QUERY = "C1CCCCCCCCCCCCCCCCCCC1"
INVALID_QUERY = "this_is_not_smiles"

FORBIDDEN_CONSOLE_PATTERNS = [
    "is_valid is not a function",
    "get_smarts is not a function",
    "Unexpected end of JSON input",
    "uncaught",
]


try:
    from playwright.sync_api import sync_playwright  # type: ignore
except Exception:  # pragma: no cover
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "playwright package is not installed")
class TestStructureSearchPlaywright(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._pw = sync_playwright().start()
        cls._browser = cls._pw.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls._browser.close()
        cls._pw.stop()

    def setUp(self):
        self.page = self._browser.new_page()
        self.console_messages = []
        self.failed_requests = []

        def on_console(msg):
            text = msg.text or ""
            if msg.type == "error" or "uncaught" in text.lower():
                self.console_messages.append(text)

        def on_response(resp):
            status = int(resp.status)
            if status >= 400:
                self.failed_requests.append({"url": resp.url, "status": status})

        self.page.on("console", on_console)
        self.page.on("response", on_response)
        self.page.goto(
            "{}/release/{}".format(PORTAL_BASE_URL, PORTAL_RELEASE_ID),
            wait_until="domcontentloaded",
            timeout=60000,
        )

        frame_el = self.page.locator("#hosted-report-shell")
        frame_el.wait_for(state="visible", timeout=60000)
        self.frame = frame_el.element_handle().content_frame()
        self.assertIsNotNone(self.frame, "Hosted report iframe did not load")
        self.frame.wait_for_selector("#structure-search-run", timeout=60000)

    def tearDown(self):
        self.page.close()

    def _assert_no_forbidden_console_errors(self):
        joined = "\n".join(self.console_messages)
        for pattern in FORBIDDEN_CONSOLE_PATTERNS:
            self.assertNotIn(
                pattern.lower(),
                joined.lower(),
                "Forbidden console error detected: {}\nConsole:\n{}".format(pattern, joined),
            )

    def _assert_no_http_errors(self):
        if self.failed_requests:
            msg = "\n".join(["{} {}".format(r["status"], r["url"]) for r in self.failed_requests])
            self.fail("HTTP 4xx/5xx observed during test:\n{}".format(msg))

    def _run_substructure_search(self, query):
        self.frame.get_by_role("button", name="Reset Search").click()
        self.frame.get_by_role("radio", name="Substructure search").check()
        self.frame.get_by_role("textbox", name="Paste SMILES or SMARTS here (e.g. c1ccccc1 or [#6]-[#7])").fill(query)
        self.frame.get_by_role("button", name="Search").click()

        for _ in range(25):
            self.page.wait_for_timeout(250)
            status = self.frame.locator("#structure-search-status .search-status-line").inner_text().strip()
            if status and "Preparing structure search." not in status:
                return status
        return self.frame.locator("#structure-search-status .search-status-line").inner_text().strip()

    def _target_is_visible_in_scaffold_and_deep_dive(self):
        result = self.frame.evaluate(
            """
            (targetMolId) => {
              function visible(el){
                if(!el){return false;}
                var s = window.getComputedStyle(el);
                return s.display !== 'none' && s.visibility !== 'hidden' && el.getClientRects().length > 0;
              }
              var scaffoldCards = Array.from(document.querySelectorAll('.idea-card')).filter(visible);
              var targetCard = scaffoldCards.find(function(card){
                return String(card.textContent || '').indexOf(targetMolId) !== -1;
              });
              var scaffoldId = targetCard ? String(targetCard.getAttribute('data-scaffold') || '') : '';

              if (targetCard && scaffoldId) {
                var deepLink = targetCard.querySelector("a[onclick*='openDeepDive']");
                if (deepLink) {
                  deepLink.click();
                }
              }

              var deepDiveCards = Array.from(document.querySelectorAll('.card'));
              var targetDeep = deepDiveCards.find(function(card){
                return visible(card) && String(card.textContent || '').indexOf(targetMolId) !== -1;
              });

              return {
                scaffoldMatched: !!targetCard,
                scaffoldId: scaffoldId,
                deepDiveMatched: !!targetDeep,
                deepDiveScaffold: targetDeep ? String(targetDeep.getAttribute('data-scaffold') || '') : ''
              };
            }
            """,
            TARGET_MOLECULE_ID,
        )
        self.page.wait_for_timeout(1500)
        return result

    def test_1_smiles_substructure_positive_control(self):
        status = self._run_substructure_search(SMILES_QUERY)
        self.assertNotIn("Invalid", status, "SMILES query should be valid")
        self.assertNotIn("No matching", status, "Positive control should not return no-match")

        vis = self._target_is_visible_in_scaffold_and_deep_dive()
        self.assertTrue(vis["scaffoldMatched"], "Matching scaffold card was not visible for positive-control SMILES query")
        self.assertTrue(vis["deepDiveMatched"], "Target molecule EN300-5962644_30111 was not visible in Deep Dive for SMILES query")

        self._assert_no_forbidden_console_errors()
        self._assert_no_http_errors()

    def test_2_smarts_substructure_positive_control(self):
        status = self._run_substructure_search(SMARTS_QUERY)
        self.assertNotIn("Invalid", status, "SMARTS query should be valid")
        self.assertNotIn("No matching", status, "Positive control SMARTS should not return no-match")

        vis = self._target_is_visible_in_scaffold_and_deep_dive()
        self.assertTrue(vis["scaffoldMatched"], "Matching scaffold card was not visible for positive-control SMARTS query")
        self.assertTrue(vis["deepDiveMatched"], "Target molecule EN300-5962644_30111 was not visible in Deep Dive for SMARTS query")

        self._assert_no_forbidden_console_errors()
        self._assert_no_http_errors()

    def test_3_no_match_query(self):
        status = self._run_substructure_search(NO_MATCH_QUERY)
        self.assertIn("No matches", status, "No-match query should display a clean no-match message")
        self._assert_no_forbidden_console_errors()
        self._assert_no_http_errors()

    def test_4_invalid_query(self):
        status = self._run_substructure_search(INVALID_QUERY)
        self.assertTrue(
            ("Invalid" in status) or ("valid SMARTS or SMILES" in status),
            "Invalid query should display a clean validation message",
        )
        self._assert_no_forbidden_console_errors()
        self._assert_no_http_errors()
