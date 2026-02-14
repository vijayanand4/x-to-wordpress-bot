import requests
import json
import os
from google import genai
from datetime import datetime
import time
import re

# ============================================
# CONFIGURATION - Load from GitHub Secrets
# ============================================
X_USERNAME = os.getenv('X_USERNAME', '')
HASHTAG = os.getenv('HASHTAG', '')
WP_SITE_URL = os.getenv('WP_SITE_URL', '').rstrip('/')
WP_USERNAME = os.getenv('WP_USERNAME', '')
WP_PASSWORD = os.getenv('WP_PASSWORD', '')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
X_BEARER_TOKEN = os.getenv('X_BEARER_TOKEN', '')

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
print(f"  Bearer Token:    {'✅ Present (' + str(len(X_BEARER_TOKEN)) + ' chars)' if X_BEARER_TOKEN else '❌ MISSING'}")

# Stop if critical secrets are missing
missing = []
if not X_USERNAME: missing.append('X_USERNAME')
if not HASHTAG: missing.append('HASHTAG')
if not WP_SITE_URL: missing.append('WP_SITE_URL')
if not WP_USERNAME: missing.append('WP_USERNAME')
if not WP_PASSWORD: missing.append('WP_PASSWORD')
if not GEMINI_API_KEY: missing.append('GEMINI_API_KEY')
if not X_BEARER_TOKEN: missing.append('X_BEARER_TOKEN')

if missing:
    print(f"\n❌ MISSING SECRETS: {', '.join(missing)}")
    print("Please add these to GitHub Secrets and try again.")
    exit(1)

print("\n✅ All secrets loaded successfully!\n")

# ============================================
# INITIALIZE GEMINI
# ============================================
try:
    genai_client = genai.Client(api_key=GEMINI_API_KEY)
    print("✅ Gemini AI initialized")
except Exception as e:
    print(f"❌ Gemini initialization failed: {str(e)}")
    exit(1)

# ============================================
# HELPER FUNCTIONS
# ============================================

def get_processed_tweets():
    """Load already processed tweet IDs"""
    try:
        with open('processed_tweets.json', 'r') as f:
            data = json.load(f)
            print(f"📋 Found {len(data)} previously processed tweets")
            return data
    except FileNotFoundError:
        print("📋 No previous tweets found, starting fresh")
        return []

def save_processed_tweet(tweet_id):
    """Save processed tweet ID"""
    processed = get_processed_tweets()
    processed.append({
        'id': str(tweet_id),
        'processed_at': datetime.now().isoformat()
    })
    with open('processed_tweets.json', 'w') as f:
        json.dump(processed, f, indent=2)
    print(f"✅ Saved tweet {tweet_id} as processed")

def get_headers():
    """Get X API authorization headers"""
    return {
        'Authorization': f'Bearer {X_BEARER_TOKEN}',
        'Content-Type': 'application/json'
    }

# ============================================
# X API FUNCTIONS
# ============================================

def get_user_id():
    """Get X user ID from username"""
    print(f"\n🔎 Looking up @{X_USERNAME} on X...")
    
    url = f"https://api.twitter.com/2/users/by/username/{X_USERNAME}"
    
    try:
        response = requests.get(
            url,
            headers=get_headers(),
            timeout=15
        )
        
        print(f"  API Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            user_id = data['data']['id']
            print(f"  ✅ Found user ID: {user_id}")
            return user_id
            
        elif response.status_code == 401:
            print(f"  ❌ 401 Unauthorized")
            print(f"  Full response: {response.text}")
            print(f"  → Your Bearer Token is invalid or expired")
            print(f"  → Please regenerate it at developer.twitter.com")
            return None
            
        elif response.status_code == 403:
            print(f"  ❌ 403 Forbidden")
            print(f"  Full response: {response.text}")
            print(f"  → Your app may not have permission to read user data")
            return None
            
        elif response.status_code == 429:
            print(f"  ❌ 429 Rate Limited - Too many requests")
            return None
            
        else:
            print(f"  ❌ Unexpected status: {response.status_code}")
            print(f"  Full response: {response.text}")
            return None
            
    except Exception as e:
        print(f"  ❌ Request failed: {str(e)}")
        return None

def fetch_user_tweets(user_id):
    """Fetch recent tweets from user"""
    print(f"\n📥 Fetching tweets for user {user_id}...")
    
    url = f"https://api.twitter.com/2/users/{user_id}/tweets"
    params = {
        'max_results': 100,
        'tweet.fields': 'created_at,text,referenced_tweets',
        'expansions': 'referenced_tweets.id'
    }
    
    try:
        response = requests.get(
            url,
            headers=get_headers(),
            params=params,
            timeout=15
        )
        
        print(f"  API Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            count = len(data.get('data', []))
            print(f"  ✅ Fetched {count} tweets")
            return data
        else:
            print(f"  ❌ Error: {response.text[:300]}")
            return None
            
    except Exception as e:
        print(f"  ❌ Request failed: {str(e)}")
        return None

def process_tweets(tweets_data):
    """Filter for quote tweets containing hashtag"""
    print(f"\n🔍 Scanning tweets for hashtag {HASHTAG}...")
    
    if not tweets_data or 'data' not in tweets_data:
        print("  ⚠️  No tweet data to process")
        return []
    
    tweets = tweets_data['data']
    includes = tweets_data.get('includes', {})
    included_tweets = {
        t['id']: t for t in includes.get('tweets', [])
    }
    
    print(f"  Total tweets to scan: {len(tweets)}")
    
    quote_tweets = []
    
    for tweet in tweets:
        text = tweet.get('text', '')
        
        # Check for hashtag
        if HASHTAG.lower() not in text.lower():
            continue
        
        print(f"  📌 Found tweet with hashtag: {text[:60]}...")
        
        # Check if it's a quote tweet
        refs = tweet.get('referenced_tweets', [])
        quoted_ref = next(
            (r for r in refs if r['type'] == 'quoted'),
            None
        )
        
        if not quoted_ref:
            print(f"     ⚠️  Has hashtag but is not a quote tweet, skipping")
            continue
        
        # Get the quoted tweet's text
        quoted_tweet = included_tweets.get(quoted_ref['id'], {})
        quoted_text = quoted_tweet.get('text', '')
        
        quote_tweets.append({
            'id': tweet['id'],
            'text': text,
            'quoted_text': quoted_text,
            'url': f"https://x.com/{X_USERNAME}/status/{tweet['id']}"
        })
        
        print(f"     ✅ Valid quote tweet found!")
    
    print(f"\n🎯 Total valid quote tweets: {len(quote_tweets)}")
    return quote_tweets

# ============================================
# RESEARCH FUNCTION
# ============================================

def research_topic(tweet_text):
    """Research topic using DuckDuckGo"""
    print("\n🔬 Researching topic...")
    
    search_query = tweet_text.replace(HASHTAG, '').strip()[:150]
    print(f"  Search query: {search_query[:80]}...")
    
    try:
        response = requests.get(
            "https://api.duckduckgo.com/",
            params={
                'q': search_query,
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
        print(f"  ❌ Research failed: {str(e)}")
        return []

# ============================================
# ARTICLE GENERATION
# ============================================

def generate_article(tweet, sources):
    """Generate 300-word article using Gemini"""
    print("\n✍️  Generating article with Gemini AI...")
    
    sources_text = "\n".join([
        f"- {s['title']}: {s['snippet']} (URL: {s['url']})"
        for s in sources
    ]) if sources else "No sources available. Use general knowledge."
    
    prompt = f"""You are a professional blogger. Write a 300-word article.

TWEET: {tweet['text']}
QUOTED TWEET: {tweet.get('quoted_text', 'N/A')}
SOURCES: {sources_text}

STRICT FORMAT - follow exactly:
Title: [Your engaging title here]

[Opening paragraph - introduce the topic]

[Main paragraph - key information and context]

[Supporting paragraph - additional details]

[Closing paragraph - conclusion and takeaway]

References:
1. [Source Name](URL)
2. [Source Name](URL)

Original Source: {tweet['url']}
"""
    
    try:
        response = genai_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt
        )
        print("  ✅ Article generated!")
        return response.text
    except Exception as e:
        print(f"  ❌ Generation failed: {str(e)}")
        return None

# ============================================
# WORDPRESS PUBLISHING
# ============================================

def publish_to_wordpress(article, tweet):
    """Publish article to WordPress"""
    print("\n📤 Publishing to WordPress...")
    
    if not article:
        print("  ❌ No article content")
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
        title = f"Article: {tweet['text'][:50]}..."
        content = article
    
    # Convert markdown to HTML
    content = re.sub(
        r'\[([^\]]+)\]\(([^\)]+)\)',
        r'<a href="\2">\1</a>',
        content
    )
    content = content.replace('\n\n', '</p><p>')
    content = content.replace('\n', '<br>')
    content = f"<p>{content}</p>"
    
    print(f"  Title: {title}")
    print(f"  Posting to: {WP_SITE_URL}/wp-json/wp/v2/posts")
    
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
        
        print(f"  WordPress Response: {response.status_code}")
        
        if response.status_code in [200, 201]:
            result = response.json()
            print(f"  ✅ Published! URL: {result.get('link')}")
            return result
        else:
            print(f"  ❌ Failed: {response.text[:300]}")
            return None
            
    except Exception as e:
        print(f"  ❌ Publish error: {str(e)}")
        return None

# ============================================
# MAIN
# ============================================

def main():
    # Step 1: Get user ID
    user_id = get_user_id()
    if not user_id:
        print("\n❌ Cannot continue without user ID\n")
        exit(1)
    
    # Step 2: Fetch tweets
    tweets_data = fetch_user_tweets(user_id)
    if not tweets_data:
        print("\n❌ Cannot continue without tweets\n")
        exit(1)
    
    # Step 3: Filter quote tweets
    tweets = process_tweets(tweets_data)
    if not tweets:
        print("\n⚠️  No new quote tweets with hashtag found\n")
        return
    
    # Step 4: Skip already processed
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
    
    print(f"\n📊 {len(new_tweets)} new tweet(s) to process\n")
    
    # Step 5: Process each tweet
    for i, tweet in enumerate(new_tweets, 1):
        print(f"\n{'='*40}")
        print(f"PROCESSING TWEET {i} of {len(new_tweets)}")
        print(f"{'='*40}")
        print(f"Text: {tweet['text'][:100]}...")
        
        sources = research_topic(
            tweet.get('quoted_text', tweet['text'])
        )
        time.sleep(2)
        
        article = generate_article(tweet, sources)
        if not article:
            print("⚠️  Skipping - article generation failed")
            continue
        
        result = publish_to_wordpress(article, tweet)
        if result:
            save_processed_tweet(str(tweet['id']))
            print("\n✅ Tweet fully processed!")
        else:
            print("\n❌ Failed to publish")
        
        time.sleep(3)
    
    print("\n" + "="*50)
    print("🎉 BOT RUN COMPLETE!")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
