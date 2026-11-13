"""Radio station logos from Wikipedia/Wikimedia Commons -> frontend/public/radio-logos/<key>.png.

Usage: python3 scripts/fetch_radio_logos.py frontend/public/radio-logos   (needs Pillow; see docs/radio_logos.md)
"""
import json,urllib.request,urllib.parse,io,sys,os
from PIL import Image
UA='muzplayer-logo-fetch/0.1 (self-hosted music player; https://github.com/zardkim/muzplayer)'
FILES={
 'kbs-1radio':'KBS Radio 1 logo.svg','kbs-2fm':'KBS2FM logo.svg','kbs':'KBS logo (2001).svg',
 'mbc-sfm':'MBC Standard FM Logo.svg','mbc-fm4u':'MBC FM4U Logo.svg','mbc':'MBC Radio 2018.svg',
 'sbs-power':'SBS Power FM Logo.svg','sbs-love':'SBS Love FM Logo.svg','sbs':'Seoul Broadcasting System logo.svg',
 'ebs':'EBS Logo.svg','obs':'OBS Kyung-In TV 2023.png','ifm':'ITV LOGO.svg','ytn':'YTN logo 2014.svg',
 'tbs':'Traffic Broadcasting System logo.png','cbs':'Christian Broadcasting System logo.svg',
 'febc':'Febc logov2.gif','bbs':'Buddhist Broadcasting System logo.png','cpbc':'CPBC logo.png',
 'afn':'American Forces Network logo.png','arirang':'Arirang.svg','knn':'KNN logo.svg','ubc':'UBC 울산방송.svg',
 'tbc':'Daegu Broadcasting Corporation.svg','kbc':'Kbc logo2.svg','jtv':'JTV로고1.gif','tjb':'Tjb logo.svg',
 'cjb':'Cjb logo.svg','g1':'G1 broadcasting logo.svg',
}
out=sys.argv[1]; os.makedirs(out,exist_ok=True)
q=dict(action='query',prop='imageinfo',iiprop='url|extmetadata',iiurlwidth=512,format='json',formatversion=2,titles='|'.join('File:'+f for f in FILES.values()))
d=json.load(urllib.request.urlopen(urllib.request.Request('https://ko.wikipedia.org/w/api.php?'+urllib.parse.urlencode(q),headers={'User-Agent':UA})))
norm={n['from']:n['to'] for n in d['query'].get('normalized',[])}
pages={p['title']:p for p in d['query']['pages']}
src={}
for key,f in FILES.items():
    t=norm.get('File:'+f,'File:'+f); p=pages.get(t)
    if not p or 'imageinfo' not in p: print('MISSING',key,f); continue
    ii=p['imageinfo'][0]; url=ii.get('thumburl') or ii['url']
    raw=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':UA})).read()
    im=Image.open(io.BytesIO(raw)); im.seek(0); im=im.convert('RGBA')
    bb=im.getbbox()
    if bb: im=im.crop(bb)
    # a 3:2 tile (the logos are mostly wide wordmarks), a little air around
    k=min(264/im.width, 160/im.height)
    im=im.resize((max(1,round(im.width*k)),max(1,round(im.height*k))),Image.LANCZOS)
    canvas=Image.new('RGB',(288,192),'white'); canvas.paste(im,((288-im.width)//2,(192-im.height)//2),im)
    canvas.save(f'{out}/{key}.png',optimize=True)
    lic=(ii.get('extmetadata',{}).get('LicenseShortName') or {}).get('value','?')
    src[key]={'file':t,'page':ii.get('descriptionurl'),'license':lic}
    print(key,lic,os.path.getsize(f'{out}/{key}.png'))
print(json.dumps(src,ensure_ascii=False,indent=1))  # for the sources table in docs/radio_logos.md
