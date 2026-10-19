"""Reproducible local comparison of the fixed-pose sweep. No device control."""
from pathlib import Path
import csv, hashlib, json
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parent
FONT=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',20)
ROIS=dict(shadow=(240,415,260,470),neighbor=(320,415,345,470),bright_band=(350,100,1000,550))

def region(im, box):
    x0,y0,x1,y1=box
    return im[y0:y1,x0:x1]

def edge(im):
    line=cv2.GaussianBlur(im,(5,5),0)[420:465,235:360].mean(axis=0)
    low=float(np.median(line[:15])); high=float(np.median(line[-15:]))
    points=[]
    for fraction in [.1,.5,.9]:
        target=low+(high-low)*fraction
        candidates=np.flatnonzero((line[:-1]<target)&(line[1:]>=target))
        if not len(candidates): return None
        i=int(candidates[-1])
        points.append(235+i+(target-line[i])/(line[i+1]-line[i]))
    return dict(x50=float(points[1]),width10_90=float(points[2]-points[0]))

if __name__=='__main__':
    records=[]
    for folder in [ROOT,ROOT/'refine']:
        rows=[json.loads(s) for s in (folder/'captures.jsonl').read_text().splitlines()]
        assert len(rows)==(42 if folder==ROOT else 18)
        for row in rows:
            p=folder/row['file']; data=p.read_bytes()
            assert hashlib.sha256(data).hexdigest()==row['sha256']
            im=cv2.imdecode(np.frombuffer(data,np.uint8),0)
            assert im.shape==(1080,1280)
            a=float(region(im,ROIS['shadow']).mean()); b=float(region(im,ROIS['neighbor']).mean())
            records.append(dict(file=str(p.relative_to(ROOT)),level=row['brightness'],pass_name=row['pass_name'],
                shadow_mean=a,neighbor_mean=b,contrast=b-a,
                nearwhite_percent=float((region(im,ROIS['bright_band'])>=240).mean()*100),edge=edge(im)))
    summaries=[]
    for level in sorted({r['level'] for r in records}):
        group=[r for r in records if r['level']==level]
        assert len(group)==6
        row=dict(brightness=level,images=6)
        for name in ['shadow_mean','neighbor_mean','contrast','nearwhite_percent']:
            vals=[r[name] for r in group]
            row[name]=round(float(np.mean(vals)),3)
            row[name+'_sd']=round(float(np.std(vals)),3)
        xs=[r['edge']['x50'] for r in group if r['edge']]
        widths=[r['edge']['width10_90'] for r in group if r['edge']]
        row.update(edge_x50=round(float(np.mean(xs)),3),edge_x50_sd=round(float(np.std(xs)),3),
            edge_width_10_90=round(float(np.mean(widths)),3))
        summaries.append(row)
    report=dict(rois_xyxy=ROIS,metrics=summaries,images=records,
        limitation='Fixed pose, angle unverified; these intensity/edge metrics do not prove angle accuracy. >=240 is decoded near-white, not proof of sensor clipping.',
        recommended_range=[60,70],selected=65)
    (ROOT/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with (ROOT/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(summaries[0]));writer.writeheader();writer.writerows(summaries)
    levels=[40,55,60,65,70,75,100]
    sheet=Image.new('RGB',(7*360,2*390),(24,24,24));draw=ImageDraw.Draw(sheet)
    for col,level in enumerate(levels):
        source=ROOT/'refine' if level in (55,65,75) else ROOT
        for row,label in enumerate(['up','down']):
            p=source/f'{label}-{level:03d}-2.png'
            tile=Image.open(p).crop((130,280,580,700)).resize((360,336))
            sheet.paste(tile,(col*360,row*390+52))
            draw.text((col*360+10,row*390+4),f'{level}/100 '+('正向' if row==0 else '反向'),font=FONT,fill='white')
            contrast=next(r['contrast'] for r in summaries if r['brightness']==level)
            draw.text((col*360+10,row*390+27),f'明暗差 {contrast:.1f}',font=FONT,fill=(180,230,190))
    sheet.save(ROOT/'comparison-contact-sheet.png')
    preview=Image.new('RGB',(1350,470),(24,24,24));draw=ImageDraw.Draw(preview)
    for col,level in enumerate([40,65,100]):
        source=ROOT/'refine' if level==65 else ROOT
        tile=Image.open(source/f'up-{level:03d}-2.png').crop((130,280,580,700))
        preview.paste(tile,(col*450,50))
        label=f'背光 {level}/100'+('（建议起点）' if level==65 else '')
        draw.text((col*450+12,12),label,font=FONT,fill=(180,230,190) if level==65 else 'white')
    preview.save(ROOT/'40-65-100.png')
    sample=Image.open(ROOT/'refine/up-065-2.png').convert('RGB'); draw=ImageDraw.Draw(sample)
    for name,box in ROIS.items():
        color={'shadow':'red','neighbor':'lime','bright_band':'yellow'}[name]
        draw.rectangle(box,outline=color,width=3);draw.text((box[0],box[1]-25),name,font=FONT,fill=color)
    sample.save(ROOT/'measurement-regions.png')
    print(json.dumps(summaries,ensure_ascii=True,indent=2))
