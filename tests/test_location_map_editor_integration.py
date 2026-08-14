import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nohtus import navigation
from nohtus.pages import location_map_editor
from nohtus.services import location_map_layout
from nohtus.services.location_map_layout_seed import initial_layout
from nohtus.services.location_map_new_layout import _NEW_CSS, _saved_layout_markup


class LocationMapEditorIntegrationTests(unittest.TestCase):
    def test_admin_menu_is_under_basic_section_and_shippable_menu_is_removed(self):
        basic = dict(navigation.MENU_SECTIONS)['기초']
        self.assertIn('로케이션맵 편집', basic)
        self.assertIn('로케이션맵 편집', navigation.ADMIN_ONLY_PAGES)
        self.assertNotIn('출고가능 관리', [label for _, labels in navigation.MENU_SECTIONS for label in labels])
        source = (Path(__file__).resolve().parents[1] / 'nohtus' / 'application.py').read_text(encoding='utf-8')
        self.assertIn('elif menu == "로케이션맵 편집":', source)
        self.assertIn('page_location_map_editor()', source)
        self.assertNotIn('page_shippable_inventory', source)
        self.assertNotIn('menu == "출고가능 관리"', source)

    def test_non_admin_cannot_see_or_directly_open_editor(self):
        with patch.object(navigation, 'is_admin', return_value=False):
            self.assertFalse(navigation._is_admin_only_allowed('로케이션맵 편집'))
        with (
            patch.object(location_map_editor, 'is_admin', return_value=False),
            patch.object(location_map_editor.st, 'warning') as warning,
            patch.object(location_map_editor.st, 'title') as title,
        ):
            location_map_editor.page_location_map_editor()
        warning.assert_called_once()
        title.assert_not_called()

    def test_seed_matches_latest_layout_and_c1_has_only_three_locations(self):
        layout = initial_layout()
        codes = {item['code'] for item in layout['items']}
        self.assertEqual(layout['canvas'], {'width': 1482, 'height': 910, 'grid': 10})
        self.assertEqual({code for code in codes if code.startswith('C1-')}, {'C1-01', 'C1-02', 'C1-03'})
        self.assertFalse({'C1-04', 'C1-05', 'C1-06'} & codes)

    def test_saved_json_generates_existing_click_targets_and_styles(self):
        layout = initial_layout()
        c1 = next(item for item in layout['items'] if item['code'] == 'C1-01')
        c1['x'] = 777
        markup = _saved_layout_markup(layout)
        self.assertIn('data-loc="C1-01"', markup)
        self.assertIn('left:777px', markup)
        self.assertIn('z-index:1', markup)
        self.assertIn('class="nw-zone zone farm"', markup)
        self.assertIn('.nw-zone.selected', _NEW_CSS)
        self.assertIn('.dynamic-stock-dot', _NEW_CSS)
        c1['rotation'] = 90
        rotated_markup = _saved_layout_markup(layout)
        self.assertIn('transform:rotate(-90deg)', rotated_markup)

    def test_layout_round_trip_keeps_rotation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / 'location_map_layout.json'
            with patch.object(location_map_layout, '_LAYOUT_PATH', path):
                layout = initial_layout()
                layout['items'][0]['rotation'] = 90
                layout['items'][0]['group_id'] = 'split-group-1'
                location_map_layout.save_location_map_layout(layout)
                restored = location_map_layout.load_location_map_layout()
        self.assertEqual(restored['items'][0]['rotation'], 90)
        self.assertEqual(restored['items'][0]['group_id'], 'split-group-1')

    def test_draft_layout_is_separate_and_can_be_deleted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            draft_path = Path(temp_dir) / 'location_map_layout.draft.json'
            with patch.object(location_map_layout, '_DRAFT_PATH', draft_path):
                layout = initial_layout()
                layout['items'][0]['x'] = 654
                location_map_layout.save_location_map_draft(layout)
                restored = location_map_layout.load_location_map_draft()
                self.assertEqual(restored['items'][0]['x'], 654)
                self.assertTrue(draft_path.exists())
                location_map_layout.delete_location_map_draft()
                self.assertIsNone(location_map_layout.load_location_map_draft())
                self.assertFalse(draft_path.exists())

    def test_decorative_shapes_are_saved_but_not_location_click_targets(self):
        layout = initial_layout()
        layout['items'].append({
            'code': '__shape-test',
            'label': '직선',
            'x': 10,
            'y': 20,
            'width': 240,
            'height': 30,
            'rotation': 35,
            'company': '기타',
            'kind': 'shape',
            'shape_type': 'line',
            'stroke': '#123456',
            'note': '',
        })
        markup = _saved_layout_markup(layout)
        self.assertIn('class="map-shape map-shape-line"', markup)
        self.assertIn('#123456', markup)
        self.assertNotIn('data-loc="__shape-test"', markup)

    def test_editor_supports_shape_transform_and_new_location_setup(self):
        with (
            patch.object(location_map_editor, 'is_admin', return_value=True),
            patch.object(location_map_editor, '_consume_save_payload', return_value=False),
            patch.object(location_map_editor, 'load_location_map_layout', return_value=initial_layout()),
            patch.object(location_map_editor.components, 'html') as rendered,
            patch.object(location_map_editor.st, 'title'),
            patch.object(location_map_editor.st, 'caption'),
        ):
            location_map_editor.page_location_map_editor()

        editor_html = rendered.call_args.args[0]
        self.assertIn('class="resize-handle', editor_html)
        self.assertIn('class="rotate-handle"', editor_html)
        self.assertIn('id="propCode"', editor_html)
        self.assertNotIn('id="propX"', editor_html)
        self.assertNotIn('id="propY"', editor_html)
        self.assertNotIn('id="propWidth"', editor_html)
        self.assertNotIn('id="propHeight"', editor_html)
        self.assertNotIn('id="propRotation"', editor_html)
        self.assertIn('id="newCode"', editor_html)
        self.assertIn('id="newKind"', editor_html)
        self.assertIn("isDuplicateCode(code)", editor_html)
        self.assertIn('id="splitSelected"', editor_html)
        self.assertIn('분할 후 칸 수', editor_html)
        self.assertIn('4 입력 → 분할선 3개, 결과 4칸', editor_html)
        self.assertIn('gap*(cellCount-1)', editor_html)
        self.assertIn('for(let i=0;i<cellCount;i++)', editor_html)
        self.assertIn('i===cellCount-1', editor_html)
        self.assertIn('id="duplicateSelected"', editor_html)
        self.assertIn('showSmartGuides', editor_html)
        self.assertIn('group_id', editor_html)
        self.assertIn('id="selectAll"', editor_html)
        self.assertIn('const selectedIndices=new Set()', editor_html)
        self.assertIn("action.members.forEach", editor_html)
        self.assertIn("showSmartGuides(it,action.idx)", editor_html)
        self.assertIn('data-tab="changeTab"', editor_html)
        self.assertIn('data-tab="newTab"', editor_html)
        self.assertIn('id="undo"', editor_html)
        self.assertIn('id="redo"', editor_html)
        self.assertIn('function checkpoint()', editor_html)
        self.assertIn('function deleteSelection(', editor_html)
        self.assertIn("e.key==='Delete'", editor_html)
        self.assertIn("e.key.toLowerCase()==='z'", editor_html)
        self.assertIn("e.key.toLowerCase()==='y'", editor_html)
        self.assertIn('className=\'selection-box\'', editor_html)
        self.assertIn("mode:'marquee'", editor_html)
        self.assertIn('it.x<right&&it.x+it.width>left', editor_html)
        self.assertIn('groupCx', editor_html)
        self.assertIn('groupCy', editor_html)
        self.assertIn('newCx=action.groupCx+dx*cos-dy*sin', editor_html)
        self.assertIn('newCy=action.groupCy+dx*sin+dy*cos', editor_html)
        self.assertIn('target.rotation=m.rotation+deltaRotation', editor_html)
        self.assertIn("label.style.transform=`rotate(${-Number(it.rotation||0)}deg)`", editor_html)
        self.assertIn('data-tab="shapeTab"', editor_html)
        self.assertIn('data-add-shape="rounded_rect"', editor_html)
        self.assertIn('data-add-shape="line"', editor_html)
        self.assertIn('data-add-shape="circle"', editor_html)
        self.assertIn('function addMapShape(', editor_html)
        self.assertIn("kind:'shape'", editor_html)
        self.assertIn('stage.style.zoom=String(scale)', editor_html)
        self.assertNotIn('stage.style.transform=`scale(', editor_html)
        self.assertIn('viewport.scrollLeft=0', editor_html)
        self.assertIn('viewport.scrollTop=0', editor_html)
        self.assertIn('id="saveDraft"', editor_html)
        self.assertIn('id="loadDraft"', editor_html)
        self.assertIn('id="deleteDraft"', editor_html)
        self.assertIn('localStorage.setItem(draftKey,snapshot())', editor_html)
        self.assertIn('localStorage.removeItem(draftKey)', editor_html)
        self.assertIn("draftKey='nohtus-location-map-editor-draft-v2'", editor_html)
        self.assertIn('실제 지도에는 반영되지 않습니다', editor_html)
        self.assertIn('function copySelection()', editor_html)
        self.assertIn('function pasteSelection()', editor_html)
        self.assertIn("key==='c'", editor_html)
        self.assertIn("key==='v'", editor_html)
        self.assertIn('itemClipboard.length', editor_html)
        self.assertIn('layout.canvas.width=Math.max(2000', editor_html)
        self.assertIn('resizeAngle=action.rotation*Math.PI/180', editor_html)
        self.assertIn('resizeDx=dx*cosResize+dy*sinResize', editor_html)
        self.assertIn('resizeDy=-dx*sinResize+dy*cosResize', editor_html)
        self.assertIn("action.width+resizeDx", editor_html)
        self.assertIn("action.height+resizeDy", editor_html)
        self.assertIn("shiftLocalX=dir.includes('e')?(w-action.width)/2", editor_html)
        self.assertIn("dir.includes('w')?(action.width-w)/2", editor_html)
        self.assertIn("shiftLocalY=dir.includes('s')?(h-action.height)/2", editor_html)
        self.assertIn("dir.includes('n')?(action.height-h)/2", editor_html)
        self.assertIn('shiftWorldX=shiftLocalX*cosResize-shiftLocalY*sinResize', editor_html)
        self.assertIn('startCenterX+shiftWorldX-w/2', editor_html)
        self.assertIn('function resizeCursor(dir,rotation)', editor_html)
        self.assertIn("['ew-resize','nwse-resize','ns-resize','nesw-resize'][bucket]", editor_html)
        self.assertIn('function applyHandleCursors(el,rotation)', editor_html)
        self.assertIn('id="bringToFront"', editor_html)
        self.assertIn('id="sendToBack"', editor_html)
        self.assertIn('function moveSelectionLayer(toFront)', editor_html)
        self.assertIn('toFront?[...remaining,...chosen]:[...chosen,...remaining]', editor_html)
        self.assertIn('document.elementsFromPoint(e.clientX,e.clientY)', editor_html)
        self.assertIn('if(e.altKey)', editor_html)
        self.assertIn('겹친 항목 중', editor_html)
        self.assertIn('applyHandleCursors(el,it.rotation)', editor_html)


if __name__ == '__main__':
    unittest.main()
