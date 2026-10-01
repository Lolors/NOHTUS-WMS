from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from nohtus.export_app.services import folder_service, folder_sync_service as batch


def case(id=1, **values):
    return dict(id=id, export_no=f"EXP-{id}", status="진행중", stage="출고 대기",
                created_at="2026-01-01", actual_ship_date="", updated_at="2026-09-17", **values)


class FolderBatchTests(unittest.TestCase):
    def test_recent_includes_old_cases_updated_recently_and_boundary(self):
        cases=[case(1),case(2),case(3),case(4)]
        cases[1]["updated_at"]="2026-09-04"
        cases[2]["updated_at"]="2026-09-03"
        cases[3]["status"]="취소"
        self.assertEqual([c["id"] for c in batch.select_cases(cases,14,date(2026,9,17))],[1,2])
        self.assertEqual([c["id"] for c in batch.select_cases(cases)],[1,2,3])

    def test_new_and_changed_collected_but_unchanged_skipped(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            folders={1:root/"러시아"/"2026"/"09월"/"[세나] 제품",2:root/"조지아"/"2026"/"09월"/"[세나] 제품"}
            def sync(id):
                if id == 3:
                    return root/"unchanged", False
                folder=folders[id];folder.mkdir(parents=True,exist_ok=True)
                (folder/"수출진행내역.xlsx").write_text("regenerated",encoding="utf-8")
                (folder/"사진.jpg").write_bytes(b"user photo")
                return folder, True
            with patch.object(folder_service,"storage_root",return_value=root),patch.object(folder_service,"sync_case_folder_if_changed",side_effect=sync) as writer:
                result=batch.rebuild_batch([case(1),case(2),case(3)])
            self.assertEqual(writer.call_count,3)
            self.assertEqual(result["skipped"],["EXP-3"])
            self.assertEqual(len(result["gathered"]),2)
            for folder in folders.values():
                copy=result["root"]/folder.relative_to(root)
                self.assertEqual((copy/"사진.jpg").read_bytes(),b"user photo")
                self.assertEqual((copy/"수출진행내역.xlsx").read_text(),"regenerated")

    def test_copy_failure_is_reported_without_claiming_collected(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/"case";folder.mkdir()
            with patch.object(folder_service,"storage_root",return_value=root),patch.object(folder_service,"sync_case_folder_if_changed",return_value=(folder,True)),patch.object(batch.shutil,"copytree",side_effect=PermissionError("locked")):
                result=batch.rebuild_batch([case()])
            self.assertEqual(result["rebuilt"],["EXP-1"])
            self.assertEqual(result["gathered"],[])
            self.assertEqual(len(result["copy_failures"]),1)

    def test_empty_does_not_create_batch(self):
        with patch.object(folder_service,"storage_root") as storage:
            self.assertIsNone(batch.rebuild_batch([])["root"])
            storage.assert_not_called()

    def test_folder_discovery_never_uses_collected_copy_as_original(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);collected=root/"갱신폴더_20260917"/"case";original=root/"조지아"/"case"
            for folder in [collected,original]:
                folder.mkdir(parents=True)
                (folder/folder_service.CASE_MARKER_NAME).write_text('{"case_id":1}')
            with patch.object(folder_service.db,"row",return_value={"folder_path":str(collected)}),patch.object(folder_service,"resolve_database_path",return_value=collected),patch.object(folder_service,"storage_root",return_value=root):
                self.assertEqual(folder_service.find_case_folder(1),original)

    def test_all_unchanged_creates_no_batch_and_reports_progress(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);events=[]
            with patch.object(folder_service,"storage_root",return_value=root),patch.object(folder_service,"sync_case_folder_if_changed",return_value=(root,False)),patch.object(batch.shutil,"copytree") as copy:
                result=batch.rebuild_batch([case(1),case(2)],progress=lambda i,total:events.append((i,total)))
            self.assertIsNone(result["root"])
            self.assertEqual(result["skipped"],["EXP-1","EXP-2"])
            self.assertEqual(events,[(1,2),(2,2)])
            copy.assert_not_called()
            self.assertEqual(list(root.iterdir()),[])
