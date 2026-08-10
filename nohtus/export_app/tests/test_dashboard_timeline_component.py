from pathlib import Path
import unittest


class DashboardTimelineComponentTests(unittest.TestCase):
    def test_component_bootstrap_uses_streamlit_protocol(self):
        component = (
            Path(__file__).parents[1]
            / 'components'
            / 'dashboard_timeline_component'
            / 'index.html'
        ).read_text(encoding='utf-8')

        self.assertIn('streamlit:componentReady', component)
        self.assertIn("event.data.type !== 'streamlit:render'", component)
        self.assertIn('document.write(args.document', component)

    def test_timeline_sends_clicked_case_to_streamlit(self):
        renderer = (
            Path(__file__).parents[1] / 'components' / 'dashboard_timeline.py'
        ).read_text(encoding='utf-8')

        self.assertIn('data-case-id=', renderer)
        self.assertIn("type:'streamlit:setComponentValue'", renderer)
        self.assertIn('value:Number(bar.dataset.caseId)', renderer)


if __name__ == '__main__':
    unittest.main()
