import requests
import json
import os
from google import genai
from datetime import datetime
import time
import re

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
# METHOD 1: SYNDICATION RSS
# ============================================

def fetch_via_syndication():
    """Use Twitter's own syndication API - no auth needed"""
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
        
        if response.status_code == 200:
            data = response.json()
            tweets = extract_from_syndication(data)
            if tweets:
                return tweets
        else:
            print(f"  ❌ Failed: {response.text[:100]}")
            
    except Exception as e:
        print(f"  ❌ Error: {str(e)[:80]}")
    
    return None

def extract_from_syndication(data):
    """Extract tweets from syndication response"""
    try:
        timeline = data.get('timeline', {})
        entries = timeline.get('entries', [])
        
        print(f"  Found {len(entries)} entries")
        
        quote_tweets = []
        
        for entry in entries:
            tweet = entry.get('tweet', {})
            text = tweet.get('full_text', tweet.get('text', ''))
            
            if not text:
                continue
            
            # Check hashtag
            if HASHTAG.lower() not in text.lower():
                continue
            
            # Check if quote tweet
            quoted = tweet.get('quoted_status', {})
            is_quote = bool(quoted)
            
            if not is_quote:
                continue
            
            tweet_id = tweet.get('id_str', '')
            quoted_text = quoted.get('full_text', quoted.get('text', ''))
            
            quote_tweets.append({
                'id': tweet_id,
                'text': text,
                'quoted_text': quoted_text,
                'url': f"https://x.com/{X_USERNAME}/status/{tweet_id}"
            })
            
            print(f"  ✅ Found quote tweet: {tweet_id}")
        
        return quote_tweets if quote_tweets else None
        
    except Exception as e:
        print(f"  ❌ Parse error: {str(e)}")
        return None

# ============================================
# METHOD 2: TWSTALKER / THIRD PARTY
# ============================================

def fetch_via_twstalker():
    """Try tweetscraper alternative"""
    print("\n📡 Method 2: Alternative scraper...")
    
    url = f"https://api.allorigins.win/get?url={requests.utils.quote(f'https://nitter.net/{X_USERNAME}/rss')}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=20)
        print(f"  Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            content = data.get('contents', '')
            
            if '<rss' in content or '<item>' in content:
                print(f"  ✅ Got RSS content!")
                return parse_rss_content(content)
            else:
                print(f"  ❌ No RSS content found")
                print(f"  Preview: {content[:100]}")
                
    except Exception as e:
        print(f"  ❌ Error: {str(e)[:80]}")
    
    return None

def parse_rss_content(xml_content):
    """Parse RSS XML content"""
    import xml.etree.ElementTree as ET
    
    try:
        root = ET.fromstring(xml_content)
        items = root.findall('.//item')
        
        print(f"  Found {len(items)} RSS items")
        
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
            
            tweet_id = link.split('/')[-1].replace('#m', '') if link else str(int(time.time()))
            
            # Clean description HTML
            clean_desc = re.sub(r'<[^>]+>', ' ', description)
            clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()
            
            # Check for quote indicators
            is_quote = any([
                'quote' in description.lower(),
                '<blockquote' in description,
                '&gt;' in description
            ])
            
            if not is_quote:
                print(f"  ⚠️  Has hashtag but may not be quote tweet")
            
            quote_tweets.append({
                'id': tweet_id,
                'text': title,
                'quoted_text': clean_desc[:500],
                'url': link
            })
            
            print(f"  ✅ Found tweet: {tweet_id}")
        
        return quote_tweets if quote_tweets else None
        
    except Exception as e:
        print(f"  ❌ RSS parse error: {str(e)}")
        return None

# ============================================
# METHOD 3: MANUAL ENTRY FALLBACK
# ============================================

def check_manual_tweets():
    """Check manually added tweets file as fallback"""
    print("\n📡 Method 3: Checking manual_tweets.json...")
    
    try:
        with open('manual_tweets.json', 'r') as f:
            data = json.load(f)
            
        if not data:
            print("  ℹ️  No manual tweets found")
            return None
            
        print(f"  ✅ Found {len(data)} manual tweet(s)!")
        return data
        
    except FileNotFoundError:
        print("  ℹ️  No manual_tweets.json file found")
        return None
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None

# ============================================
# RESEARCH
# ============================================

def research_topic(text):
    """Research using DuckDuckGo"""
    print("\n🔬 Researching topic...")
    
    query = re.sub(r'#\w+', '', text)
    query = re.sub(r'http\S+', '', query)
    query = query.strip()[:150]
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
    """Generate article using Gemini"""
    print("\n✍️  Generating article...")
    
    sources_text = "\n".join([
        f"- {s['title']}: {s['snippet']} (URL: {s['url']})"
        for s in sources
    ]) if sources else "Use your general knowledge."
    
    prompt = f"""You are a professional blogger. Write a 300-word article.

TWEET: {tweet['text']}
QUOTED CONTENT: {tweet.get('quoted_text', 'N/A')[:300]}
SOURCES: {sources_text}

Use this EXACT format:

Title: [Engaging title]

[Opening paragraph]

[Main information paragraph]

[Supporting details paragraph]

[Conclusion paragraph]

References:
1. [Source Name](URL)
2. [Source Name](URL)

Original Tweet: {tweet['url']}
"""
    
    try:
        response = genai_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt
        )
        print("  ✅ Article generated!")
        return response.text
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None

# ============================================
# WORDPRESS
# ============================================

def publish_to_wordpress(article, tweet):
    """Publish to WordPress"""
    print("\n📤 Publishing to WordPress...")
    
    if not article:
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
    
    # Markdown links → HTML
    content = re.sub(
        r'\[([^\]]+)\]\(([^\)]+)\)',
        r'<a href="\2">\1</a>',
        content
    )
    content = content.replace('\n\n', '</p><p>')
    content = content.replace('\n', '<br>')
    content = f"<p>{content}</p>"
    
    print(f"  Title: {title[:60]}")
    
    try:
        response = requests.post(
            f"{WP_SITE_URL}/wp-json/wp/v2/posts",
            json={
                'title': title,
                'content': content,
                'status': 'publish',
                'excerpt': f"From: {tweet['url']}"
            },
            auth=(WP_USERNAME, WP_PASSWORD),
            timeout=30
        )
        
        print(f"  Status: {response.status_code}")
        
        if response.status_code in [200, 201]:
            result = response.json()
            print(f"  ✅ Published → {result.get('link')}")
            return result
        else:
            print(f"  ❌ Failed: {response.text[:300]}")
            return None
            
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None

# ============================================
# MAIN
# ============================================

def main():
    # Try all methods to get tweets
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
All automatic methods failed. Here's what you can do:

MANUAL METHOD:
1. Find your quote tweet on X
2. Copy the tweet URL (looks like: https://x.com/username/status/1234567890)
3. Create a file called 'manual_tweets.json' in your GitHub repo
4. Add your tweet details like this:

[
  {
    "id": "1234567890",
    "text": "Your tweet text here #YourHashtag",
    "quoted_text": "The tweet you quoted text here",
    "url": "https://x.com/yourusername/status/1234567890"
  }
]

5. Run the workflow again - it will process your tweet!
""")
        return
    
    # Filter already processed
    processed_ids = [
        str(t['id']) if isinstance(t, dict) else str(t)
        for t in get_processed_tweets()
    ]
    
    new_tweets = [
        t for t in tweets
        if str(t['id']) not in processed_ids
    ]
    
    if not new_tweets:
        print(f"\n✅ All {len(tweets)} tweets already processed!\n")
        return
    
    print(f"\n📊 Processing {len(new_tweets)} new tweet(s)...\n")
    
    for i, tweet in enumerate(new_tweets, 1):
        print(f"\n{'='*40}")
        print(f"TWEET {i} of {len(new_tweets)}")
        print(f"{'='*40}")
        print(f"Text: {tweet['text'][:100]}")
        
        sources = research_topic(
            tweet.get('quoted_text') or tweet['text']
        )
        time.sleep(2)
        
        article = generate_article(tweet, sources)
        if not article:
            print("⚠️  Skipping - generation failed")
            continue
        
        result = publish_to_wordpress(article, tweet)
        if result:
            save_processed_tweet(str(tweet['id']))
            print("\n🎉 Successfully processed!")
        else:
            print("\n❌ Failed to publish")
        
        time.sleep(3)
    
    print("\n" + "="*50)
    print("🎉 BOT RUN COMPLETE!")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
