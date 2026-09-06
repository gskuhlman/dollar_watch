from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests

from .evidence import classify_source, fetch_source_text

UA={"User-Agent":"dollar_watch/2.7 (+local research dashboard)"}

# Deterministic primary-source destinations. These do not assert that a claim is true;
# they put the analyst at the authoritative evidence surface first.
PRIMARY_ADAPTERS={
    'FX intervention':[
        ('US Treasury ESF','https://home.treasury.gov/policy-issues/international/exchange-stabilization-fund'),
        ('NY Fed FX operations','https://www.newyorkfed.org/markets/international-market-operations/foreign-exchange-operations'),
        ('Japan MOF intervention','https://www.mof.go.jp/english/policy/international_policy/reference/feio/index.htm'),
        ('Bank of Japan','https://www.boj.or.jp/en/'),
    ],
    'Treasury / Bessent':[
        ('Treasury press releases','https://home.treasury.gov/news/press-releases'),
        ('Treasury financing','https://home.treasury.gov/policy-issues/financing-the-government'),
        ('TreasuryDirect buyback results','https://www.treasurydirect.gov/auctions/announcements-data-results/buy-backs/'),
    ],
    'Fed / Warsh':[
        ('Federal Reserve speeches','https://www.federalreserve.gov/newsevents/speeches.htm'),
        ('Federal Reserve H.4.1','https://www.federalreserve.gov/releases/h41/'),
        ('Fed Monetary Policy Report','https://www.federalreserve.gov/monetarypolicy/mpr_default.htm'),
    ],
    'Funding stress':[
        ('NY Fed markets','https://www.newyorkfed.org/markets'),
        ('Federal Reserve H.4.1','https://www.federalreserve.gov/releases/h41/'),
        ('NY Fed reference rates','https://www.newyorkfed.org/markets/reference-rates'),
    ],
    'Central-bank gold':[
        ('World Gold Council CB data','https://www.gold.org/goldhub/data/gold-reserves-by-country'),
        ('DNB newsroom','https://www.dnb.nl/en/general-news/'),
        ('ECB reserves','https://www.ecb.europa.eu/'),
    ],
    'BRICS / de-dollarization':[
        ('BRICS official','https://brics.br/'),
        ('Reserve Bank of India','https://www.rbi.org.in/'),
    ],
    'China':[
        ('PBOC','http://www.pbc.gov.cn/en/3688006/index.html'),
        ('SAFE','https://www.safe.gov.cn/en/'),
    ],
    'Stablecoins':[
        ('US Treasury','https://home.treasury.gov/'),
        ('Federal Reserve','https://www.federalreserve.gov/'),
        ('SEC','https://www.sec.gov/'),
    ],
}

STOPWORDS={
    'the','a','an','and','or','to','of','in','on','for','with','from','by','is','are','was','were','be','been','being',
    'that','this','it','its','as','at','after','before','about','into','over','under','us','u','s','says','said','reportedly',
    'will','would','could','may','might','new','latest','more','less','than','amid','via','has','have','had'
}

BUCKET_ANCHORS={
    'FX intervention': {'intervention','exchange','currency','yen','dollar','foreign exchange','esf','fx'},
    'Treasury / Bessent': {'treasury','buyback','debt','financing','bessent','exchange','currency'},
    'Fed / Warsh': {'federal reserve','fed','warsh','monetary','rates','balance sheet','fomc'},
    'Funding stress': {'sofr','repo','fima','swap','liquidity','funding','dollar'},
    'Central-bank gold': {'gold','reserve','central bank','bullion','repatriation'},
    'BRICS / de-dollarization': {'brics','payment','settlement','local currency','dedollar','de-dollar','reserve'},
    'China': {'pboc','safe','yuan','renminbi','reserve','currency','china'},
    'Stablecoins': {'stablecoin','stablecoins','payment stablecoin','digital asset','digital dollar','genius act','usdc','usdt','usd1'},
}
MIN_RELEVANCE_SCORE=35.0

def _anchor_tokens(bucket:str)->set[str]:
    out=set()
    for phrase in BUCKET_ANCHORS.get(bucket,set()):
        out |= _tokens(phrase)
    return out

def source_relevance(bucket:str,claim:str,text:str,anchor:str='',url:str='')->dict:
    claim_tokens=_tokens(claim)
    content_tokens=_tokens((text or '')+' '+(anchor or '')+' '+(url or '').replace('/',' ').replace('-',' '))
    overlap=claim_tokens & content_tokens
    ratio=len(overlap)/max(1,len(claim_tokens))
    bucket_tokens=_anchor_tokens(bucket)
    bucket_hits=bucket_tokens & content_tokens
    anchor_score=_anchor_score(claim_tokens,anchor,url)
    score=min(100.0, 70.0*ratio + min(20.0,7.5*len(bucket_hits)) + min(15.0,2.0*anchor_score))
    # Official reachability is necessary but not sufficient. Require semantic overlap with
    # the actual claim plus at least one topic anchor for specialized policy buckets.
    if len(claim_tokens)<=3:
        relevant=bool(overlap) and (bool(bucket_hits) if bucket_tokens else True) and score>=MIN_RELEVANCE_SCORE
    else:
        relevant=((len(overlap)>=2 and ratio>=0.25) or (len(overlap)>=1 and ratio>=0.15 and len(bucket_hits)>=1))
        if bucket_tokens and not bucket_hits:
            relevant=False
        relevant=bool(relevant and score>=MIN_RELEVANCE_SCORE)
    return {
        'relevance_score':round(score,1),
        'relevance_status':'RELEVANT' if relevant else 'IRRELEVANT_SOURCE',
        'claim_token_overlap':len(overlap),
        'claim_overlap_ratio':round(ratio,3),
        'bucket_anchor_overlap':len(bucket_hits),
        'matched_claim_tokens':sorted(overlap)[:12],
        'matched_bucket_tokens':sorted(bucket_hits)[:12],
    }


def primary_source_candidates(bucket:str,claim:str='')->list[dict]:
    return [{'name':name,'url':url,'bucket':bucket,'claim':claim,'status':'PRIMARY_SOURCE_CANDIDATE'} for name,url in PRIMARY_ADAPTERS.get(bucket,[])]


def _tokens(text:str)->set[str]:
    words={w.lower() for w in re.findall(r"[A-Za-z0-9$%.-]{3,}",text or '')}
    return {w.strip('.-$%') for w in words if w.strip('.-$%') and w not in STOPWORDS}


def _same_host_family(a:str,b:str)->bool:
    ha=(urlparse(a).hostname or '').lower().removeprefix('www.')
    hb=(urlparse(b).hostname or '').lower().removeprefix('www.')
    return ha==hb or ha.endswith('.'+hb) or hb.endswith('.'+ha)


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self._href=None; self._parts=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()=='a':
            self._href=dict(attrs).get('href'); self._parts=[]
    def handle_data(self,data):
        if self._href is not None: self._parts.append(data)
    def handle_endtag(self,tag):
        if tag.lower()=='a' and self._href is not None:
            self.links.append((self._href,unescape(' '.join(self._parts)).strip()))
            self._href=None; self._parts=[]


def _anchor_score(claim_tokens:set[str],anchor:str,url:str)->float:
    hay=_tokens((anchor or '')+' '+(url or '').replace('/',' ').replace('-',' '))
    if not claim_tokens: return 0.0
    overlap=len(claim_tokens & hay)
    # Names, years and numbers tend to be especially discriminating in policy claims.
    numeric=sum(1 for t in claim_tokens & hay if any(ch.isdigit() for ch in t))
    return overlap + 1.5*numeric


def discover_primary_evidence(bucket:str,claim:str,timeout:int=10,max_candidates:int=8)->list[dict]:
    """Find likely primary-source pages for a queued claim.

    This is deterministic discovery, not factual verification. It starts from known official index pages,
    ranks same-domain links by lexical overlap, then fetches the strongest pages for a content-overlap score.
    """
    roots=primary_source_candidates(bucket,claim)
    claim_tokens=_tokens(claim)
    candidates=[]
    seen=set()
    for root in roots:
        base=root['url']
        # The base page itself is always a candidate.
        candidates.append({**root,'discovery':'adapter-root','anchor_score':0.0})
        seen.add(base)
        try:
            r=requests.get(base,headers=UA,timeout=timeout,allow_redirects=True)
            if not (200 <= r.status_code < 400):
                continue
            ctype=(r.headers.get('content-type') or '').lower()
            if 'html' not in ctype and '<html' not in r.text[:1000].lower():
                continue
            parser=_Links(); parser.feed(r.text)
            ranked=[]
            for href,anchor in parser.links:
                full=urljoin(r.url,href).split('#',1)[0]
                if not full.startswith(('http://','https://')) or not _same_host_family(full,r.url):
                    continue
                sc=_anchor_score(claim_tokens,anchor,full)
                if sc <= 0: continue
                ranked.append((sc,full,anchor))
            for sc,full,anchor in sorted(ranked,reverse=True)[:6]:
                if full in seen: continue
                seen.add(full)
                candidates.append({'name':root['name'],'url':full,'bucket':bucket,'claim':claim,'status':'PRIMARY_SOURCE_CANDIDATE','discovery':'same-domain-link','anchor':anchor,'anchor_score':sc})
        except Exception:
            continue

    # Fetch strongest candidates and measure claim/content overlap. Keep whole source pages out of the UI;
    # only a short excerpt is returned. The LLM verifier fetches the selected source again when requested.
    scored=[]
    for c in sorted(candidates,key=lambda x:x.get('anchor_score',0),reverse=True)[:max(12,max_candidates*2)]:
        fetched=fetch_source_text(c['url'],max_chars=18000,timeout=timeout)
        text=fetched.get('text','') if fetched.get('ok') else ''
        rel=source_relevance(bucket,claim,text,c.get('anchor',''),fetched.get('final_url',c['url']))
        excerpt=''
        if text:
            # Prefer a line containing one of the rarer claim tokens.
            lines=[x.strip() for x in text.splitlines() if x.strip()]
            hit=next((x for x in lines if len(_tokens(x)&claim_tokens)>=2),None)
            excerpt=(hit or '\n'.join(lines[:3]))[:700]
        scored.append({**c,'reachable':bool(fetched.get('ok')),'source_tier':fetched.get('source_tier',classify_source(c['url']).get('source_tier')),'final_url':fetched.get('final_url',c['url']),**rel,'excerpt':excerpt,'error':fetched.get('error','')})
    scored.sort(key=lambda x:(bool(x.get('reachable')),float(x.get('relevance_score') or 0)),reverse=True)
    return scored[:max_candidates]
