import requests
import json
import os
from google import genai
from datetime import datetime
import time
import re
import xml.etree.ElementTree as ET

# ============================================
# CONFIGURATION - Load from GitHub Secrets
# ============================================
X_USERNAME = os.getenv('X_USERNAME', '')
HASHTAG = os.getenv('HASHTAG', '')
WP_SITE_URL = os.getenv('WP_SITE_URL', '').rstrip('/')
WP_USERNAME = os.getenv('WP_USERNAME', '')
WP_PASSWORD = os.getenv('WP_PASSWORD', '')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')

# ============================================
# STARTUP CHECKS
# ============================================
print("\n" + "="*50)
print("🚀 X TO WORDPRESS BOT STARTED")
print("="*50 + "\n")

print("🔍 Configuration Check:")
print(f"  X Username:      {'✅' if X_USERNAME else '❌ MISSING'}")
print(f"  Hashtag:         {'✅' if HASHTAG else '❌ MISSING'}")
print(f"  WP Site URL:     {'✅' if WP_SITE_URL else '❌ MISSING'}")
print(f"  WP Username:     {'✅' if WP_USERNAME else '❌ MISSING'}")
print(f"  WP Password:     {'✅' if WP_PASSWORD else '❌ MISSING'}")
print(f"  Gemini API Key:  {'✅' if GEMINI_API_KEY else '❌ MISSING'}")

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

# ============================================
# INITIALIZE GEMINI
# ============================================
try:
    genai_client = genai.Client(api_key=GEMINI_API_KEY)
    print("✅ Gemini AI initialized\n")
except Exception as e:
    print(f"❌ Gemini initialization failed: {str(e)}")
    exit(1)

# ============================================
# PROCESSED TWEETS TRACKING
# ============================================

def get_processed_tweets():
    try:
        with open('processed_tweets.json', 'r') as f:
            data = json.load(f)
            print(f"📋 Found {len(data)} previously processed tweets")
            return data
    except FileNotFoundError:
        print("📋 Starting fresh - no previous tweets")
        return []

def save_processed_tweet(tweet_id):
    processed = get_processed_tweets()
    processed.append({
        'id': str(tweet_id),
        'processed_at': datetime.now().isoformat()
    })
    with open('processed_tweets.json', 'w') as f:
        json.dump(processed, f, indent=2)
    print(f"✅ Saved tweet {tweet_id} as processed")

# ============================================
# RSS FEED PARSING
# ============================================

def fetch_tweets_via_rss():
    """Fetch tweets using Nitter RSS feed"""
    
    nitter_instances = [
        'https://nitter.net',
        'https://nitter.poast.org',
        'https://nitter.privacydev.net',
        'https://nitter.lucabased.xyz',
        'https://nitter.lunar.icu'
    ]
    
    print(f"📡 Fetching RSS feed for @{X_USERNAME}...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    for instance in nitter_instances:
        rss_url = f"{instance}/{X_USERNAME}/rss"
        print(f"  Trying: {rss_url}")
        
        try:
            response = requests.get(
                rss_url,
                headers=headers,
                timeout=15
            )
            
            print(f"  Status: {response.status_code}")
            
            if response.status_code == 200 and '<rss' in response.text:
                print(f"  ✅ Got RSS feed! ({len(response.text)} chars)")
                tweets = parse_rss(response.text)
                if tweets is not None:
                    return tweets
            else:
                print(f"  ❌ Invalid response")
                
        except Exception as e:
            print(f"  ❌ Error: {str(e)[:60]}")
            continue
    
    print("❌ Could not fetch RSS from any instance")
    return []

def parse_rss(xml_content):
    """Parse RSS XML and extract quote tweets with hashtag"""
    print("\n🔍 Parsing RSS feed...")
    
    try:
        root = ET.fromstring(xml_content)
        
        # Handle XML namespaces
        namespace = ''
        if 'http' in xml_content[:200]:
            try:
                ns_match = re.search(r'xmlns="([^"]+)"', xml_content[:500])
                if ns_match:
                    namespace = f"{{{ns_match.group(1)}}}"
            except:
                pass
        
        # Find all items
        items = root.findall('.//item')
        print(f"  Found {len(items)} total items in RSS")
        
        if len(items) == 0:
            print("  ⚠️  No items found in RSS feed")
            return []
        
        quote_tweets = []
        
        for item in items:
            try:
                # Get title (tweet text)
                title_elem = item.find('title')
                title = title_elem.text if title_elem is not None else ''
                
                # Get description (full tweet HTML)
                desc_elem = item.find('description')
                description = desc_elem.text if desc_elem is not None else ''
                
                # Get link
                link_elem = item.find('link')
                link = link_elem.text if link_elem is not None else ''
                
                # Get tweet ID from link
                tweet_id = link.split('/')[-1].replace('#m', '') if link else ''
                
                # Combine title and description for hashtag search
                full_text = f"{title} {description}"
                
                # Check for hashtag
                if HASHTAG.lower() not in full_text.lower():
                    continue
                
                print(f"\n  📌 Found tweet with {HASHTAG}!")
                print(f"     Title: {title[:80]}...")
                
                # Check if it's a quote tweet
                # Quote tweets contain a blockquote or "RT" style content
                is_quote = any([
                    'class="quote"' in description,
                    '<blockquote' in description,
                    'twitter-tweet' in description,
                    'RT @' in full_text,
                    'quote' in description.lower()
                ])
                
                print(f"     Is quote tweet: {is_quote}")
                
                # Extract quoted text from description HTML
                quoted_text = ''
                if description:
                    # Remove HTML tags to get plain text
                    clean_desc = re.sub(r'<[^>]+>', ' ', description)
                    clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()
                    quoted_text = clean_desc[:500]
                
                # Use title as main text (cleaner)
                tweet_text = title if title else clean_desc[:280]
                
                quote_tweets.append({
                    'id': tweet_id,
                    'text': tweet_text,
                    'quoted_text': quoted_text,
                    'url': link or f"https://x.com/{X_USERNAME}/status/{tweet_id}",
                    'is_confirmed_quote': is_quote
                })
                
                print(f"     ✅ Added to processing queue!")
                
            except Exception as e:
                print(f"  ⚠️  Error parsing item: {str(e)[:60]}")
                continue
        
        print(f"\n🎯 Found {len(quote_tweets)} tweets with {HASHTAG}")
        return quote_tweets
        
    except ET.ParseError as e:
        print(f"  ❌ XML parse error: {str(e)}")
        return []
    except Exception as e:
        print(f"  ❌ Unexpected error: {str(e)}")
        return []

# ============================================
# RESEARCH
# ============================================

def research_topic(text):
    """Research topic using DuckDuckGo"""
    print("\n🔬 Researching topic...")
    
    # Clean query
    query = re.sub(r'#\w+', '', text)
    query = re.sub(r'http\S+', '', query)
    query = query.strip()[:150]
    
    print(f"  Query: {query[:80]}...")
    
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
    """Generate article using Gemini"""
    print("\n✍️  Generating article...")
    
    sources_text = "\n".join([
        f"- {s['title']}: {s['snippet']} (URL: {s['url']})"
        for s in sources
    ]) if sources else "Use your general knowledge about this topic."
    
    prompt = f"""You are a professional blogger. Write a 300-word informative article.

TWEET: {tweet['text']}
CONTEXT: {tweet.get('quoted_text', 'N/A')[:300]}
SOURCES: {sources_text}

Write in this EXACT format:

Title: [Engaging title here]

[Opening paragraph - hook the reader and introduce topic]

[Main paragraph - key facts and information]

[Supporting paragraph - additional context and details]

[Closing paragraph - conclusion and why it matters]

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
        print(f"  ❌ Generation error: {str(e)}")
        return None

# ============================================
# WORDPRESS PUBLISHING
# ============================================

def publish_to_wordpress(article, tweet):
    """Publish to WordPress via REST API"""
    print("\n📤 Publishing to WordPress...")
    
    if not article:
        return None
    
    # Extract title
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
        title = f"Article: {tweet['text'][:60]}..."
        content = article
    
    # Convert markdown links to HTML
    content = re.sub(
        r'\[([^\]]+)\]\(([^\)]+)\)',
        r'<a href="\2">\1</a>',
        content
    )
    
    # Convert line breaks to HTML
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
                'excerpt': f"Auto-generated from: {tweet['url']}"
            },
            auth=(WP_USERNAME, WP_PASSWORD),
            timeout=30
        )
        
        print(f"  WordPress Status: {response.status_code}")
        
        if response.status_code in [200, 201]:
            result = response.json()
            print(f"  ✅ Published! → {result.get('link')}")
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
    # Step 1: Fetch tweets via RSS
    tweets = fetch_tweets_via_rss()
    
    if not tweets:
        print("\n⚠️  No tweets found with hashtag. Exiting.\n")
        return
    
    # Step 2: Check already processed
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
    
    print(f"\n📊 {len(new_tweets)} new tweet(s) to process!\n")
    
    # Step 3: Process each tweet
    for i, tweet in enumerate(new_tweets, 1):
        print(f"\n{'='*40}")
        print(f"TWEET {i} of {len(new_tweets)}")
        print(f"{'='*40}")
        
        # Research
        research_text = tweet.get('quoted_text') or tweet['text']
        sources = research_topic(research_text)
        time.sleep(2)
        
        # Generate article
        article = generate_article(tweet, sources)
        if not article:
            print("⚠️  Skipping - generation failed")
            continue
        
        # Publish
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
