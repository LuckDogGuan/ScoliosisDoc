"""Independently read the production export's native charts and numeric ranges."""
from pathlib import Path
import hashlib, json, shutil, zipfile
import openpyxl

root = Path(__file__).parent
source = Path('D:/code/Scoliosis/ScoliosisFlutter/build/school-curve-export-fixture.xlsx')
example = root / '学校汇总与曲线_匿名示例.xlsx'
shutil.copyfile(source, example)
book = openpyxl.load_workbook(example, data_only=True)
assert book.sheetnames == ['导出汇总', '拍摄汇总', '角度明细', '尺读数曲线', '曲线数据']
assert list(book['导出汇总'].values)[3][3:] == (3, 1, 2, 0, 4)
summary = list(book['拍摄汇总'].values)[3:]
assert [r[8] for r in summary] == ['f', 'f-repeat', 'm', 'g2']
assert all(r[11] == 7 for r in summary)
curves = book['尺读数曲线']._charts
assert len(curves) == 4
for curve in curves:
    assert curve.scatterStyle == 'lineMarker' and curve.display_blanks == 'gap'
    assert len(curve.series) == 1 and curve.series[0].smooth is False
    series = curve.series[0]
    assert [p.idx for p in series.yVal.numRef.numCache.pt] == [0, 1, 3, 4]
    assert [p.v for p in series.yVal.numRef.numCache.pt] == [-7, 1, 3, 4]
    assert series.xVal.numRef.f.startswith("'曲线数据'!$C$")
    assert series.yVal.numRef.f.startswith("'曲线数据'!$D$")
with zipfile.ZipFile(example) as bundle:
    assert bundle.testzip() is None
    assert not any(name.startswith('xl/media/') for name in bundle.namelist())
report = {'synthetic_example': True, 'production_exporter': True,
    'students': 3, 'male': 1, 'female': 2, 'records': 4,
    'native_charts': 4, 'series_per_record': 1, 'individual_frame_images': 0,
    'summary_details_curves_order_match': True, 'signed_values_and_missing_gaps': True,
    'maximum_absolute_reading': 7, 'independent_openpyxl_check': 'passed',
    'excel_wps_native_opening': 'pending', 'sha256': hashlib.sha256(example.read_bytes()).hexdigest()}
(root / 'example-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=True))
