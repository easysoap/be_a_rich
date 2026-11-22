"""Public regional trade feed. Reads its API key only from GitHub Secrets."""
import datetime as dt
import json
import os
from pathlib import Path
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

API = 'https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade'

def parse(xml):
    root = ET.fromstring(xml)
    if (root.findtext('.//resultCode') or '').strip() not in {'0','00','000'}:
        raise ValueError('Public data authorization or upstream error')
    total = int(root.findtext('.//totalCount') or '0')
    rows = []
    for item in root.findall('.//item'):
        text = lambda name: (item.findtext(name) or '').strip()
        day = dt.date(int(text('dealYear')), int(text('dealMonth')), int(text('dealDay'))).isoformat()
        price = int(text('dealAmount').replace(',', '')) * 10000
        area = float(text('excluUseAr'))
        if price <= 0 or area <= 0 or not text('aptNm') or not text('umdNm'):
            raise ValueError('Invalid trade row')
        rows.append(dict(id='|'.join([text('aptNm'),text('umdNm'),text('jibun'),str(area),day,str(price),text('floor')]), name=text('aptNm'), dong=text('umdNm'), jibun=text('jibun'), area=area, date=day, price=price, floor=text('floor'), cancelled=text('cdealType') in {'O','Y'} or bool(text('cdealDay'))))
    return total, rows

def update():
    key, region = os.environ.get('MOLIT_SERVICE_KEY',''), os.environ.get('MOLIT_LAWD_CD','')
    if not key or not re.fullmatch(r'\d{5}', region):
        raise ValueError('Configure MOLIT_SERVICE_KEY and MOLIT_LAWD_CD in GitHub Secrets')
    # Accept either key format from the portal without double percent-encoding.
    if '%' in key:
        key = urllib.parse.unquote(key)
    now = dt.datetime.now(ZoneInfo('Asia/Seoul'))
    rows = []
    for offset in range(6):
        index = now.year * 12 + now.month - 1 - offset
        year, month = divmod(index, 12)
        for page in range(1, 6):
            query = urllib.parse.urlencode(dict(serviceKey=key, LAWD_CD=region, DEAL_YMD=f'{year:04}{month+1:02}', pageNo=page, numOfRows=1000))
            try:
                with urllib.request.urlopen(API+'?'+query, timeout=25) as response:
                    total, received = parse(response.read())
            except Exception:
                # Do not expose request URLs or API keys in a public Actions log.
                raise RuntimeError('Official trade feed failed; no replacement was published') from None
            rows.extend(received)
            if total <= page*1000:
                break
            if page == 5:
                raise RuntimeError('Trade feed is incomplete; previous deployment must be retained')
    output = dict(schema=1, complete=True, region=region, source='국토교통부 아파트 매매 실거래가', fetchedAt=now.isoformat(), records=rows)
    stage = Path('_property_site')
    stage.mkdir(exist_ok=True)
    (stage/'index.html').write_bytes(Path('index.html').read_bytes())
    (stage/'property-market.json').write_text(json.dumps(output, ensure_ascii=False, separators=(',',':')))
    print(f'Prepared {len(rows)} public regional trade rows. Personal financial JSON is excluded.')

if __name__ == '__main__':
    update()
