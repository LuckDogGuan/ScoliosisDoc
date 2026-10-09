"""Read native exports; compare complete sets and unchanged sample values."""
from pathlib import Path
from collections import Counter
import hashlib, json, openpyxl

root = Path(__file__).parent
load = lambda name: openpyxl.load_workbook(root / name, data_only=True)
roster = load('roster-female-view-both-333.xlsx')
before = load('roster-school-all.xlsx')
members = lambda book: [tuple(row) for sheet in book if sheet.title != '汇总'
                       for row in sheet.iter_rows(min_row=2, values_only=True) if row[1] is not None]
assert members(roster) == members(before)
sex_counts = Counter(row[3] for row in members(roster))
assert sex_counts == {'男': 18, '女': 18}
assert len(roster.sheetnames) == 19

records = load('records-female-view-both-333.xlsx')
old = load('records-all.xlsx')
summary = list(records['拍摄汇总'].iter_rows(min_row=4, values_only=True))
original = list(old['拍摄汇总'].iter_rows(min_row=4, values_only=True))
assert {r[8] for r in summary} == {r[8] for r in original}
assert len(summary) == 17
counts = Counter(r[12] for r in summary)
assert counts == {'男': 10, '女': 7}
assert [r[12] for r in summary] == ['男'] * 10 + ['女'] * 7
for gender in ['男', '女']:
    times = [r[6] for r in summary if r[12] == gender]
    assert times == sorted(times, reverse=True)
detail = list(records['角度明细'].iter_rows(min_row=2, values_only=True))
old_detail = list(old['角度明细'].iter_rows(min_row=2, values_only=True))
assert len(detail) == 749
key = lambda row: (row[1], row[4], row[5])
old_map = {key(row): row for row in old_detail}
summary_map = {r[8]: r for r in summary}
for row in detail:
    previous = old_map[key(row)]
    assert row[1:7] == previous[1:7]
    assert row[8:10] == previous[8:10]
    assert row[7].startswith('历史测试图（非实测）')
    parent = summary_map[row[1]]
    assert row[0] == parent[0] and row[10] == parent[12]
assert all(r[10] == '历史测试图（非实测）' and r[11] is None for r in summary)
report = {'version': '3.3.3', 'native_ui_export': True,
    'screen_gender_filter': 'female', 'screen_filter_unchanged': True,
    'roster': {'count': 36, 'sex_counts': dict(sex_counts), 'sheets': 19,
               'identical_to_prior_all_gender_export': True},
    'records': {'count': 17, 'sex_counts': dict(counts), 'samples': 749,
                'all_ids_match_prior_database_verified_export': True,
                'grouped_male_then_female': True, 'time_descending_within_gender': True,
                'sample_values_and_associations_match': True, 'legacy_explicitly_labeled': True},
    'files': {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in
              ['roster-female-view-both-333.xlsx', 'records-female-view-both-333.xlsx']},
    'excel_wps_opening': 'pending'}
(root / 'gender-export-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=True))
