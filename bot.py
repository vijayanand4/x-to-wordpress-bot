import requests
import json
import os
from google import genai
from datetime import datetime
import time
import re
import base64
import xml.etree.ElementTree as ET

# ============================================
# CONFIGURATION
# ============================================
X_USERNAME = os.getenv('X_USERNAME', '')
HASHTAG = os.getenv('HASHTAG', '')
WP_SITE_URL = os.getenv('WP_SITE_URL', '').rstrip('/')
WP_USERNAME = os.getenv('WP_USERNAME', '')
WP_PASSWORD = os.getenv('WP_PASSWORD', '')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')

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
print(f"  Gemini API Key: {'✅' if GEMINI_API_KEY else '❌ MISSING'}")

missing = []
if not X_USERNAME: missing.append('X_USERNAME')
if not HASHTAG: missing.append('HASHTAG')
if not WP_SITE_URL: missing.append('WP_SITE_URL')
if not WP_USERNAME: missing.append('WP_USERNAME')
if not WP_PASSWORD: missing.append('WP_PASSWORD')
if not GEMINI_API_KEY: missing.append('GEMINI_API_KEY')

if missing:
    print(f"\n❌ MISSING SECRETS: {', '.join(missing)}")
    exit(1)

print("\n✅ All secrets loaded!\n")

# Initialize Gemini
try:
    genai_client = genai.Client(api_key=GEMINI_API_KEY)
    print("✅ Gemini AI initialized\n")
except Exception as e:
    print(f"❌ Gemini init failed: {str(e)}")
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
        print(f"  Response preview: {response.text[:150]}")

        if response.status_code == 200 and response.text.strip():
            try:
                data = response.json()
                tweets = extract_from_syndication(data)
                if tweets:
                    return tweets
                else:
                    print("  ⚠️  No matching tweets found in syndication data")
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
        print(f"  Found {len(entries)} entries in timeline")

        quote_tweets = []

        for entry in entries:
            tweet = entry.get('tweet', {})
            text = tweet.get('full_text', tweet.get('text', ''))

            if not text:
                continue

            if HASHTAG.lower() not in text.lower():
                continue

            print(f"  📌 Found tweet with hashtag: {text[:60]}...")

            quoted = tweet.get('quoted_status', {})
            is_quote = bool(quoted)

            if not is_quote:
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
# METHOD 2: ALLORIGINS PROXY + BASE64 DECODE
# ============================================

def fetch_via_twstalker():
    """Try allorigins proxy with base64 decode support"""
    print("\n📡 Method 2: AllOrigins RSS Proxy...")

    nitter_url = f'https://nitter.net/{X_USERNAME}/rss'
    proxy_url = f"https://api.allorigins.win/get?url={requests.utils.quote(nitter_url)}"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }

    try:
        response = requests.get(proxy_url, headers=headers, timeout=20)
        print(f"  Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            content = data.get('contents', '')

            if not content:
                print("  ❌ Empty content received")
                return None

            # Handle base64 encoded response
            if content.startswith('data:'):
                print("  📦 Base64 encoded content detected, decoding...")
                try:
                    base64_data = content.split(',', 1)[1]
                    content = base64.b64decode(base64_data).decode('utf-8')
                    print(f"  ✅ Decoded successfully! ({len(content)} chars)")
                except Exception as e:
                    print(f"  ❌ Decode error: {str(e)}")
                    return None

            print(f"  Content preview: {content[:100]}")

            if '<rss' in content or '<item>' in content:
                print("  ✅ Valid RSS content found!")
                return parse_rss_content(content)
            else:
                print("  ❌ No RSS content found after decode")

    except Exception as e:
        print(f"  ❌ Error: {str(e)[:80]}")

    return None

def parse_rss_content(xml_content):
    """Parse RSS XML and find quote tweets with hashtag"""
    print("\n  🔍 Parsing RSS content...")

    try:
        root = ET.fromstring(xml_content)
        items = root.findall('.//item')
        print(f"  Found {len(items)} items in RSS")

        if len(items) == 0:
            print("  ⚠️  No items in RSS feed")
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

            # Check hashtag
            if HASHTAG.lower() not in full_text.lower():
                continue

            print(f"  📌 Found tweet with hashtag: {title[:60]}...")

            # Get tweet ID
            tweet_id = link.split('/')[-1].replace('#m', '') if link else str(int(time.time()))

            # Clean HTML from description
            clean_desc = re.sub(r'<[^>]+>', ' ', description)
            clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()

            # Check if quote tweet
            is_quote = any([
                'class="quote"' in description,
                '<blockquote' in description,
                'RT @' in full_text,
                'quote' in description.lower()
            ])

            print(f"     Is quote: {is_quote}")

            quote_tweets.append({
                'id': tweet_id,
                'text': title,
                'quoted_text': clean_desc[:500],
                'url': link or f"https://x.com/{X_USERNAME}/status/{tweet_id}"
            })

            print(f"     ✅ Added: {tweet_id}")

        return quote_tweets if quote_tweets else None

    except ET.ParseError as e:
        print(f"  ❌ XML parse error: {str(e)}")
        return None
    except Exception as e:
        print(f"  ❌ Unexpected error: {str(e)}")
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
            print("  ℹ️  manual_tweets.json is empty")
            return None

        data = json.loads(content)

        if not data:
            print("  ℹ️  No tweets in manual_tweets.json")
            return None

        print(f"  ✅ Found {len(data)} manual tweet(s)!")

        # Validate each tweet has required fields
        valid_tweets = []
        for i, tweet in enumerate(data):
            if not tweet.get('id'):
                print(f"  ⚠️  Tweet {i+1} missing 'id' field, skipping")
                continue
            if not tweet.get('url'):
                tweet['url'] = f"https://x.com/{X_USERNAME}/status/{tweet['id']}"
            if not tweet.get('text'):
                tweet['text'] = HASHTAG
            if not tweet.get('quoted_text'):
                tweet['quoted_text'] = ''
            valid_tweets.append(tweet)

        print(f"  ✅ {len(valid_tweets)} valid tweet(s) ready to process")
        return valid_tweets if valid_tweets else None

    except json.JSONDecodeError as e:
        print(f"  ❌ JSON format error: {str(e)}")
        print("  💡 Make sure your JSON is valid at jsonlint.com")
        return None
    except FileNotFoundError:
        print("  ℹ️  manual_tweets.json not found")
        return None
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None

# ============================================
# RESEARCH
# ============================================

def research_topic(text):
    """Research topic using DuckDuckGo"""
    print("\n🔬 Researching topic...")

    # Clean query - remove hashtags and URLs
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
        print(f"  ❌ Research error: {str(e)}")
        return []

# ============================================
# ARTICLE GENERATION
# ============================================

def generate_article(tweet, sources):
    """Generate 300-word article using Gemini"""
    print("\n✍️  Generating article...")

    sources_text = "\n".join([
        f"- {s['title']}: {s['snippet']} (URL: {s['url']})"
        for s in sources
    ]) if sources else "Use your general knowledge about this topic."

    prompt = f"""You are a professional blogger and journalist. 
Write a well-researched 300-word article based on the following:

TWEET: {tweet['text']}
QUOTED CONTENT: {tweet.get('quoted_text', 'N/A')[:300]}
RESEARCH SOURCES: {sources_text}

Use this EXACT format - do not deviate:

Title: [Write an engaging, informative title here]

[Opening paragraph - hook the reader, introduce the topic clearly]

[Main paragraph - key facts, background, and important details]

[Supporting paragraph - additional context, implications, or analysis]

[Closing paragraph - conclusion, takeaway, or call to action]

References:
1. [Source Name](URL)
2. [Source Name](URL)

Original Tweet: {tweet['url']}

Remember: Exactly 300 words, professional tone, factual and informative.
"""

    try:
        response = genai_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt
        )
        print("  ✅ Article generated!")
        return response.text
    except Exception as e:
        print(f"  ❌ Generation error: {str(e)}")
        return None

# ============================================
# WORDPRESS PUBLISHING
# ============================================

def publish_to_wordpress(article, tweet):
    """Publish article to WordPress via REST API"""
    print("\n📤 Publishing to WordPress...")

    if not article:
        print("  ❌ No article to publish")
        return None

    # Extract title and content
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

    # Remove ** bold markdown
    content = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', content)

    # Convert markdown links to HTML
    content = re.sub(
        r'\[([^\]]+)\]\(([^\)]+)\)',
        r'<a href="\2">\1</a>',
        content
    )

    # Convert line breaks to HTML paragraphs
    content = content.replace('\n\n', '</p><p>')
    content = content.replace('\n', '<br>')
    content = f"<p>{content}</p>"

    print(f"  Title: {title[:70]}")
    print(f"  Posting to: {WP_SITE_URL}/wp-json/wp/v2/posts")

    try:
        response = requests.post(
            f"{WP_SITE_URL}/wp-json/wp/v2/posts",
            json={
                'title': title,
                'content': content,
                'status': 'publish',
                'excerpt': f"Auto-generated article from tweet: {tweet['url']}"
            },
            auth=(WP_USERNAME, WP_PASSWORD),
            timeout=30
        )

        print(f"  WordPress Response: {response.status_code}")

        if response.status_code in [200, 201]:
            result = response.json()
            print(f"  ✅ Successfully published!")
            print(f"  🔗 Post URL: {result.get('link')}")
            return result
        elif response.status_code == 401:
            print("  ❌ 401 Unauthorized - Check WP_USERNAME and WP_PASSWORD")
            print(f"  Response: {response.text[:200]}")
            return None
        elif response.status_code == 403:
            print("  ❌ 403 Forbidden - User may not have permission to post")
            print(f"  Response: {response.text[:200]}")
            return None
        else:
            print(f"  ❌ Failed with status {response.status_code}")
            print(f"  Response: {response.text[:300]}")
            return None

    except Exception as e:
        print(f"  ❌ Publish error: {str(e)}")
        return None

# ============================================
# MAIN
# ============================================

def main():
    print("🔄 Trying all methods to fetch tweets...\n")

    # Try all methods in order
    tweets = None

    tweets = fetch_via_syndication()

    if not tweets:
        tweets = fetch_via_twstalker()

    if not tweets:
        tweets = check_manual_tweets()

    if not tweets:
        print("\n" + "="*50)
        print("⚠️  COULD NOT FETCH TWEETS AUTOMATICALLY")
        print("="*50)
        print("""
All automatic methods failed.

MANUAL METHOD - Add your tweet to manual_tweets.json:
[
  {
    "id": "YOUR_TWEET_ID",
    "text": "Your tweet text #YourHashtag",
    "quoted_text": "The text of the tweet you quoted",
    "url": "https://x.com/yourusername/status/YOUR_TWEET_ID"
  }
]

Get your tweet ID from the URL when you open your tweet.
Example URL: https://x.com/username/status/1234567890123456789
                                              ^^^^^^^^^^^^^^^^^^^
                                              This is your tweet ID
""")
        return

    # Filter already processed tweets
    processed_ids = [
        str(t['id']) if isinstance(t, dict) else str(t)
        for t in get_processed_tweets()
    ]

    new_tweets = [
        t for t in tweets
        if str(t['id']) not in processed_ids
    ]

    if not new_tweets:
        print(f"\n✅ All {len(tweets)} tweet(s) already processed! Nothing to do.\n")
        return

    print(f"\n📊 Found {len(new_tweets)} new tweet(s) to process!\n")

    # Process each tweet
    success_count = 0
    fail_count = 0

    for i, tweet in enumerate(new_tweets, 1):
        print(f"\n{'='*40}")
        print(f"PROCESSING TWEET {i} of {len(new_tweets)}")
        print(f"{'='*40}")
        print(f"ID:   {tweet['id']}")
        print(f"Text: {tweet['text'][:100]}")
        print(f"URL:  {tweet['url']}")

        # Research the topic
        research_text = tweet.get('quoted_text') or tweet['text']
        sources = research_topic(research_text)
        time.sleep(2)

        # Generate article
        article = generate_article(tweet, sources)
        if not article:
            print("⚠️  Skipping - article generation failed")
            fail_count += 1
            continue

        # Publish to WordPress
        result = publish_to_wordpress(article, tweet)
        if result:
            save_processed_tweet(str(tweet['id']))
            success_count += 1
            print(f"\n🎉 Tweet {i} successfully processed!")
        else:
            fail_count += 1
            print(f"\n❌ Tweet {i} failed to publish")

        # Pause between tweets
        if i < len(new_tweets):
            print("\n⏳ Waiting 3 seconds before next tweet...")
            time.sleep(3)

    # Summary
    print("\n" + "="*50)
    print("📊 FINAL SUMMARY")
    print("="*50)
    print(f"  ✅ Successfully processed: {success_count}")
    print(f"  ❌ Failed: {fail_count}")
    print(f"  📝 Total: {len(new_tweets)}")
    print("="*50)
    print("🎉 BOT RUN COMPLETE!")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
