# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from urllib.parse import urlsplit, parse_qs
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bug_report
from app_info import VERSION, REPOSITORY


class BugReportTests(unittest.TestCase):
    release = {'PRETTY_NAME': 'Ubuntu 26.04 LTS'}
    env = {'XDG_CURRENT_DESKTOP': 'ubuntu:GNOME', 'XDG_SESSION_TYPE': 'wayland', 'HOME': '/home/private-user'}

    def test_prefills_the_issue_form_without_personal_data(self):
        report = {'app': 'Uplugo', 'version': VERSION, 'controllers': [{'controller': 1, 'battery': 70}]}
        url, included = bug_report.issue_url(report, release=self.release, env=self.env)
        self.assertTrue(included)
        self.assertTrue(url.startswith(REPOSITORY+'/issues/new?'))
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query['template'], ['bug_report.yml'])
        self.assertEqual(query['version'], [VERSION])
        self.assertIn('Ubuntu 26.04 LTS · ubuntu:GNOME (wayland)', query['environment'][0])
        self.assertIn('"battery":70', query['diagnostics'][0])
        self.assertNotIn('private-user', url)

    def test_long_reports_stay_out_of_the_link(self):
        report = {'controllers': [{'controller': n, 'note': 'x'*400} for n in range(40)]}
        url, included = bug_report.issue_url(report, release=self.release, env=self.env)
        self.assertFalse(included)
        self.assertLessEqual(len(url), bug_report.MAX_URL)
        self.assertNotIn('diagnostics=', url)

    def test_template_fields_match_the_prefilled_ids(self):
        template = (Path(__file__).resolve().parents[1]/'.github/ISSUE_TEMPLATE/bug_report.yml').read_text()
        for field in ('version', 'environment', 'diagnostics'):
            self.assertIn('id: '+field, template)


if __name__ == '__main__':
    unittest.main()
