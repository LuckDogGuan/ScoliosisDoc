"""Add individually readable, responsive figures to a frozen options report."""
import argparse
import json
from pathlib import Path
import numpy as np
from ruler_curve_options import METHODS, draw_curve, dump, font_manager, plt, sample_arrays, sha_bytes

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
root=args.output.resolve()
raw=json.loads((root/'raw.json').read_text(encoding='utf-8'))
saved={key:json.loads((root/f'beautified_{key}.json').read_text(encoding='utf-8')) for key in METHODS}
page=(root/'对照报告.html').read_text(encoding='utf-8')
font_manager.fontManager.addfont('C:/Windows/Fonts/msyh.ttc')
plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'svg.fonttype':'none'})
for capture in raw['captures']:
    rid=capture['metadata']['review_id']
    t,y,valid,outside=sample_arrays(capture['samples'])
    figures=[]
    for key in ['raw',*METHODS]:
        values=y if key=='raw' else np.array([row['angle_deg'] if row['angle_deg'] is not None else np.nan for row in saved[key]['samples'] if row['video_id']==rid])
        assert len(values)==len(t)
        title='原始数据' if key=='raw' else f'{key} · {METHODS[key]["name"]}'
        fig,ax=plt.subplots(figsize=(3.8,7.3),layout='constrained')
        draw_curve(ax,t,y,valid,values,key,title)
        fig.savefig(root/f'{rid}_{key}.svg');fig.savefig(root/f'{rid}_{key}.png',dpi=130)
        plt.close(fig)
        figures.append(f'<a class="figure" href="{rid}_{key}.png"><img src="{rid}_{key}.svg" alt="{rid} {title}"></a>')
    old=f'<a class="figure" href="{rid}.png"><img src="{rid}.svg" alt="{rid} 原始与三种美化曲线对照"></a>'
    assert old in page,'Responsive rendering was already applied, or source report changed'
    page=page.replace(old,'<div class="plots">'+''.join(figures)+'</div>')
page=page.replace('</style>','.plots{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}@media(max-width:1100px){.plots{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){.plots{grid-template-columns:1fr}}</style>')
(root/'对照报告.html').write_text(page,encoding='utf-8')
summary=json.loads((root/'summary.json').read_text(encoding='utf-8'))
summary['responsive_figures']=dict(script_sha256=sha_bytes(Path(__file__).read_bytes()),panels=20,uses_saved_beautified_values=True)
dump(root/'summary.json',summary)
dump(root/'file-hashes.json',{str(p.relative_to(root)):sha_bytes(p.read_bytes()) for p in sorted(root.iterdir()) if p.is_file() and p.name!='file-hashes.json'})
print(json.dumps({'responsive_panels':20,'source_database_opened':False}))
