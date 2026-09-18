import json, re, hashlib, html, unicodedata, time, traceback
from difflib import SequenceMatcher
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote_plus, urlsplit, urlunsplit, parse_qsl, urlencode
import feedparser, requests, trafilatura
from googlenewsdecoder import gnewsdecoder
from deep_translator import GoogleTranslator, MyMemoryTranslator
from langdetect import detect as detect_language

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
DATA = ROOT / 'data/articles.json'
DOCS = ROOT / 'docs'
CATDIR = DOCS / 'categories'
KWDIR = DOCS / 'keywords'
STATE = ROOT / 'data/state.json'

def norm(s):
    return re.sub(r'\s+', ' ', ''.join(c for c in unicodedata.normalize('NFKD', str(s)) if not unicodedata.combining(c)).lower()).strip()

def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', norm(s)).strip('-')

def clean_url(u):
    try:
        p = urlsplit(u)
        q = [(k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith('utm_') and k.lower() not in {'fbclid','gclid','mc_cid','mc_eid'}]
        return urlunsplit((p.scheme,p.netloc,p.path,urlencode(q),''))
    except Exception:
        return u

def domain(u):
    try:
        return urlsplit(u).netloc.removeprefix('www.')
    except Exception:
        return ''

def parse_dt(s):
    for f in ('%Y%m%dT%H%M%SZ','%Y%m%d%H%M%S','%Y-%m-%dT%H:%M:%SZ'):
        try:
            return datetime.strptime(str(s), f).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)

def feed_dt(e):
    p = getattr(e,'published_parsed',None) or getattr(e,'updated_parsed',None)
    return datetime(*p[:6], tzinfo=timezone.utc) if p else datetime.now(timezone.utc)

def search_query(item):
    kw=item['keyword']
    cat=item['category']
    rules=CFG.get('category_search_rules',{}).get(cat,{})
    extras=rules.get('extra_terms',[])
    if cat=='Horoscopes & Astrology':
        # Horoscope publishers use many different phrasings. Search both the exact
        # configured keyword and common love/dating astrology terminology.
        broad=' OR '.join(f'"{x}"' for x in extras)
        return f'(\"{kw}\" OR {broad})'
    context=' OR '.join(f'"{x}"' for x in extras) if extras else 'relationship OR dating OR romance OR love'
    return f'\"{kw}\" ({context})'

def decode_google(u):
    if 'news.google.com' not in u:
        return clean_url(u)
    try:
        r = gnewsdecoder(u, interval=CFG['settings'].get('google_decode_interval_seconds',0.05))
        if isinstance(r, dict) and r.get('status') and r.get('decoded_url'):
            return clean_url(r['decoded_url'])
    except Exception:
        pass
    return None

def discover_gdelt(item):
    try:
        r = requests.get('https://api.gdeltproject.org/api/v2/doc/doc', params={
            'query': search_query(item), 'mode':'artlist',
            'maxrecords': CFG['settings']['gdelt_results_per_keyword'],
            'timespan': f"{CFG['settings']['max_age_hours']}h",
            'sort':'datedesc','format':'json'
        }, timeout=30, headers={'User-Agent':'RelationshipNewsRSS/1.0'})
        arr = r.json().get('articles',[])
    except Exception:
        return []
    return [dict(url=clean_url(x.get('url','')), title=x.get('title',''), source=x.get('domain',''),
                 published=parse_dt(x.get('seendate')), language=x.get('language',''), country=x.get('sourcecountry',''),
                 via='GDELT', keyword=item['keyword'], category=item['category']) for x in arr if x.get('url')]

def discover_google(item):
    out=[]; q=search_query(item)
    cutoff=datetime.now(timezone.utc)-timedelta(hours=float(CFG['settings'].get('max_age_hours',2)))

    for ed in CFG['google_news_editions']:
        url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl={quote_plus(ed['hl'])}&gl={quote_plus(ed['gl'])}&ceid={quote_plus(ed['ceid'])}"
        feed = feedparser.parse(url)

        for e in list(getattr(feed,'entries',[]))[:CFG['settings']['google_results_per_edition']]:
            # IMPORTANT: cheap date check first.
            published=feed_dt(e)
            if published < cutoff:
                continue

            # Only decode the expensive Google News URL when the item is fresh.
            u = decode_google(getattr(e,'link',''))
            if not u:
                continue

            src=''
            try:
                src = e.source.get('title','') if getattr(e,'source',None) else ''
            except Exception:
                pass

            out.append(dict(
                url=u,
                title=getattr(e,'title',''),
                source=src or domain(u),
                published=published,
                language='',
                country=ed['label'],
                via='Google News',
                keyword=item['keyword'],
                category=item['category']
            ))
    return out

def extract(u):
    try:
        raw = trafilatura.fetch_url(u)
        if not raw: return None
        x = trafilatura.extract(raw,url=u,output_format='json',with_metadata=True,include_comments=False,include_tables=True,favor_precision=True)
        if not x: return None
        d=json.loads(x); body=(d.get('text') or '').strip()
        if not body: return None
        return {'title':(d.get('title') or '').strip(),'author':(d.get('author') or '').strip(),'body':body}
    except Exception:
        return None

def has_context(text,item=None):
    if item:
        rules=CFG.get('category_search_rules',{}).get(item.get('category',''),{})
        if rules.get('require_relationship_context',True) is False:
            return True
    n=norm(text)
    return any(norm(t) in n for t in CFG['relationship_context_terms'])

def keyword_matches(text, kw, item=None):
    n=norm(text)
    if norm(kw) in n:
        return True
    if item and item.get('category')=='Horoscopes & Astrology':
        # For astrology, real-world headlines rarely repeat our exact SEO phrase.
        astrology_terms=['horoscope','astrology','zodiac','tarot','synastry','birth chart','venus sign','mars sign','moon sign','star sign','retrograde']
        love_terms=['love','romance','romantic','dating','relationship','compatibility','attraction','intimacy','passion','match','couple']
        return any(norm(x) in n for x in astrology_terms) and any(norm(x) in n for x in love_terms)
    return False

def split_chunks(text, n):
    out=[]; cur=''
    for para in str(text).split('\n'):
        para=para.strip()
        if not para: continue
        while len(para)>n:
            cut=para.rfind(' ',0,n); cut=cut if cut>n//2 else n
            piece,para=para[:cut],para[cut:]
            if cur: out.append(cur); cur=''
            out.append(piece)
        add=para if not cur else '\n\n'+para
        if len(cur)+len(add)<=n: cur+=add
        else:
            if cur: out.append(cur)
            cur=para
    if cur: out.append(cur)
    return out

def translate(text):
    text=str(text or '').strip()
    if not text:
        return text,False
    target=CFG['translation'].get('target_language','es')
    retries=int(CFG['translation'].get('max_retries',3))
    delay=float(CFG['translation'].get('retry_delay_seconds',2.0))
    parts=split_chunks(text,CFG['translation'].get('chunk_size',2200))
    output=[]; translated_count=0

    language_names={'en':'english','es':'spanish','fr':'french','de':'german','it':'italian','pt':'portuguese','nl':'dutch','ru':'russian','ja':'japanese','ko':'korean'}

    for idx,chunk in enumerate(parts,1):
        result=None
        for attempt in range(1,retries+1):
            try:
                result=GoogleTranslator(source='auto',target=target).translate(chunk)
                if result and result.strip():
                    break
            except Exception as exc:
                print(f'    Google translation {attempt}/{retries} failed for chunk {idx}/{len(parts)}: {exc}')
                time.sleep(delay*attempt)

        if (not result or not result.strip()) and CFG['translation'].get('use_mymemory_fallback',True):
            try:
                detected=detect_language(chunk[:1500])
                if detected=='es':
                    result=chunk
                elif detected in language_names:
                    result=MyMemoryTranslator(source=language_names[detected],target='spanish').translate(chunk)
                    print(f'    MyMemory fallback used ({detected}) for chunk {idx}/{len(parts)}')
            except Exception as exc:
                print(f'    MyMemory fallback failed for chunk {idx}/{len(parts)}: {exc}')

        if not result or not result.strip():
            print(f'    TRANSLATION FAILED for chunk {idx}/{len(parts)}; original retained')
            result=chunk
        elif norm(result)!=norm(chunk):
            translated_count+=1
        output.append(result.strip())

    final='\n\n'.join(output).strip()
    return final or text, translated_count>0

def ensure_translation(a):
    a['original_title']=a.get('original_title') or a.get('title','')
    a['original_body']=a.get('original_body') or a.get('body','')

    if a.get('translation_status') in {'translated','already_spanish'} and a.get('rss_title') and a.get('rss_body'):
        return

    try:
        detected=detect_language(a['original_body'][:1800])
    except Exception:
        detected=''

    if detected=='es':
        a['rss_title']=a['original_title']
        a['rss_body']=a['original_body']
        a['translation_status']='already_spanish'
        a['translated_to']='es'
        a['source_detected_language']='es'
        a['translation_last_attempt']=datetime.now(timezone.utc).isoformat()
        print('  Already Spanish:',a['original_title'][:90])
        return

    print('  Translating:',a['original_title'][:90])
    a['rss_title'],ok1=translate(a['original_title'])
    a['rss_body'],ok2=translate(a['original_body'])
    a['translation_status']='translated' if ok1 and ok2 else 'partial_or_fallback'
    a['translated_to']='es'
    a['source_detected_language']=detected
    a['translation_last_attempt']=datetime.now(timezone.utc).isoformat()
    print('    Translation status:',a['translation_status'])

def tokens(s):
    return {w for w in re.findall(r'[a-z0-9]+',norm(s)) if len(w)>2}

def sim(a,b):
    return SequenceMatcher(None,norm(a),norm(b)).ratio() if a and b else 0

def overlap(a,b):
    x,y=tokens(a),tokens(b)
    return len(x&y)/len(x|y) if x and y else 0

def art_dt(a):
    try: return datetime.fromisoformat(a['published_iso']).astimezone(timezone.utc)
    except Exception: return datetime.now(timezone.utc)

def duplicate(a,b):
    d=CFG['deduplication']
    if abs((art_dt(a)-art_dt(b)).total_seconds())/3600 > d['max_hours_apart']: return False
    if not (set(a.get('categories',[]))&set(b.get('categories',[])) or set(a.get('matched_keywords',[]))&set(b.get('matched_keywords',[]))): return False
    ta,tb=a.get('rss_title') or a.get('title',''),b.get('rss_title') or b.get('title',''); ba,bb=a.get('rss_body') or a.get('body',''),b.get('rss_body') or b.get('body','')
    ts,ov=sim(ta,tb),overlap(ta,tb); bs=sim(ba[:d['body_lead_characters']],bb[:d['body_lead_characters']])
    return ts>=d['title_similarity_threshold'] or ov>=d['title_token_overlap_threshold'] or (ts>=.5 and bs>=d['body_lead_similarity_threshold']) or bs>=.82

def score(a):
    s=min(len(a.get('rss_body','')),25000)+min(len(a.get('rss_title','')),180)*2
    if a.get('author'): s+=500
    if a.get('source'): s+=250
    if a.get('translation_status')=='translated': s+=150
    return s

def merge_meta(w,l):
    for k in ('discovery_sources','source_languages','source_countries','matched_keywords','categories'):
        w.setdefault(k,[])
        for v in l.get(k,[]):
            if v and v not in w[k]: w[k].append(v)
    w.setdefault('alternate_sources',[])
    info={'source':l.get('source',''),'url':l.get('url',''),'title':l.get('title',''),'body_characters':len(l.get('rss_body',''))}
    if info['url'] and not any(x.get('url')==info['url'] for x in w['alternate_sources']): w['alternate_sources'].append(info)
    w['duplicate_versions_removed']=len(w['alternate_sources'])

def deduplicate(arr):
    kept=[]
    for a in sorted(arr,key=lambda x:x.get('published_iso',''),reverse=True):
        idx=next((i for i,b in enumerate(kept) if duplicate(a,b)),None)
        if idx is None: kept.append(a)
        elif score(a)>score(kept[idx]): merge_meta(a,kept[idx]); kept[idx]=a
        else: merge_meta(kept[idx],a)
    return kept

def source_label(a):
    return (a.get('source') or domain(a.get('url','')) or 'Fuente desconocida').strip()

def display_title(a):
    return f"[{source_label(a)}] {a.get('rss_title') or a.get('title','')}"

def cdata(s):
    return '<![CDATA['+str(s).replace(']]>',']]]]><![CDATA[>')+']]>'

def make_rss(arr,title,desc):
    items=[]
    for a in sorted(arr,key=lambda x:x.get('published_iso',''),reverse=True)[:CFG['settings']['max_feed_items']]:
        body=a.get('rss_body') or a.get('body','')
        body_html='<p>'+html.escape(body).replace('\n\n','</p><p>').replace('\n','<br>')+'</p>'
        cats=''.join(f'<category>{html.escape(x)}</category>' for x in a.get('categories',[])+a.get('matched_keywords',[]))
        creator=f'<dc:creator>{cdata(a["author"])}</dc:creator>' if a.get('author') else ''
        article_url=a.get('url','')
        article_id=a.get('id') or hashlib.sha256(article_url.encode()).hexdigest()[:20]
        pub_date=a.get('published_rfc2822')
        if not pub_date:
            pub_date=format_datetime(art_dt(a))
        item=(f'<item><title>{cdata(display_title(a))}</title><link>{html.escape(article_url)}</link>'
              f'<guid isPermaLink="false">{article_id}</guid><pubDate>{pub_date}</pubDate>'
              f'<source>{cdata(a.get("source",""))}</source>{creator}<description>{cdata(body[:500])}</description>'
              f'<content:encoded>{cdata(body_html)}</content:encoded>{cats}</item>')
        items.append(item)
    return (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" '
            f'xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><title>{cdata(title)}</title><link>{CFG["feed"]["site_url"]}</link>'
            f'<description>{cdata(desc)}</description><lastBuildDate>{format_datetime(datetime.now(timezone.utc))}</lastBuildDate>{"".join(items)}</channel></rss>')

def generate(arr):
    DOCS.mkdir(exist_ok=True); CATDIR.mkdir(parents=True,exist_ok=True); KWDIR.mkdir(parents=True,exist_ok=True)
    (DOCS/'feed.xml').write_text(make_rss(arr,CFG['feed']['title'],CFG['feed']['description']),encoding='utf-8')
    cats=[]
    for item in CFG['keywords']:
        if item['category'] not in cats: cats.append(item['category'])
    for cat in cats:
        sub=[a for a in arr if cat in a.get('categories',[])]
        (CATDIR/f'{slug(cat)}.xml').write_text(make_rss(sub,f'{cat} — Relationship News',f'Noticias de {cat}.'),encoding='utf-8')
    for item in CFG['keywords']:
        kw=item['keyword']; sub=[a for a in arr if kw in a.get('matched_keywords',[])]
        (KWDIR/f'{slug(kw)}.xml').write_text(make_rss(sub,f'{kw} — Relationship News',f'Noticias para {kw}.'),encoding='utf-8')
    links=''.join(f'<li><a href="categories/{slug(c)}.xml">{html.escape(c)}</a></li>' for c in cats)
    cards=''.join(f'<article><h2><a href="{html.escape(a["url"])}">{html.escape(display_title(a))}</a></h2><p>{html.escape(", ".join(a.get("categories",[])))}</p></article>' for a in sorted(arr,key=lambda x:x.get('published_iso',''),reverse=True)[:300])
    (DOCS/'index.html').write_text(f'<!doctype html><html><meta charset="utf-8"><body><h1>Relationship News RSS</h1><p><a href="feed.xml">RSS general</a></p><h2>Categorías</h2><ul>{links}</ul>{cards}</body></html>',encoding='utf-8')

def load_state():
    if not STATE.exists():
        return {'next_batch':1}
    try:
        return json.loads(STATE.read_text(encoding='utf-8'))
    except Exception:
        return {'next_batch':1}

def save_state(state):
    STATE.parent.mkdir(parents=True,exist_ok=True)
    STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')

def select_keyword_batch():
    """
    Batch 1: keyword IDs 1-55.
    Batch 2: keyword IDs 56-105.
    The batch only advances after the run finishes and saves successfully.
    """
    state=load_state()
    batch_number=1 if int(state.get('next_batch',1))==1 else 2
    split_at=int(CFG['settings'].get('keyword_batch_1_end',55))

    if batch_number==1:
        selected=[x for x in CFG['keywords'] if int(x.get('id',0))<=split_at]
    else:
        selected=[x for x in CFG['keywords'] if int(x.get('id',0))>split_at]

    print(f'Keyword batch {batch_number}: {len(selected)} searches')
    print(f'Rolling news window: last {CFG["settings"].get("max_age_hours",2)} hours')
    return selected,batch_number,state

def main():
    articles=json.loads(DATA.read_text(encoding='utf-8')) if DATA.exists() else []
    byurl={a.get('url'):a for a in articles}

    cutoff=datetime.now(timezone.utc)-timedelta(
        hours=float(CFG['settings'].get('max_age_hours',2))
    )

    selected,batch_number,state=select_keyword_batch()
    new_ids=[]

    for item in selected:
        print('SEARCH:',item['category'],'/',item['keyword'])
        if item['category']=='Horoscopes & Astrology':
            print('  Astrology query:',search_query(item))

        candidates=discover_gdelt(item)+discover_google(item)

        # Both discovery functions already use the rolling window, but retain
        # this second check as protection against malformed dates.
        unique={
            c['url']:c for c in candidates
            if c.get('url') and c['published']>=cutoff
        }

        for c in sorted(unique.values(),key=lambda x:x['published'],reverse=True):
            if c['url'] in byurl:
                a=byurl[c['url']]

                if c['keyword'] not in a.setdefault('matched_keywords',[]):
                    a['matched_keywords'].append(c['keyword'])
                if c['category'] not in a.setdefault('categories',[]):
                    a['categories'].append(c['category'])
                if c.get('via') and c['via'] not in a.setdefault('discovery_sources',[]):
                    a['discovery_sources'].append(c['via'])
                if c.get('language') and c['language'] not in a.setdefault('source_languages',[]):
                    a['source_languages'].append(c['language'])
                if c.get('country') and c['country'] not in a.setdefault('source_countries',[]):
                    a['source_countries'].append(c['country'])
                continue

            # Expensive operations happen only for genuinely new, fresh URLs.
            ex=extract(c['url'])
            if not ex or len(ex['body'])<CFG['settings']['minimum_body_characters']:
                continue

            full=ex['title']+'\n'+ex['body']
            if not keyword_matches(full,c['keyword'],item) or not has_context(full,item):
                continue

            pub=c['published']
            a={
                'id':hashlib.sha256(c['url'].encode()).hexdigest()[:20],
                'title':ex['title'] or c['title'],
                'source':c['source'] or domain(c['url']),
                'author':ex['author'],
                'url':c['url'],
                'published_iso':pub.isoformat(),
                'published_rfc2822':format_datetime(pub),
                'body':ex['body'],
                'matched_keywords':[c['keyword']],
                'categories':[c['category']],
                'source_languages':[c['language']] if c['language'] else [],
                'source_countries':[c['country']] if c['country'] else [],
                'discovery_sources':[c['via']]
            }

            articles.append(a)
            byurl[a['url']]=a
            new_ids.append(a['id'])

    articles=sorted(
        articles,
        key=lambda x:x.get('published_iso',''),
        reverse=True
    )[:CFG['settings']['max_stored_articles']]

    # Translate every newly accepted article.
    new_set=set(new_ids)
    new_articles=[a for a in articles if a.get('id') in new_set]

    print(f'New accepted articles this run: {len(new_articles)}')
    for a in new_articles:
        ensure_translation(a)

    # Gradually repair a small number of old incomplete translations so a
    # previous failure does not make each hourly run heavy.
    repair_limit=int(CFG['settings'].get('old_translation_repairs_per_run',20))
    repairs=0
    for a in articles:
        if repairs>=repair_limit:
            break
        if a.get('id') in new_set:
            continue
        if a.get('translation_status') not in {'translated','already_spanish'}:
            ensure_translation(a)
            repairs+=1

    print(f'Older translation repairs attempted: {repairs}/{repair_limit}')

    articles=deduplicate(articles)

    DATA.write_text(
        json.dumps(articles,ensure_ascii=False,indent=2),
        encoding='utf-8'
    )
    generate(articles)

    # Advance 1 -> 2 -> 1 only after the output has been generated.
    state['last_completed_batch']=batch_number
    state['last_completed_at']=datetime.now(timezone.utc).isoformat()
    state['next_batch']=2 if batch_number==1 else 1
    save_state(state)

    print('Unique stories:',len(articles))
    print('Next keyword batch:',state['next_batch'])

if __name__=='__main__':
    try:
        main()
    except Exception:
        print("\nFATAL ERROR — full traceback follows:\n")
        traceback.print_exc()
        raise
