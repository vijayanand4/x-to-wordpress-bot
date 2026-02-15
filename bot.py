import requests
import json
import os
from datetime import datetime
import time
import re
import base64
import xml.etree.ElementTree as ET
from groq import Groq

# ============================================
# CONFIGURATION
# ============================================
X_USERNAME = os.getenv('X_USERNAME', '')
HASHTAG = os.getenv('HASHTAG', '')
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')
BLOG_GITHUB_TOKEN = os.getenv('BLOG_GITHUB_TOKEN', '')
BLOG_GITHUB_USERNAME = os.getenv('BLOG_GITHUB_USERNAME', '')
BLOG_REPO = f"{BLOG_GITHUB_USERNAME}.github.io"

# ============================================
# STARTUP
# ============================================
print("\n" + "="*50)
print("🚀 X TO GITHUB PAGES BOT STARTED")
print("="*50 + "\n")

print("🔍 Configuration Check:")
print(f"  X Username:          {'✅' if X_USERNAME else '❌ MISSING'}")
print(f"  Hashtag:             {'✅' if HASHTAG else '❌ MISSING'}")
print(f"  Groq API Key:        {'✅' if GROQ_API_KEY else '❌ MISSING'}")
print(f"  Blog GitHub Token:   {'✅' if BLOG_GITHUB_TOKEN else '❌ MISSING'}")
print(f"  Blog GitHub Username:{'✅' if BLOG_GITHUB_USERNAME else '❌ MISSING'}")

missing = []
if not X_USERNAME: missing.append('X_USERNAME')
if not HASHTAG: missing.append('HASHTAG')
if not GROQ_API_KEY: missing.append('GROQ_API_KEY')
if not BLOG_GITHUB_TOKEN: missing.append('BLOG_GITHUB_TOKEN')
if not BLOG_GITHUB_USERNAME: missing.append('BLOG_GITHUB_USERNAME')

if missing:
    print(f"\n❌ MISSING SECRETS: {', '.join(missing)}")
    exit(1)

print(f"\n✅ All secrets loaded!")
print(f"📝 Blog will publish to: https://{BLOG_REPO}\n")

# Initialize Groq
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    print("✅ Groq AI initialized\n")
except Exception as e:
    print(f"❌ Groq init failed: {str(e)}")
    exit(1)

# GitHub API headers
GITHUB_HEADERS = {
    'Authorization': f'token {BLOG_GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json',
    'Content-Type': 'application/json'
}

# ============================================
# PROCESSED TWEETS
# ============================================

def get_processed_tweets():
    try:
        with open('processed_tweets.json', 'r') as f:
            data = json.load(f)
            print(f"📋 {len(data)} previously processed tweets")
            return data
    except FileNotFoundError:
        print("📋 Starting fresh")
        return []

def save_processed_tweet(tweet_id):
    processed = get_processed_tweets()
    processed.append({
        'id': str(tweet_id),
        'processed_at': datetime.now().isoformat()
    })
    with open('processed_tweets.json', 'w') as f:
        json.dump(processed, f, indent=2)
    print(f"✅ Saved tweet {tweet_id}")

# ============================================
# METHOD 1: TWITTER SYNDICATION
# ============================================

def fetch_via_syndication():
    print("\n📡 Method 1: Twitter Syndication API...")
    url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{X_USERNAME}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Referer': f'https://twitter.com/{X_USERNAME}'
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        print(f"  Status: {response.status_code}")
        if response.status_code == 200 and response.text.strip():
            try:
                data = response.json()
                tweets = extract_from_syndication(data)
                if tweets:
                    return tweets
            except json.JSONDecodeError as e:
                print(f"  ❌ JSON error: {str(e)}")
        else:
            print("  ❌ Empty or failed response")
    except Exception as e:
        print(f"  ❌ Error: {str(e)[:80]}")
    return None

def extract_from_syndication(data):
    try:
        entries = data.get('timeline', {}).get('entries', [])
        print(f"  Found {len(entries)} entries")
        quote_tweets = []
        for entry in entries:
            tweet = entry.get('tweet', {})
            text = tweet.get('full_text', tweet.get('text', ''))
            if not text or HASHTAG.lower() not in text.lower():
                continue
            quoted = tweet.get('quoted_status', {})
            if not quoted:
                continue
            tweet_id = tweet.get('id_str', '')
            quote_tweets.append({
                'id': tweet_id,
                'text': text,
                'quoted_text': quoted.get('full_text', quoted.get('text', '')),
                'url': f"https://x.com/{X_USERNAME}/status/{tweet_id}"
            })
            print(f"  ✅ Found: {tweet_id}")
        return quote_tweets if quote_tweets else None
    except Exception as e:
        print(f"  ❌ Parse error: {str(e)}")
        return None

# ============================================
# METHOD 2: RSS PROXY
# ============================================
def fetch_via_rss_proxy():
    """Try multiple Nitter instances directly"""
    print("\n📡 Method 2: Direct Nitter Instances...")

    nitter_instances = [
        'https://nitter.net',
        'https://nitter.poast.org',
        'https://nitter.privacydev.net',
        'https://nitter.lucabased.xyz',
        'https://nitter.lunar.icu',
        'https://nitter.rawbit.ninja',
        'https://nitter.mint.lgbt',
        'https://nitter.bus-hit.me',
        'https://tweet.namejeff.com',
        'https://nitter.nicfab.eu',
    ]

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Cache-Control': 'no-cache',
    }

    for instance in nitter_instances:
        rss_url = f"{instance}/{X_USERNAME}/rss"
        try:
            print(f"  Trying: {instance}...")
            response = requests.get(
                rss_url,
                headers=headers,
                timeout=10,
                allow_redirects=True
            )
            print(f"  Status: {response.status_code}")

            if response.status_code != 200:
                continue

            content = response.text
            if not content or len(content) < 100:
                print(f"  ❌ Empty or too short")
                continue

            if '<rss' in content or '<item>' in content:
                print(f"  ✅ Valid RSS from {instance}!")
                result = parse_rss_content(content)
                if result:
                    return result
                else:
                    print(f"  ⚠️  RSS parsed but no matching tweets")
            else:
                print(f"  ❌ Not RSS content")

        except requests.exceptions.Timeout:
            print(f"  ❌ Timeout")
        except requests.exceptions.ConnectionError:
            print(f"  ❌ Connection failed")
        except Exception as e:
            print(f"  ❌ Error: {str(e)[:60]}")

    print("  ❌ All Nitter instances failed")
    return None
    
def parse_rss_content(xml_content):
    print("\n  🔍 Parsing RSS...")
    try:
        root = ET.fromstring(xml_content)
        items = root.findall('.//item')
        print(f"  Found {len(items)} items")
        if not items:
            return None
        quote_tweets = []
        for item in items:
            title = item.findtext('title') or ''
            description = item.findtext('description') or ''
            link = item.findtext('link') or ''
            if HASHTAG.lower() not in f"{title} {description}".lower():
                continue
            tweet_id = link.split('/')[-1].replace('#m', '') if link else str(int(time.time()))
            clean_desc = re.sub(r'<[^>]+>', ' ', description)
            clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()
            quote_tweets.append({
                'id': tweet_id,
                'text': title,
                'quoted_text': clean_desc[:500],
                'url': link or f"https://x.com/{X_USERNAME}/status/{tweet_id}"
            })
            print(f"  ✅ Added: {tweet_id}")
        return quote_tweets if quote_tweets else None
    except ET.ParseError as e:
        print(f"  ❌ XML error: {str(e)}")
        return None

# ============================================
# METHOD 3: MANUAL TWEETS
# ============================================

def check_manual_tweets():
    print("\n📡 Method 3: Checking manual_tweets.json...")
    try:
        with open('manual_tweets.json', 'r') as f:
            content = f.read().strip()
        if not content or content == '[]':
            print("  ℹ️  Empty")
            return None
        data = json.loads(content)
        if not data:
            return None
        print(f"  ✅ Found {len(data)} manual tweet(s)!")
        for tweet in data:
            if not tweet.get('url'):
                tweet['url'] = f"https://x.com/{X_USERNAME}/status/{tweet['id']}"
            if not tweet.get('text'):
                tweet['text'] = HASHTAG
            if not tweet.get('quoted_text'):
                tweet['quoted_text'] = ''
        return data
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None

# ============================================
# RESEARCH
# ============================================

def research_topic(text):
    print("\n🔬 Researching topic...")
    query = re.sub(r'#\w+', '', text)
    query = re.sub(r'http\S+', '', query)
    query = re.sub(r'\s+', ' ', query).strip()[:150]
    if not query:
        query = text[:150]
    print(f"  Query: {query[:80]}")
    try:
        response = requests.get(
            "https://api.duckduckgo.com/",
            params={'q': query, 'format': 'json', 'no_html': 1, 'skip_disambig': 1},
            timeout=10
        )
        data = response.json()
        sources = []
        if data.get('AbstractURL'):
            sources.append({
                'title': data.get('AbstractSource', 'Source'),
                'url': data.get('AbstractURL'),
                'snippet': data.get('AbstractText', '')[:300]
            })
        for topic in data.get('RelatedTopics', [])[:4]:
            if isinstance(topic, dict) and topic.get('FirstURL'):
                sources.append({
                    'title': topic.get('Text', '')[:100],
                    'url': topic.get('FirstURL'),
                    'snippet': topic.get('Text', '')[:300]
                })
        print(f"  ✅ Found {len(sources)} sources")
        return sources
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return []

# ============================================
# ARTICLE GENERATION
# ============================================

def generate_article(tweet, sources):
    print("\n✍️  Generating article with Groq AI...")
    sources_text = "\n".join([
        f"- {s['title']}: {s['snippet']} (URL: {s['url']})"
        for s in sources
    ]) if sources else "Use your general knowledge."

    prompt = f"""You are a professional blogger. Write a 300-word article.

TWEET: {tweet['text']}
QUOTED CONTENT: {tweet.get('quoted_text', 'N/A')[:300]}
SOURCES: {sources_text}

EXACT FORMAT:
Title: [Engaging title]

[Opening paragraph]

[Main paragraph with key facts]

[Supporting paragraph with context]

[Closing paragraph with takeaway]

References:
1. [Source Name](URL)
2. [Source Name](URL)

Original Tweet: {tweet['url']}
"""
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a professional blogger writing 300-word articles."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        article = response.choices[0].message.content
        print("  ✅ Article generated!")
        return article
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None

# ============================================
# GITHUB PAGES PUBLISHING
# ============================================

def slugify(text):
    """Convert title to URL-friendly slug"""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'\s+', '-', text.strip())
    return text[:60]

def create_article_html(article, tweet):
    """Convert article text to HTML page"""

    lines = article.split('\n')
    title_line = next(
        (l for l in lines if l.strip().startswith('Title:')),
        None
    )

    if title_line:
        title = title_line.replace('Title:', '').strip()
        idx = lines.index(title_line) + 1
        content = '\n'.join(lines[idx:]).strip()
    else:
        title = f"Article: {tweet['text'][:60]}"
        content = article

    # Convert markdown to HTML
    content = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', content)
    content = re.sub(
        r'\[([^\]]+)\]\(([^\)]+)\)',
        r'<a href="\2" target="_blank">\1</a>',
        content
    )

    paragraphs = content.split('\n\n')
    html_paragraphs = ''.join(
        f'<p>{p.strip().replace(chr(10), "<br>")}</p>\n'
        for p in paragraphs if p.strip()
    )

    date_str = datetime.now().strftime('%B %d, %Y')

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: Georgia, 'Times New Roman', serif;
            line-height: 1.8;
            color: #333;
            background: #fafafa;
        }}
        header {{
            background: #1a1a2e;
            color: white;
            padding: 20px 40px;
        }}
        header a {{
            color: #e0e0e0;
            text-decoration: none;
            font-size: 14px;
        }}
        header a:hover {{ color: white; }}
        .article-container {{
            max-width: 800px;
            margin: 40px auto;
            padding: 0 20px;
        }}
        .article-header {{
            margin-bottom: 30px;
            border-bottom: 3px solid #1a1a2e;
            padding-bottom: 20px;
        }}
        h1 {{
            font-size: 2em;
            color: #1a1a2e;
            line-height: 1.3;
            margin-bottom: 10px;
        }}
        .meta {{
            color: #888;
            font-size: 14px;
            font-family: Arial, sans-serif;
        }}
        .content p {{
            margin-bottom: 20px;
            font-size: 1.1em;
        }}
        .content a {{
            color: #1a1a2e;
        }}
        .source-tweet {{
            background: #f0f4ff;
            border-left: 4px solid #1a1a2e;
            padding: 15px 20px;
            margin: 30px 0;
            border-radius: 0 8px 8px 0;
        }}
        .source-tweet p {{
            margin: 0;
            font-size: 0.95em;
        }}
        .source-tweet a {{
            color: #1a1a2e;
            font-weight: bold;
        }}
        footer {{
            text-align: center;
            padding: 40px;
            color: #888;
            font-family: Arial, sans-serif;
            font-size: 13px;
            border-top: 1px solid #eee;
            margin-top: 60px;
        }}
    </style>
</head>
<body>
    <header>
        <a href="/">← Back to Home</a>
    </header>

    <div class="article-container">
        <div class="article-header">
            <h1>{title}</h1>
            <p class="meta">Published on {date_str} • Auto-researched article</p>
        </div>

        <div class="content">
            {html_paragraphs}
        </div>

        <div class="source-tweet">
            <p>📌 <strong>Source Tweet:</strong> <a href="{tweet['url']}" target="_blank">{tweet['url']}</a></p>
        </div>
    </div>

    <footer>
        <p>Auto-generated article • {date_str}</p>
    </footer>
</body>
</html>"""

    return title, html

def get_existing_articles():
    """Get list of existing articles from GitHub"""
    url = f"https://api.github.com/repos/{BLOG_GITHUB_USERNAME}/{BLOG_REPO}/contents/articles"
    try:
        response = requests.get(url, headers=GITHUB_HEADERS, timeout=10)
        if response.status_code == 200:
            files = response.json()
            return [f['name'].replace('.html', '') for f in files if f['name'].endswith('.html')]
        return []
    except:
        return []

def publish_to_github_pages(article, tweet):
    """Publish article as HTML file to GitHub Pages"""
    print("\n📤 Publishing to GitHub Pages...")

    title, html_content = create_article_html(article, tweet)
    slug = slugify(title)
    filename = f"{slug}-{tweet['id'][:8]}.html"
    filepath = f"articles/{filename}"

    print(f"  Title: {title[:60]}")
    print(f"  File: {filepath}")

    # Encode content to base64
    encoded_content = base64.b64encode(html_content.encode('utf-8')).decode('utf-8')

    # Check if file exists
    check_url = f"https://api.github.com/repos/{BLOG_GITHUB_USERNAME}/{BLOG_REPO}/contents/{filepath}"
    check_response = requests.get(check_url, headers=GITHUB_HEADERS)

    payload = {
        'message': f'Add article: {title[:50]}',
        'content': encoded_content,
        'branch': 'main'
    }

    if check_response.status_code == 200:
        payload['sha'] = check_response.json()['sha']

    try:
        response = requests.put(
            check_url,
            headers=GITHUB_HEADERS,
            json=payload,
            timeout=30
        )

        print(f"  GitHub Response: {response.status_code}")

        if response.status_code in [200, 201]:
            article_url = f"https://{BLOG_REPO}/articles/{filename}"
            print(f"  ✅ Published! → {article_url}")
            update_homepage(title, filename, tweet)
            return {'link': article_url, 'title': title}
        else:
            print(f"  ❌ Failed: {response.text[:300]}")
            return None

    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None

def update_homepage(new_title, new_filename, tweet):
    """Update the blog homepage with new article"""
    print("  📝 Updating homepage...")

    # Get existing index.html
    index_url = f"https://api.github.com/repos/{BLOG_GITHUB_USERNAME}/{BLOG_REPO}/contents/index.html"
    existing_sha = None
    existing_articles_html = ""

    response = requests.get(index_url, headers=GITHUB_HEADERS)
    if response.status_code == 200:
        existing_sha = response.json()['sha']
        existing_content = base64.b64decode(response.json()['content']).decode('utf-8')
        # Extract existing articles list
        match = re.search(r'<ul class="articles-list">(.*?)</ul>', existing_content, re.DOTALL)
        if match:
            existing_articles_html = match.group(1).strip()

    # Add new article to top of list
    date_str = datetime.now().strftime('%B %d, %Y')
    new_item = f'''        <li>
            <span class="date">{date_str}</span>
            <a href="articles/{new_filename}">{new_title}</a>
            <span class="source"><a href="{tweet['url']}" target="_blank">source tweet</a></span>
        </li>'''

    updated_list = new_item + "\n" + existing_articles_html

    homepage_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>My Research Blog</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: Arial, sans-serif;
            background: #fafafa;
            color: #333;
        }}
        header {{
            background: #1a1a2e;
            color: white;
            padding: 40px;
            text-align: center;
        }}
        header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        header p {{
            color: #aaa;
            font-size: 1.1em;
        }}
        .container {{
            max-width: 800px;
            margin: 40px auto;
            padding: 0 20px;
        }}
        h2 {{
            font-size: 1.4em;
            color: #1a1a2e;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #1a1a2e;
        }}
        .articles-list {{
            list-style: none;
        }}
        .articles-list li {{
            padding: 15px 0;
            border-bottom: 1px solid #eee;
            display: flex;
            align-items: baseline;
            gap: 15px;
            flex-wrap: wrap;
        }}
        .articles-list a {{
            color: #1a1a2e;
            text-decoration: none;
            font-size: 1.05em;
            font-weight: bold;
            flex: 1;
        }}
        .articles-list a:hover {{
            text-decoration: underline;
        }}
        .date {{
            color: #888;
            font-size: 13px;
            white-space: nowrap;
        }}
        .source {{
            font-size: 12px;
            color: #888;
        }}
        .source a {{
            color: #888;
            font-weight: normal !important;
        }}
        .empty {{
            text-align: center;
            padding: 60px;
            color: #888;
        }}
        footer {{
            text-align: center;
            padding: 40px;
            color: #888;
            font-size: 13px;
            border-top: 1px solid #eee;
            margin-top: 40px;
        }}
    </style>
</head>
<body>
    <header>
        <h1>📰 My Research Blog</h1>
        <p>Auto-researched articles from X/Twitter</p>
    </header>

    <div class="container">
        <h2>Latest Articles</h2>
        <ul class="articles-list">
{updated_list}
        </ul>
    </div>

    <footer>
        <p>Powered by X → GitHub Pages Bot</p>
    </footer>
</body>
</html>"""

    encoded = base64.b64encode(homepage_html.encode('utf-8')).decode('utf-8')

    payload = {
        'message': f'Update homepage with: {new_title[:40]}',
        'content': encoded,
        'branch': 'main'
    }
    if existing_sha:
        payload['sha'] = existing_sha

    response = requests.put(
        index_url,
        headers=GITHUB_HEADERS,
        json=payload,
        timeout=30
    )

    if response.status_code in [200, 201]:
        print(f"  ✅ Homepage updated!")
    else:
        print(f"  ❌ Homepage update failed: {response.text[:200]}")

# ============================================
# MAIN
# ============================================

def main():
    print("🔄 Fetching tweets...\n")

    tweets = fetch_via_syndication()
    if not tweets:
        tweets = fetch_via_rss_proxy()
    if not tweets:
        tweets = check_manual_tweets()

    if not tweets:
        print("\n⚠️  No tweets found.\n")
        return

    processed_ids = [
        str(t['id']) if isinstance(t, dict) else str(t)
        for t in get_processed_tweets()
    ]

    new_tweets = [
        t for t in tweets
        if str(t['id']) not in processed_ids
    ]

    if len(new_tweets) > 3:
        print(f"⚠️  Found {len(new_tweets)} tweets, processing 3 per run")
        new_tweets = new_tweets[:3]

    if not new_tweets:
        print(f"\n✅ All tweets already processed!\n")
        return

    print(f"\n📊 Processing {len(new_tweets)} tweet(s)...\n")

    success_count = 0
    fail_count = 0

    for i, tweet in enumerate(new_tweets, 1):
        print(f"\n{'='*40}")
        print(f"TWEET {i} of {len(new_tweets)}")
        print(f"{'='*40}")
        print(f"ID:   {tweet['id']}")
        print(f"Text: {tweet['text'][:100]}")

        sources = research_topic(tweet.get('quoted_text') or tweet['text'])
        time.sleep(2)

        article = generate_article(tweet, sources)
        if not article:
            fail_count += 1
            continue

        result = publish_to_github_pages(article, tweet)
        if result:
            save_processed_tweet(str(tweet['id']))
            success_count += 1
            print(f"\n🎉 Tweet {i} done! → {result['link']}")
        else:
            fail_count += 1

        if i < len(new_tweets):
            time.sleep(3)

    print("\n" + "="*50)
    print("📊 SUMMARY")
    print("="*50)
    print(f"  ✅ Success: {success_count}")
    print(f"  ❌ Failed:  {fail_count}")
    print("="*50)
    print("🎉 BOT COMPLETE!\n")

if __name__ == "__main__":
    main()
