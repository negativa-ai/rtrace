from rtrace.postprocess import get_pid_tid, remove_duplicate_branch_taken


class TestRemoveDuplicateBranchTaken:
    def test_empty_list(self):
        assert remove_duplicate_branch_taken([]) == []

    def test_single_element(self):
        assert remove_duplicate_branch_taken([0x1]) == [0x1]

    def test_no_duplicates(self):
        assert remove_duplicate_branch_taken([0x1, 0x2, 0x3]) == [0x1, 0x2, 0x3]

    def test_consecutive_duplicates_removed(self):
        assert remove_duplicate_branch_taken([0x1, 0x2, 0x2, 0x3]) == [0x1, 0x2, 0x3]

    def test_runs_collapse_to_one(self):
        assert remove_duplicate_branch_taken([0x1, 0x1, 0x1, 0x2, 0x2]) == [0x1, 0x2]

    def test_non_consecutive_duplicates_preserved(self):
        assert remove_duplicate_branch_taken([0x1, 0x2, 0x1]) == [0x1, 0x2, 0x1]


class TestGetPidTid:
    def test_groups_tids_by_pid(self, tmp_path):
        for name in [
            "rtrace-intermediate-100-200-branch_taken.log",
            "rtrace-intermediate-100-200-loaded_modules.log",
            "rtrace-intermediate-100-201-branch_taken.log",
            "rtrace-intermediate-101-300-branch_taken.log",
        ]:
            (tmp_path / name).touch()

        pid_to_tids = get_pid_tid(str(tmp_path))

        assert sorted(pid_to_tids) == ["100", "101"]
        assert sorted(pid_to_tids["100"]) == ["200", "201"]
        assert pid_to_tids["101"] == ["300"]

    def test_ignores_unrelated_files(self, tmp_path):
        (tmp_path / "function-executed-100-200.json").touch()
        (tmp_path / "notes.txt").touch()

        assert get_pid_tid(str(tmp_path)) == {}

    def test_tid_not_duplicated_across_log_kinds(self, tmp_path):
        (tmp_path / "rtrace-intermediate-100-200-branch_taken.log").touch()
        (tmp_path / "rtrace-intermediate-100-200-func_args_ret.log").touch()

        assert get_pid_tid(str(tmp_path)) == {"100": ["200"]}
