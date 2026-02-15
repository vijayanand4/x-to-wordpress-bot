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
WP_SITE_URL = os.getenv('WP_SITE_URL', '').rstrip('/')
WP_USERNAME = os.getenv('WP_USERNAME', '')
WP_PASSWORD = os.getenv('WP_PASSWORD', '')
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')

# ============================================
# STARTUP
# ============================================
print("\n" + "="*50)
print("🚀 X TO WORDPRESS BOT STARTED")
print("="*50 + "\n")

print("🔍 Configuration Check:")
print(f"  X Username:     {'✅' if X_USERNAME else '❌ MISSING'}")
print(f"  Hashtag:        {'✅' if HASHTAG else '❌ MISSING'}")
print(f"  WP Site URL:    {'✅' if WP_SITE_URL else '❌ MISSING'}")
print(f"  WP Username:    {'✅' if WP_USERNAME else '❌ MISSING'}")
print(f"  WP Password:    {'✅' if WP_PASSWORD else '❌ MISSING'}")
print(f"  Groq API Key:   {'✅' if GROQ_API_KEY else '❌ MISSING'}")

missing = []
if not X_USERNAME: missing.append('X_USERNAME')
if not HASHTAG: missing.append('HASHTAG')
if not WP_SITE_URL: missing.append('WP_SITE_URL')
if not WP_USERNAME: missing.append('WP_USERNAME')
if not WP_PASSWORD: missing.append('WP_PASSWORD')
if not GROQ_API_KEY: missing.append('GROQ_API_KEY')

if missing:
    print(f"\n❌ MISSING SECRETS: {', '.join(missing)}")
    exit(1)

print("\n✅ All secrets loaded!\n")

# Initialize Groq
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    print("✅ Groq AI initialized\n")
except Exception as e:
    print(f"❌ Groq init failed: {str(e)}")
    exit(1)

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
# METHOD 1: TWITTER SYNDICATION API
# ============================================

def fetch_via_syndication():
    """Use Twitter syndication API - no auth needed"""
    print("\n📡 Method 1: Twitter Syndication API...")

    url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{X_USERNAME}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
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
                else:
                    print("  ⚠️  No matching tweets found")
            except json.JSONDecodeError as e:
                print(f"  ❌ JSON parse error: {str(e)}")
        else:
            print(f"  ❌ Empty or failed response")

    except Exception as e:
        print(f"  ❌ Error: {str(e)[:80]}")

    return None

def extract_from_syndication(data):
    """Extract quote tweets from syndication response"""
    try:
        timeline = data.get('timeline', {})
        entries = timeline.get('entries', [])
        print(f"  Found {len(entries)} entries")

        quote_tweets = []
        for entry in entries:
            tweet = entry.get('tweet', {})
            text = tweet.get('full_text', tweet.get('text', ''))

            if not text or HASHTAG.lower() not in text.lower():
                continue

            print(f"  📌 Found tweet with hashtag: {text[:60]}...")

            quoted = tweet.get('quoted_status', {})
            if not quoted:
                print(f"     ⚠️  Not a quote tweet, skipping")
                continue

            tweet_id = tweet.get('id_str', '')
            quoted_text = quoted.get('full_text', quoted.get('text', ''))

            quote_tweets.append({
                'id': tweet_id,
                'text': text,
                'quoted_text': quoted_text,
                'url': f"https://x.com/{X_USERNAME}/status/{tweet_id}"
            })
            print(f"     ✅ Valid quote tweet: {tweet_id}")

        return quote_tweets if quote_tweets else None

    except Exception as e:
        print(f"  ❌ Parse error: {str(e)}")
        return None

# ============================================
# METHOD 2: ALLORIGINS RSS PROXY
# ============================================

def fetch_via_rss_proxy():
    """Try allorigins proxy with base64 decode support"""
    print("\n📡 Method 2: RSS Proxy...")

    nitter_url = f'https://nitter.net/{X_USERNAME}/rss'
    proxy_url = f"https://api.allorigins.win/get?url={requests.utils.quote(nitter_url)}"

    try:
        response = requests.get(proxy_url, timeout=20)
        print(f"  Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            content = data.get('contents', '')

            if not content:
                print("  ❌ Empty content")
                return None

            if content.startswith('data:'):
                print("  📦 Decoding base64...")
                try:
                    base64_data = content.split(',', 1)[1]
                    content = base64.b64decode(base64_data).decode('utf-8')
                    print(f"  ✅ Decoded! ({len(content)} chars)")
                except Exception as e:
                    print(f"  ❌ Decode error: {str(e)}")
                    return None

            if '<rss' in content or '<item>' in content:
                print("  ✅ Valid RSS found!")
                return parse_rss_content(content)
            else:
                print(f"  ❌ No RSS content")

    except Exception as e:
        print(f"  ❌ Error: {str(e)[:80]}")

    return None

def parse_rss_content(xml_content):
    """Parse RSS XML and find tweets with hashtag"""
    print("\n  🔍 Parsing RSS...")

    try:
        root = ET.fromstring(xml_content)
        items = root.findall('.//item')
        print(f"  Found {len(items)} items in RSS")

        if not items:
            return None

        quote_tweets = []
        for item in items:
            title_elem = item.find('title')
            desc_elem = item.find('description')
            link_elem = item.find('link')

            title = title_elem.text if title_elem is not None else ''
            description = desc_elem.text if desc_elem is not None else ''
            link = link_elem.text if link_elem is not None else ''

            full_text = f"{title} {description}"

            if HASHTAG.lower() not in full_text.lower():
                continue

            print(f"  📌 Found: {title[:60]}...")

            tweet_id = link.split('/')[-1].replace('#m', '') if link else str(int(time.time()))

            clean_desc = re.sub(r'<[^>]+>', ' ', description)
            clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()

            quote_tweets.append({
                'id': tweet_id,
                'text': title,
                'quoted_text': clean_desc[:500],
                'url': link or f"https://x.com/{X_USERNAME}/status/{tweet_id}"
            })
            print(f"     ✅ Added: {tweet_id}")

        return quote_tweets if quote_tweets else None

    except ET.ParseError as e:
        print(f"  ❌ XML error: {str(e)}")
        return None

# ============================================
# METHOD 3: MANUAL TWEETS FILE
# ============================================

def check_manual_tweets():
    """Read from manual_tweets.json as fallback"""
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

        valid_tweets = []
        for tweet in data:
            if not tweet.get('id'):
                continue
            if not tweet.get('url'):
                tweet['url'] = f"https://x.com/{X_USERNAME}/status/{tweet['id']}"
            if not tweet.get('text'):
                tweet['text'] = HASHTAG
            if not tweet.get('quoted_text'):
                tweet['quoted_text'] = ''
            valid_tweets.append(tweet)

        return valid_tweets if valid_tweets else None

    except json.JSONDecodeError as e:
        print(f"  ❌ JSON error: {str(e)}")
        return None
    except FileNotFoundError:
        print("  ℹ️  File not found")
        return None

# ============================================
# RESEARCH
# ============================================

def research_topic(text):
    """Research using DuckDuckGo"""
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
            params={
                'q': query,
                'format': 'json',
                'no_html': 1,
                'skip_disambig': 1
            },
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
    """Generate 300-word article using Groq"""
    print("\n✍️  Generating article with Groq AI...")

    sources_text = "\n".join([
        f"- {s['title']}: {s['snippet']} (URL: {s['url']})"
        for s in sources
    ]) if sources else "Use your general knowledge about this topic."

    prompt = f"""You are a professional blogger and journalist.
Write a well-researched 300-word article based on the following:

TWEET: {tweet['text']}
QUOTED CONTENT: {tweet.get('quoted_text', 'N/A')[:300]}
RESEARCH SOURCES: {sources_text}

Use this EXACT format:

Title: [Write an engaging informative title here]

[Opening paragraph - hook the reader introduce the topic]

[Main paragraph - key facts background important details]

[Supporting paragraph - additional context implications]

[Closing paragraph - conclusion and takeaway]

References:
1. [Source Name](URL)
2. [Source Name](URL)

Original Tweet: {tweet['url']}

Important: Write exactly 300 words professional tone factual and informative.
"""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional blogger who writes clear informative 300-word articles."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=1000,
            temperature=0.7
        )

        article = response.choices[0].message.content
        print("  ✅ Article generated!")
        return article

    except Exception as e:
        print(f"  ❌ Generation error: {str(e)}")
        return None

# ============================================
# WORDPRESS PUBLISHING
# ============================================

def publish_to_wordpress(article, tweet):
    """Publish article to WordPress via REST API with retries"""
    print("\n📤 Publishing to WordPress...")

    if not article:
        print("  ❌ No article to publish")
        return None

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
        r'<a href="\2">\1</a>',
        content
    )
    content = content.replace('\n\n', '</p><p>')
    content = content.replace('\n', '<br>')
    content = f"<p>{content}</p>"

    print(f"  Title: {title[:70]}")
    print(f"  Posting to: {WP_SITE_URL}/wp-json/wp/v2/posts")

    # Try up to 3 times
    for attempt in range(1, 4):
        try:
            print(f"  Attempt {attempt} of 3...")

            if attempt > 1:
                print(f"  Waiting 15 seconds before retry...")
                time.sleep(15)

            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'Connection': 'close',
                'Content-Type': 'application/json'
            })

            response = session.post(
                f"{WP_SITE_URL}/wp-json/wp/v2/posts",
                json={
                    'title': title,
                    'content': content,
                    'status': 'publish',
                    'excerpt': f"Auto-generated from: {tweet['url']}"
                },
                auth=(WP_USERNAME, WP_PASSWORD),
                timeout=60,
                verify=True
            )

            print(f"  WordPress Response: {response.status_code}")
            if response.status_code in [200, 201]:
                # Handle empty response body (common on InfinityFree)
                try:
                    result = response.json()
                    print(f"  ✅ Published! → {result.get('link')}")
                    return result
                except json.JSONDecodeError:
                    if response.text.strip() == '':
                        print(f"  ✅ Published! (empty response but 200 OK)")
                        print(f"  🔗 Check: {WP_SITE_URL}/?p=latest")
                        return {'status': 'published', 'link': WP_SITE_URL}
                    else:
                        print(f"  ❌ Unexpected response: {response.text[:200]}")
            elif response.status_code == 401:
                print("  ❌ 401 - Wrong username or password")
                print(f"  {response.text[:200]}")
                return None
            elif response.status_code == 403:
                print("  ❌ 403 - Permission denied")
                print(f"  {response.text[:200]}")
                return None
            elif response.status_code == 500:
                print("  ❌ 500 - WordPress server error")
                print(f"  {response.text[:200]}")
            else:
                print(f"  ❌ Failed: {response.status_code}")
                print(f"  {response.text[:200]}")

        except requests.exceptions.ConnectionError as e:
            print(f"  ❌ Connection error: {str(e)[:100]}")
        except requests.exceptions.Timeout:
            print(f"  ❌ Timeout - server took too long")
        except Exception as e:
            print(f"  ❌ Error: {str(e)[:100]}")

    print("  ❌ All 3 attempts failed")
    return None

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
        print("\n⚠️  No tweets found. Add to manual_tweets.json to test.\n")
        return

    processed_ids = [
        str(t['id']) if isinstance(t, dict) else str(t)
        for t in get_processed_tweets()
    ]

    new_tweets = [
        t for t in tweets
        if str(t['id']) not in processed_ids
    ]

    # Limit to 3 per run
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

        sources = research_topic(
            tweet.get('quoted_text') or tweet['text']
        )
        time.sleep(2)

        article = generate_article(tweet, sources)
        if not article:
            fail_count += 1
            continue

        result = publish_to_wordpress(article, tweet)
        if result:
            save_processed_tweet(str(tweet['id']))
            success_count += 1
            print(f"\n🎉 Tweet {i} done!")
        else:
            fail_count += 1

        if i < len(new_tweets):
            print("\n⏳ Waiting 5 seconds...")
            time.sleep(5)

    print("\n" + "="*50)
    print("📊 SUMMARY")
    print("="*50)
    print(f"  ✅ Success: {success_count}")
    print(f"  ❌ Failed:  {fail_count}")
    print("="*50)
    print("🎉 BOT COMPLETE!\n")

if __name__ == "__main__":
    main()
