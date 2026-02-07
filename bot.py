import requests
from bs4 import BeautifulSoup
import json
import os
import google.generativeai as genai
from datetime import datetime
import time

# Configuration from GitHub Secrets
X_USERNAME = os.getenv('X_USERNAME')
HASHTAG = os.getenv('HASHTAG')
WP_SITE_URL = os.getenv('WP_SITE_URL').rstrip('/')
WP_USERNAME = os.getenv('WP_USERNAME')
WP_PASSWORD = os.getenv('WP_PASSWORD')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

print(f"🤖 Bot starting for X user: @{X_USERNAME}")
print(f"🔍 Looking for hashtag: {HASHTAG}")
print(f"📝 Will post to: {WP_SITE_URL}")

# Initialize Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

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

def scrape_x_profile():
    """Scrape X profile via Nitter mirrors"""
    nitter_instances = [
        'https://nitter.poast.org',
        'https://nitter.privacydev.net',
        'https://nitter.net'
    ]
    
    print(f"🔎 Searching for tweets from @{X_USERNAME}...")
    
    for instance in nitter_instances:
        try:
            url = f"{instance}/{X_USERNAME}"
            print(f"  Trying {instance}...")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, timeout=15, headers=headers)
            
            if response.status_code == 200:
                print(f"  ✅ Successfully connected to {instance}")
                tweets = parse_tweets(response.text)
                if tweets:
                    return tweets
            else:
                print(f"  ❌ Failed: Status {response.status_code}")
        except Exception as e:
            print(f"  ❌ Error: {str(e)[:50]}")
            continue
    
    print("⚠️  Could not fetch tweets from any Nitter instance")
    return []

def parse_tweets(html):
    """Extract tweets from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    tweets = []
    
    # Find all tweet containers
    tweet_divs = soup.find_all('div', class_='timeline-item')
    print(f"  Found {len(tweet_divs)} total tweets")
    
    for tweet_div in tweet_divs[:10]:  # Check last 10 tweets
        try:
            # Get tweet text
            text_elem = tweet_div.find('div', class_='tweet-content')
            if not text_elem:
                continue
            
            text = text_elem.get_text(strip=True)
            
            # Check if it contains the hashtag
            if HASHTAG.lower() not in text.lower():
                continue
            
            # Check if it's a quote tweet (has quoted tweet in it)
            quote_elem = tweet_div.find('div', class_='quote')
            if not quote_elem:
                continue
            
            # Extract tweet ID from link
            link_elem = tweet_div.find('a', class_='tweet-link')
            if link_elem:
                tweet_url = link_elem.get('href', '')
                tweet_id = tweet_url.split('/')[-1].replace('#m', '')
            else:
                continue
            
            quoted_text = quote_elem.get_text(strip=True)
            
            tweets.append({
                'id': tweet_id,
                'text': text,
                'quoted_text': quoted_text,
                'url': f"https://x.com/{X_USERNAME}/status/{tweet_id}"
            })
            
            print(f"  ✅ Found quote tweet with {HASHTAG}: {tweet_id}")
            
        except Exception as e:
            print(f"  ⚠️  Error parsing tweet: {str(e)[:50]}")
            continue
    
    print(f"🎯 Found {len(tweets)} quote tweets with hashtag {HASHTAG}")
    return tweets

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
        response = model.generate_content(prompt)
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
    
    # Get tweets
    tweets = scrape_x_profile()
    
    if not tweets:
        print("\n❌ No quote tweets found with hashtag. Exiting.\n")
        return
    
    processed_ids = [t['id'] if isinstance(t, dict) else t for t in get_processed_tweets()]
    
    new_tweets = [t for t in tweets if t['id'] not in processed_ids]
    
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
            save_processed_tweet(tweet['id'])
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
