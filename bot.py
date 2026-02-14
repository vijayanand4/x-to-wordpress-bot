import requests
import json
import os
from google import genai
from datetime import datetime
import time
import tweepy

# Configuration from GitHub Secrets
X_USERNAME = os.getenv('X_USERNAME')
HASHTAG = os.getenv('HASHTAG')
WP_SITE_URL = os.getenv('WP_SITE_URL').rstrip('/')
WP_USERNAME = os.getenv('WP_USERNAME')
WP_PASSWORD = os.getenv('WP_PASSWORD')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# X API credentials
X_API_KEY = os.getenv('X_API_KEY')
X_API_SECRET = os.getenv('X_API_SECRET')
X_ACCESS_TOKEN = os.getenv('X_ACCESS_TOKEN')
X_ACCESS_TOKEN_SECRET = os.getenv('X_ACCESS_TOKEN_SECRET')

print(f"🤖 Bot starting for X user: @{X_USERNAME}")
print(f"🔍 Looking for hashtag: {HASHTAG}")
print(f"📝 Will post to: {WP_SITE_URL}")

# Initialize Gemini
# genai.configure(api_key=GEMINI_API_KEY)
# model = genai.GenerativeModel('gemini-pro')
genai_client = genai.Client(api_key=GEMINI_API_KEY)

# Initialize X API (Twitter API v2)
client = tweepy.Client(
    consumer_key=X_API_KEY,
    consumer_secret=X_API_SECRET,
    access_token=X_ACCESS_TOKEN,
    access_token_secret=X_ACCESS_TOKEN_SECRET
)

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
        'id': tweet_id,
        'processed_at': datetime.now().isoformat()
    })
    with open('processed_tweets.json', 'w') as f:
        json.dump(processed, f, indent=2)
    print(f"✅ Saved tweet {tweet_id} as processed")

def get_user_id():
    """Get user ID from username"""
    try:
        user = client.get_user(username=X_USERNAME)
        if user.data:
            print(f"  ✅ Found user ID: {user.data.id}")
            return user.data.id
        else:
            print("  ❌ User not found")
            return None
    except Exception as e:
        print(f"  ❌ Error getting user ID: {str(e)}")
        return None

def fetch_user_tweets():
    """Fetch recent tweets using X API v2"""
    print(f"🔎 Fetching tweets from @{X_USERNAME} using X API...")
    
    try:
        user_id = get_user_id()
        if not user_id:
            return []
        
        # Fetch user's tweets (last 100)
        response = client.get_users_tweets(
            id=user_id,
            max_results=100,
            tweet_fields=['created_at', 'text', 'referenced_tweets'],
            expansions=['referenced_tweets.id']
        )
        
        if not response.data:
            print("  ⚠️  No tweets found")
            return []
        
        print(f"  ✅ Found {len(response.data)} total tweets")
        
        # Filter for quote tweets with hashtag
        quote_tweets = []
        
        for tweet in response.data:
            # Check if it's a quote tweet
            is_quote = False
            quoted_tweet_id = None
            
            if tweet.referenced_tweets:
                for ref in tweet.referenced_tweets:
                    if ref.type == 'quoted':
                        is_quote = True
                        quoted_tweet_id = ref.id
                        break
            
            # Check if it has the hashtag
            has_hashtag = HASHTAG.lower() in tweet.text.lower()
            
            if is_quote and has_hashtag:
                # Get the quoted tweet text
                quoted_text = ""
                if response.includes and 'tweets' in response.includes:
                    for included_tweet in response.includes['tweets']:
                        if included_tweet.id == quoted_tweet_id:
                            quoted_text = included_tweet.text
                            break
                
                quote_tweets.append({
                    'id': tweet.id,
                    'text': tweet.text,
                    'quoted_text': quoted_text,
                    'url': f"https://x.com/{X_USERNAME}/status/{tweet.id}"
                })
                
                print(f"  ✅ Found quote tweet: {tweet.id}")
        
        print(f"🎯 Found {len(quote_tweets)} quote tweets with hashtag {HASHTAG}")
        return quote_tweets
        
    except Exception as e:
        print(f"  ❌ Error fetching tweets: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

def research_topic(tweet_text):
    """Research using DuckDuckGo"""
    print("🔬 Researching topic...")
    
    # Clean the search query
    search_query = tweet_text.replace(HASHTAG, '').strip()[:150]
    
    try:
        # DuckDuckGo Instant Answer API
        ddg_url = "https://api.duckduckgo.com/"
        params = {
            'q': search_query,
            'format': 'json',
            'no_html': 1,
            'skip_disambig': 1
        }
        
        response = requests.get(ddg_url, params=params, timeout=10)
        data = response.json()
        
        sources = []
        
        # Get main abstract
        if data.get('AbstractURL'):
            sources.append({
                'title': data.get('AbstractSource', 'Source'),
                'url': data.get('AbstractURL'),
                'snippet': data.get('AbstractText', '')[:300]
            })
        
        # Get related topics
        for topic in data.get('RelatedTopics', [])[:4]:
            if isinstance(topic, dict) and topic.get('FirstURL'):
                sources.append({
                    'title': topic.get('Text', 'Related Topic').split(' - ')[0][:100],
                    'url': topic.get('FirstURL'),
                    'snippet': topic.get('Text', '')[:300]
                })
        
        print(f"  ✅ Found {len(sources)} sources")
        return sources
        
    except Exception as e:
        print(f"  ❌ Research error: {str(e)}")
        return []

def generate_article(tweet, sources):
    """Generate article using Gemini"""
    print("✍️  Generating article with AI...")
    
    if not sources:
        sources_text = "No external sources found. Write based on the quoted tweet content."
    else:
        sources_text = "\n".join([
            f"- {s['title']}: {s['snippet']} (URL: {s['url']})"
            for s in sources
        ])
    
    prompt = f"""You are a professional blogger. Write an informative article based on this information:

ORIGINAL TWEET: {tweet['text']}

QUOTED TWEET (main topic): {tweet.get('quoted_text', '')}

RESEARCH SOURCES:
{sources_text}

REQUIREMENTS:
- Write exactly 300 words
- Create an engaging title
- Write in clear paragraphs (no bullet points in main text)
- Be informative and educational
- Include all source URLs as clickable references at the end
- Make it readable and engaging

FORMAT:
Title: [Engaging Title Here]

[First paragraph introducing the topic]

[Second paragraph with main information]

[Third paragraph with additional context]

[Concluding paragraph]

References:
1. [Source name](URL)
2. [Source name](URL)

Original tweet: {tweet['url']}
"""
    
    try:
        response = genai_client.models.generate_content(
        model='gemini-2.0-flash',
        contents=prompt
        )
        article = response.text
        print("  ✅ Article generated successfully")
        return article
    except Exception as e:
        print(f"  ❌ Generation error: {str(e)}")
        return None

def publish_to_wordpress(article, tweet):
    """Publish to WordPress"""
    print("📤 Publishing to WordPress...")
    
    if not article:
        print("  ❌ No article to publish")
        return None
    
    # Parse title and content
    lines = article.split('\n')
    title_line = [l for l in lines if l.strip().startswith('Title:')]
    
    if title_line:
        title = title_line[0].replace('Title:', '').strip()
        content_start = lines.index(title_line[0]) + 1
        content = '\n'.join(lines[content_start:]).strip()
    else:
        title = "Article from X"
        content = article
    
    # Convert markdown links to HTML
    import re
    content = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2">\1</a>', content)
    
    # WordPress API endpoint
    wp_api_url = f"{WP_SITE_URL}/wp-json/wp/v2/posts"
    
    post_data = {
        'title': title,
        'content': content,
        'status': 'publish',
        'excerpt': f"Generated from X quote tweet: {tweet['url']}"
    }
    
    try:
        response = requests.post(
            wp_api_url,
            json=post_data,
            auth=(WP_USERNAME, WP_PASSWORD),
            timeout=30
        )
        
        if response.status_code in [200, 201]:
            result = response.json()
            print(f"  ✅ Published successfully!")
            print(f"  📝 Post URL: {result.get('link')}")
            return result
        else:
            print(f"  ❌ Publish failed: {response.status_code}")
            print(f"  Response: {response.text[:200]}")
            return None
            
    except Exception as e:
        print(f"  ❌ Publish error: {str(e)}")
        return None

def main():
    print("\n" + "="*50)
    print("🚀 X TO WORDPRESS BOT STARTED")
    print("="*50 + "\n")
    
    # Get tweets using X API
    tweets = fetch_user_tweets()
    
    if not tweets:
        print("\n❌ No quote tweets found with hashtag. Exiting.\n")
        return
    
    processed_ids = [str(t['id']) if isinstance(t, dict) else str(t) for t in get_processed_tweets()]
    
    new_tweets = [t for t in tweets if str(t['id']) not in processed_ids]
    
    if not new_tweets:
        print(f"\n✅ All {len(tweets)} tweets already processed. Nothing to do!\n")
        return
    
    print(f"\n📊 Processing {len(new_tweets)} new tweets...\n")
    
    for i, tweet in enumerate(new_tweets, 1):
        print(f"\n--- TWEET {i}/{len(new_tweets)} ---")
        print(f"ID: {tweet['id']}")
        print(f"Text: {tweet['text'][:100]}...")
        
        # Research
        sources = research_topic(tweet.get('quoted_text', tweet['text']))
        
        # Wait a bit to avoid rate limits
        time.sleep(2)
        
        # Generate
        article = generate_article(tweet, sources)
        
        if not article:
            print("⚠️  Skipping this tweet due to generation error")
            continue
        
        # Publish
        result = publish_to_wordpress(article, tweet)
        
        if result:
            save_processed_tweet(str(tweet['id']))
            print("✅ Complete!")
        else:
            print("❌ Failed to publish")
        
        # Be nice to APIs
        time.sleep(3)
    
    print("\n" + "="*50)
    print("🎉 BOT FINISHED SUCCESSFULLY")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
