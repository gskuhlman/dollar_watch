from __future__ import annotations

from urllib.parse import quote_plus

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
        ('Fed Monetary Policy Report','https://www.federalreserve.gov/monetarypolicy/mpr_default.htm'),
    ],
    'Central-bank gold':[
        ('World Gold Council CB data','https://www.gold.org/goldhub/data/gold-reserves-by-country'),
        ('DNB gold reserves','https://www.dnb.nl/en/'),
        ('DNB newsroom','https://www.dnb.nl/en/general-news/'),
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
    ],
}


def primary_source_candidates(bucket:str,claim:str='')->list[dict]:
    return [{'name':name,'url':url,'bucket':bucket,'claim':claim,'status':'PRIMARY_SOURCE_CANDIDATE'} for name,url in PRIMARY_ADAPTERS.get(bucket,[])]
