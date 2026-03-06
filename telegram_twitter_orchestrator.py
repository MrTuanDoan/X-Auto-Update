import os
import json
import logging
import subprocess
from datetime import datetime
import tweepy
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

# =============================================================================
# ENV GLOBALS & CONFIGURATION (Make sure to export these before running)
# =============================================================================
# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
ALLOWED_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "123456789")) # Protect your bot!

# Twitter API v2 (Need Basic/Pro tier or Free tier if limits allow)
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")

# Target custom following IDs (Instead of full following pipeline, which might hit limits, 
# you can define specific tech/KOL accounts you want to track)
TARGET_TWITTER_HANDLES = ["techhalla", "godofprompt"] # Example: Replace with your favorites

# Workspace config
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "outputs", "usecases")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Central memory to track bot states
# structure: { chat_id: { "state": "IDLE" | "WAITING_TWEET_SELECTION" | "WAITING_USECASE_APPROVAL" | "WAITING_POST_APPROVAL", "pending_tweets": [], "pending_usecase": "", "pending_tweet": "" } }
app_state = {}

# =============================================================================
# LOGGING
# =============================================================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =============================================================================
# TWITTER MODULE
# =============================================================================
def init_twitter_client():
    client = tweepy.Client(
        bearer_token=TWITTER_BEARER_TOKEN,
        consumer_key=TWITTER_API_KEY,
        consumer_secret=TWITTER_API_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_SECRET
    )
    return client

from playwright.sync_api import sync_playwright

def scan_target_tweets():
    """Scrape recent tweets from predefined target handles using Playwright."""
    STATE_FILE = os.path.join(WORKSPACE_DIR, "twitter_state.json")
    if not os.path.exists(STATE_FILE):
        return ["⚠️ ERROR: Cannot find twitter_state.json. Please run `python twitter_auth.py` first to log in."]
        
    logger.info("Starting headless Playwright scraper...")
    all_tweets = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                storage_state=STATE_FILE,
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            for handle in TARGET_TWITTER_HANDLES:
                logger.info(f"Scraping @{handle}...")
                page.goto(f"https://twitter.com/{handle}", wait_until="networkidle")
                
                # Wait for tweets to appear
                try:
                    page.wait_for_selector('article[data-testid="tweet"]', timeout=15000)
                except Exception:
                    logger.warning(f"Could not find tweets for @{handle} (Timeout or Private Account)")
                    continue
                
                # Fetch top 5 tweets
                articles = page.locator('article[data-testid="tweet"]').all()[:5]
                
                for article in articles:
                    tweet_text_locator = article.locator('[data-testid="tweetText"]')
                    if tweet_text_locator.count() > 0:
                        text = tweet_text_locator.inner_text().strip()
                        if text:
                            # Replace new lines to save space
                            all_tweets.append(f"From @{handle}: {text.replace(chr(10), ' ')}")
                            
            browser.close()
            return all_tweets
    except Exception as e:
        logger.error(f"Playwright Error: {e}")
        return [f"Debug Mock Tweet: Playwright failed. Error: {e}"]

def execute_git_commands(filepath):
    """Commit the file to Git and push to remote."""
    try:
        subprocess.run(["git", "add", filepath], cwd=WORKSPACE_DIR, check=True)
        message = f"docs(ai): add scaffold usecase {os.path.basename(filepath)}"
        subprocess.run(["git", "commit", "-m", message], cwd=WORKSPACE_DIR, check=True)
        subprocess.run(["git", "push"], cwd=WORKSPACE_DIR, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Git execution failed: {e}")
        return False

# =============================================================================
# AI MODULE (Using Claude Code CLI)
# =============================================================================
def call_claude_cli(prompt_text):
    """Call Claude Code directly using the -p command."""
    try:
        logger.info("Executing Claude CLI. This might take a minute...")
        # Put prompt in a temporary file inside WORKSPACE_DIR to ensure Claude can access it
        import tempfile
        with tempfile.NamedTemporaryFile('w', dir=WORKSPACE_DIR, delete=False, encoding='utf-8', suffix='.txt') as f:
            f.write(prompt_text)
            temp_path = f.name
        
        # We tell Claude CLI to read the file and execute its contents.
        # This will trigger the available /scaffold and /cot commands in Claude Code's environment.
        process = subprocess.run(
            ["claude", "-p", f"Read the prompt inside {temp_path}. Execute it exactly as requested. Produce only the final answer."],
            capture_output=True,
            text=True,
            encoding='utf-8',
            cwd=WORKSPACE_DIR
        )
        
        os.remove(temp_path)
        
        if process.returncode != 0:
            logger.error(f"Claude CLI error: {process.stderr}")
            return f"# Error from Claude CLI\n\n{process.stderr}"
            
        return process.stdout.strip()
    except Exception as e:
        logger.error(f"Exception calling Claude CLI: {e}")
        return f"Error executing Claude: {e}"

def ai_generate_scaffold_usecase(tweets):
    """
    Uses Claude Code explicitly calling the /scaffold framework.
    """
    tweet_context = "\n".join(tweets)
    
    prompt = f"""
/scaffold Analyze these recent tweets and propose a single, compelling, and highly practical Use Case or mini-project.
Break down the problem clearly. Use /cot for step-by-step reasoning if necessary.
Make sure your output strictly follows the Scaffold Analysis template (DECOMPOSE -> SOLVE -> VERIFY).

TWEETS CONTEXT:
{tweet_context}
    """
    return call_claude_cli(prompt)

def ai_draft_final_tweet(scaffold_markdown):
    """Takes the approved scaffold use case and drafts exactly 1 viral tweet thread for the personal timeline using Claude."""
    prompt = f"""
Based on the following Scaffold Use Case document, draft a highly engaging, concise, and professional Twitter post (or short thread) summarizing the idea for my personal account.
Make it sound insightful but grounded in practical application. No corny hashtags.
Just output the tweet text and nothing else.

SCAFFOLD DOCUMENT:
{scaffold_markdown}
    """
    return call_claude_cli(prompt)

# =============================================================================
# TELEGRAM BOT HANDLERS
# =============================================================================
async def restrict_access(update: Update) -> bool:
    """Ensure only the owner can use this bot."""
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        logger.warning(f"Unauthorized access! User Chat ID: {update.effective_chat.id} | Allowed Chat ID: {ALLOWED_CHAT_ID}")
        await update.message.reply_text(f"⛔ Unauthorized access. Your Chat ID is {update.effective_chat.id}.")
        return False
    return True

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await restrict_access(update): return
    await update.message.reply_text(
        "👋 Welcome! Available commands:\n"
        "/scan - Fetch recent tweets and list them for your selection.\n"
        "/analyze 1,3 - Analyze the selected tweets, generate Use Case, and Push to GitHub.\n"
        "/approve_usecase - Approve the Use Case and generate a draft tweet.\n"
        "/approve_post - Approve the draft and post to your Twitter timeline.\n"
        "/cancel - Abort current operation."
    )

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await restrict_access(update): return
    chat_id = update.effective_chat.id
    
    await update.message.reply_text("🔍 Starting Headless Browser (Playwright) to scrape latest target accounts...")
    tweets = scan_target_tweets()
    
    if not tweets:
        await update.message.reply_text("⚠️ No tweets found or API limits reached. (Check console logs). Aborting.")
        return
        
    # Store fetched tweets
    app_state[chat_id] = {
        "state": "WAITING_TWEET_SELECTION",
        "pending_tweets": tweets
    }
    
    await update.message.reply_text(f"✅ Fetched {len(tweets)} recent tweets. Here they are:")
    
    # Send tweets out nicely formatted with index
    # Note: Telegram message limit is 4096 chars, so we send them in chunks or one by one
    for idx, t in enumerate(tweets):
        await update.message.reply_text(f"*[{idx + 1}]* {t}", parse_mode='Markdown')
        
    await update.message.reply_text("➡️ Decide which ones are interesting! Reply with `/analyze 1,3` or `/analyze 2` to start the AI Scaffold Analysis.", parse_mode='Markdown')

async def analyze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await restrict_access(update): return
    chat_id = update.effective_chat.id
    state = app_state.get(chat_id, {})
    
    if state.get("state") != "WAITING_TWEET_SELECTION" or "pending_tweets" not in state:
        await update.message.reply_text("⚠️ No pending tweets to analyze. Please run /scan first.")
        return
        
    if not context.args:
        await update.message.reply_text("⚠️ Please provide indices of tweets to analyze, e.g., `/analyze 1,3`", parse_mode='Markdown')
        return

    # Parse args (could be '1,3' or '1', '2' etc)
    raw_indices_str = "".join(context.args)
    try:
        selected_indices = [int(x.strip()) - 1 for x in raw_indices_str.split(',')]
    except ValueError:
        await update.message.reply_text("⚠️ Invalid format. Please use numbers separated by commas, e.g., `/analyze 1,3`", parse_mode='Markdown')
        return
        
    tweets = state["pending_tweets"]
    selected_tweets = []
    
    for idx in selected_indices:
        if 0 <= idx < len(tweets):
            selected_tweets.append(tweets[idx])
            
    if not selected_tweets:
        await update.message.reply_text("⚠️ None of the indices matched any tweets. Please try again.")
        return
        
    await update.message.reply_text(f"🤖 Running /cot and /scaffold AI generation on {len(selected_tweets)} selected tweets...")
    
    usecase_content = ai_generate_scaffold_usecase(selected_tweets)
    
    # Save file
    filename = f"scaffold-{datetime.now().strftime('%Y%m%d-%H%M%S')}-usecase.md"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(usecase_content)
        
    # Git
    await update.message.reply_text("📝 Document saved. Pushing to GitHub...")
    success = execute_git_commands(filepath)
    git_msg = "✅ Synced to GitHub." if success else "⚠️ Failed to sync to GitHub."
    
    # Store State for next step
    app_state[chat_id] = {
        "state": "WAITING_USECASE_APPROVAL",
        "pending_usecase": usecase_content
    }
    
    summary = usecase_content.split("## Final Proposed Use Case Summary:")[-1].strip()
    
    msg = (f"🎉 *Use Case Generated!*\n{git_msg}\n\n"
           f"*File:* `{filename}`\n\n"
           f"*Summary:*\n{summary}\n\n"
           f"➡️ Reply with /approve_usecase to implement this and draft a Tweet.\n"
           f"➡️ Or /cancel to ignore.")
           
    await update.message.reply_text(msg, parse_mode='Markdown')

async def approve_usecase_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await restrict_access(update): return
    chat_id = update.effective_chat.id
    state = app_state.get(chat_id, {})
    
    if state.get("state") != "WAITING_USECASE_APPROVAL":
        await update.message.reply_text("⚠️ No pending use case to approve. Run /scan first.")
        return
        
    await update.message.reply_text("🚀 Use case approved! ✍️ Implementing and drafting Twitter post...")
    
    draft_tweet = ai_draft_final_tweet(state["pending_usecase"])
    
    state["state"] = "WAITING_POST_APPROVAL"
    state["pending_tweet"] = draft_tweet
    
    msg = (f"📝 *Draft Tweet Ready:*\n\n"
           f"{draft_tweet}\n\n"
           f"➡️ Reply with /approve_post to PUBLISH directly to your Twitter timeline.\n"
           f"➡️ Or /cancel to ignore.")
    await update.message.reply_text(msg, parse_mode='Markdown')

async def approve_post_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await restrict_access(update): return
    chat_id = update.effective_chat.id
    state = app_state.get(chat_id, {})
    
    if state.get("state") != "WAITING_POST_APPROVAL":
        await update.message.reply_text("⚠️ No pending post to approve.")
        return
        
    tweet_text = state["pending_tweet"]
    await update.message.reply_text("🌐 Publishing to Twitter API...")
    
    try:
        # Note: Depending on length, it might need to be split into a thread.
        # This assumes a single tweet for simplicity.
        twitter_client = init_twitter_client()
        response = twitter_client.create_tweet(text=tweet_text[:280]) # Hard limit 280 chars
        logger.info(f"Tweet response: {response}")
        
        await update.message.reply_text("✅ BOOM! Your tweet is now live on your Twitter timeline!")
        # Reset state
        app_state[chat_id] = {"state": "IDLE"}
        
    except Exception as e:
        logger.error(f"Failed to post tweet: {e}")
        await update.message.reply_text(f"❌ Failed to post tweet. Error:\n{e}")

async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await restrict_access(update): return
    chat_id = update.effective_chat.id
    app_state[chat_id] = {"state": "IDLE"}
    await update.message.reply_text("🛑 Current workflow cancelled.")

# =============================================================================
# MAIN ORCHESTRATOR
# =============================================================================
def main():
    logger.info("Starting Telegram <-> Twitter Orchestrator...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("scan", scan_cmd))
    app.add_handler(CommandHandler("analyze", analyze_cmd))
    app.add_handler(CommandHandler("approve_usecase", approve_usecase_cmd))
    app.add_handler(CommandHandler("approve_post", approve_post_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))

    app.run_polling()

if __name__ == "__main__":
    main()
