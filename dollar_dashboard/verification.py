from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests
import pandas as pd

from .evidence import classify_source, fetch_source_text

UA={"User-Agent":"dollar_watch/3.0 (+local research dashboard)"}

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
    'Administration / White House':[
        ('White House remarks','https://www.whitehouse.gov/remarks/'),
        ('White House presidential actions','https://www.whitehouse.gov/presidential-actions/'),
        ('US Treasury press releases','https://home.treasury.gov/news/press-releases'),
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
    'Administration / White House': {'white house','president','administration','dollar','currency','rates','tariff','reserve currency','miran','trump'},
}
MIN_RELEVANCE_SCORE=35.0
# High-specificity buckets require at least one discriminating topic token.  Generic
# words such as "dollar" or "reserve" are not sufficient; this prevents a sanctions
# press release that merely mentions dollar access from verifying a stablecoin claim.
# V3.0 route-aware retrieval: prefer policy/news/speech surfaces and reject generic
# privacy/help/assistance/navigation pages before semantic ranking.
ROUTE_RULES={
    'Treasury / Bessent': {
        'prefer':('/news/press-releases','/news/press-releases/statements-remarks','/policy-issues/financing-the-government'),
        'block':('/privacy','/financial-assistance','/services','/foia','/contact','/about'),
    },
    'Administration / White House': {
        'prefer':('/remarks/','/presidential-actions/','/briefings-statements/'),
        'block':('/privacy','/contact','/accessibility'),
    },
    'FX intervention': {
        'prefer':('/policy-issues/international','/markets/international-market-operations','/policy/international_policy','/news/press-releases'),
        'block':('/privacy','/contact'),
    },
    'Fed / Warsh': {
        'prefer':('/newsevents/speeches','/newsevents/pressreleases','/monetarypolicy','/releases/h41'),
        'block':('/privacy','/foia','/aboutthefed'),
    },
    'Funding stress': {
        'prefer':('/markets','/releases/h41','/newsevents'),
        'block':('/privacy','/careers'),
    },
    'Stablecoins': {
        'prefer':('/news/press-releases','/newsevents/pressreleases','/rules-regulations'),
        'block':('/privacy','/sanctions','/financial-assistance'),
    },
}

def _route_score(bucket:str,url:str)->tuple[bool,float,str]:
    path=(urlparse(url).path or '/').lower()
    rules=ROUTE_RULES.get(bucket,{})
    for bad in rules.get('block',()):
        if bad in path:
            return False,-100.0,f'blocked-route:{bad}'
    bonus=0.0; reason='generic-official-route'
    for good in rules.get('prefer',()):
        if good in path:
            bonus=max(bonus,25.0); reason=f'preferred-route:{good}'
    return True,bonus,reason

HARD_BUCKET_ANCHORS={
    'Stablecoins': {'stablecoin','stablecoins','usdc','usdt','usd1','genius'},
    'Central-bank gold': {'gold','bullion','repatriation'},
    'BRICS / de-dollarization': {'brics','dedollar','de-dollar'},
    'FX intervention': {'intervention','esf','fx'},
}

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
        hard=HARD_BUCKET_ANCHORS.get(bucket,set())
        if hard and not (hard & content_tokens):
            relevant=False
        relevant=bool(relevant and score>=MIN_RELEVANCE_SCORE)
    if len(claim_tokens)<=3:
        hard=HARD_BUCKET_ANCHORS.get(bucket,set())
        if hard and not (hard & content_tokens):
            relevant=False
    return {
        'relevance_score':round(score,1),
        'relevance_status':'RELEVANT' if relevant else 'IRRELEVANT_SOURCE',
        'claim_token_overlap':len(overlap),
        'claim_overlap_ratio':round(ratio,3),
        'bucket_anchor_overlap':len(bucket_hits),
        'matched_claim_tokens':sorted(overlap)[:12],
        'matched_bucket_tokens':sorted(bucket_hits)[:12],
    }




NEWS_BUCKET_MAP={
    'US policy':'Treasury / Bessent',
    'Fed':'Fed / Warsh',
    'Trump':'Administration / White House',
    'Miran':'Administration / White House',
    'Treasury market':'Treasury / Bessent',
    'BRICS':'BRICS / de-dollarization',
    'China':'China',
    'Japan':'FX intervention',
    'Gold reserves':'Central-bank gold',
    'Funding stress':'Funding stress',
    'Stablecoins':'Stablecoins',
    'Commodity settlement':'BRICS / de-dollarization',
    'Institutional risk':'Fed / Warsh',
}

def verification_bucket_for_news(bucket:str, claim:str='')->str:
    """Map broad discovery buckets onto primary-source verification families.

    V2.8 left Google-News buckets such as ``US policy`` and ``Japan`` unchanged, which meant
    they had no PRIMARY_ADAPTERS entry and silently fell out of P0/P1 automatic verification.
    """
    b=str(bucket or '').strip()
    text=(claim or '').lower()
    if b=='US policy' and any(k in text for k in ['intervention','exchange stabilization','yen','foreign exchange']):
        return 'FX intervention'
    return NEWS_BUCKET_MAP.get(b,b)

SYSTEMATIC_POLICY_PROBES=[
    {"priority":"P0","bucket":"Treasury / Bessent","claim":"Treasury publicly advocates broad depreciation of the U.S. dollar as a policy objective.","source":"SYSTEMATIC POLICY PROBE","link":"https://home.treasury.gov/news/press-releases","effect_target":"managed_devaluation","effect_direction":1,"effect_weight":10.0},
    {"priority":"P0","bucket":"Treasury / Bessent","claim":"Treasury publicly supports a strong or broadly stable U.S. dollar rather than deliberate broad depreciation.","source":"SYSTEMATIC POLICY PROBE","link":"https://home.treasury.gov/news/press-releases","effect_target":"managed_devaluation","effect_direction":-1,"effect_weight":8.0},
    {"priority":"P0","bucket":"Administration / White House","claim":"The White House publicly advocates deliberate broad U.S.-dollar depreciation or explicitly uses interest-rate policy to weaken the dollar.","source":"SYSTEMATIC POLICY PROBE","link":"https://www.whitehouse.gov/remarks/","effect_target":"managed_devaluation","effect_direction":1,"effect_weight":10.0},
    {"priority":"P0","bucket":"FX intervention","claim":"U.S. or Japanese officials publicly signal active or imminent foreign-exchange intervention affecting the dollar-yen rate.","source":"SYSTEMATIC POLICY PROBE","link":"https://home.treasury.gov/news/press-releases","effect_target":"managed_devaluation","effect_direction":1,"effect_weight":7.0},
    {"priority":"P0","bucket":"Funding stress","claim":"Federal Reserve or New York Fed communications report material U.S.-dollar funding-market stress or exceptional dollar-liquidity support.","source":"SYSTEMATIC POLICY PROBE","link":"https://www.newyorkfed.org/markets","effect_target":"dollar_funding_squeeze","effect_direction":1,"effect_weight":8.0},
    {"priority":"P0","bucket":"Fed / Warsh","claim":"Official communications document political pressure on Federal Reserve independence for currency or interest-rate objectives.","source":"SYSTEMATIC POLICY PROBE","link":"https://www.federalreserve.gov/newsevents/speeches.htm","effect_target":"managed_devaluation","effect_direction":1,"effect_weight":6.0},
    {"priority":"P1","bucket":"BRICS / de-dollarization","claim":"Official BRICS communications report concrete implementation of non-dollar settlement or payment infrastructure.","source":"SYSTEMATIC POLICY PROBE","link":"https://brics.br/","effect_target":"reserve_confidence","effect_direction":1,"effect_weight":6.0},
    {"priority":"P1","bucket":"China","claim":"PBOC or SAFE communications explicitly describe reducing U.S.-dollar reserve exposure as a policy objective.","source":"SYSTEMATIC POLICY PROBE","link":"https://www.safe.gov.cn/en/","effect_target":"reserve_confidence","effect_direction":1,"effect_weight":6.0},
    {"priority":"P1","bucket":"Central-bank gold","claim":"Official central-bank communications report material additions to monetary gold reserves.","source":"SYSTEMATIC POLICY PROBE","link":"https://www.gold.org/goldhub/data/gold-reserves-by-country","effect_target":"reserve_confidence","effect_direction":1,"effect_weight":5.0},
    {"priority":"P1","bucket":"Stablecoins","claim":"Treasury publicly frames payment-stablecoin policy as strengthening the U.S. dollar's international or reserve-currency role.","source":"SYSTEMATIC POLICY PROBE","link":"https://home.treasury.gov/news/press-releases","effect_target":"structural_dollar_support","effect_direction":1,"effect_weight":6.0},
    {"priority":"P1","bucket":"Treasury / Bessent","claim":"Treasury announces changes to nominal long-end buyback capacity or debt-management liquidity support.","source":"SYSTEMATIC POLICY PROBE","link":"https://home.treasury.gov/news/press-releases","effect_target":"fiscal_treasury","effect_direction":0,"effect_weight":4.0},
]
def systematic_policy_leads(max_rows:int=8)->list[dict]:
    """Return bounded standing research probes so the verification queue cannot go dark when news RSS fails.

    These are propositions to test, not facts.  They enter the same primary-source relevance and
    human-approval pipeline as headline-derived claims and remain non-scoring until approved/promoted.
    """
    out=[]
    for r in SYSTEMATIC_POLICY_PROBES[:max(0,int(max_rows))]:
        bucket=r['bucket']; claim=r['claim']; link=r['link']
        out.append({
            **r,
            'published':'standing probe',
            'source_tier':classify_source(link).get('source_tier','PRIMARY'),
            'preferred_verification_source':'; '.join(x['url'] for x in primary_source_candidates(bucket,claim)),
            'verification_status':'UNVERIFIED',
            'integrity_status':'COMPLETE',
            'probe_kind':'SYSTEMATIC_POLICY_PROBE',
        })
    return out

def primary_source_candidates(bucket:str,claim:str='')->list[dict]:
    out=[]
    for name,url in PRIMARY_ADAPTERS.get(bucket,[]):
        allowed,bonus,reason=_route_score(bucket,url)
        if allowed:
            out.append({'name':name,'url':url,'bucket':bucket,'claim':claim,'status':'PRIMARY_SOURCE_CANDIDATE','route_bonus':bonus,'route_reason':reason})
    return out


VERIFICATION_PRIORITY={
    'FX intervention':'P0','Treasury / Bessent':'P0','Fed / Warsh':'P0','Funding stress':'P0','Administration / White House':'P0',
    'BRICS / de-dollarization':'P1','China':'P1','Central-bank gold':'P1','Stablecoins':'P1',
}

def verification_rows_from_news(news_df: pd.DataFrame, max_rows:int=30)->list[dict]:
    """Convert discovery headlines into complete, primary-source-routable research rows.

    This pure helper is shared by Streamlit and the headless collector.  Broad RSS buckets are
    normalized to verification families before priority/adapters are assigned, fixing the V2.8
    failure mode where ``US policy``/``Japan``/``BRICS`` headlines silently became P2 with no
    primary-source candidates.
    """
    if news_df is None or news_df.empty:
        return []
    rows=[]
    for _,r in news_df.head(max_rows).iterrows():
        claim=str(r.get('title') or '').strip()
        source=str(r.get('source') or '').strip()
        link=str(r.get('link') or '').strip()
        raw_bucket=str(r.get('bucket') or '').strip()
        if len(claim)<10 or not source or not link.startswith(('http://','https://')):
            continue
        bucket=verification_bucket_for_news(raw_bucket,claim)
        candidates=primary_source_candidates(bucket,claim)
        rows.append({
            'priority':VERIFICATION_PRIORITY.get(bucket,'P2'),
            'bucket':bucket,
            'discovery_bucket':raw_bucket,
            'claim':claim,
            'source':source,
            'published':r.get('published',''),
            'source_tier':classify_source(link).get('source_tier','UNSOURCED'),
            'preferred_verification_source':'; '.join(x['url'] for x in candidates) or 'primary government/central-bank source if available',
            'verification_status':'UNVERIFIED',
            'integrity_status':'COMPLETE',
            'primary_source_candidates':'; '.join(x['url'] for x in candidates),
            'link':link,
            'effect_target':'', 'effect_direction':0, 'effect_weight':0.0,
        })
    return sorted(rows,key=lambda x:(x.get('priority','P9'),str(x.get('published',''))),reverse=False)


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
        candidates.append({**root,'discovery':'adapter-root','anchor_score':float(root.get('route_bonus',0.0))})
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
                allowed,route_bonus,route_reason=_route_score(bucket,full)
                if not allowed: continue
                sc=_anchor_score(claim_tokens,anchor,full) + route_bonus
                if sc <= 0: continue
                ranked.append((sc,full,anchor,route_reason,route_bonus))
            for sc,full,anchor,route_reason,route_bonus in sorted(ranked,reverse=True)[:10]:
                if full in seen: continue
                seen.add(full)
                candidates.append({'name':root['name'],'url':full,'bucket':bucket,'claim':claim,'status':'PRIMARY_SOURCE_CANDIDATE','discovery':'same-domain-link','anchor':anchor,'anchor_score':sc,'route_bonus':route_bonus,'route_reason':route_reason})
        except Exception:
            continue

    # Fetch strongest candidates and measure claim/content overlap. Keep whole source pages out of the UI;
    # only a short excerpt is returned. The LLM verifier fetches the selected source again when requested.
    scored=[]
    for c in sorted(candidates,key=lambda x:x.get('anchor_score',0),reverse=True)[:max(12,max_candidates*2)]:
        fetched=fetch_source_text(c['url'],max_chars=18000,timeout=timeout)
        text=fetched.get('text','') if fetched.get('ok') else ''
        final_url=fetched.get('final_url',c['url'])
        allowed,route_bonus,route_reason=_route_score(bucket,final_url)
        rel=source_relevance(bucket,claim,text,c.get('anchor',''),final_url)
        rel['relevance_score']=round(min(100.0,max(0.0,float(rel.get('relevance_score') or 0)+route_bonus)),1)
        if not allowed:
            rel['relevance_status']='IRRELEVANT_SOURCE'
        c['route_bonus']=route_bonus; c['route_reason']=route_reason
        excerpt=''
        if text:
            # Prefer a line containing one of the rarer claim tokens.
            lines=[x.strip() for x in text.splitlines() if x.strip()]
            hit=next((x for x in lines if len(_tokens(x)&claim_tokens)>=2),None)
            excerpt=(hit or '\n'.join(lines[:3]))[:700]
        scored.append({**c,'reachable':bool(fetched.get('ok')),'source_tier':fetched.get('source_tier',classify_source(c['url']).get('source_tier')),'final_url':fetched.get('final_url',c['url']),**rel,'excerpt':excerpt,'error':fetched.get('error','')})
    scored.sort(key=lambda x:(bool(x.get('reachable')),float(x.get('relevance_score') or 0)),reverse=True)
    return scored[:max_candidates]
