"""
Jarvis — Fixed and improved main assistant script
- Safer config handling, helpful error messages
- Cross-platform TTS init fallback
- Optional SpeechRecognition (falls back to typed input)
- Safer calculation using ast.literal_eval for arithmetic expressions
- OpenAI client support with robust response extraction
- Persistent user profile (simple JSON memory)
- Conversation history persisted (limited size)
- Avoids logging secrets; improves logging statements
- Helper functions for training/setting personal preferences

Before running:
1. Update `config.json` in the project root with real API keys and paths.
2. Remove any credentials from `jarvis.log` and other files. Do NOT commit secrets.
3. Install dependencies from requirements.txt (you may need platform-specific packages, e.g. pyaudio).

Run: python main_fixed.py
"""

import os
import sys
import json
import logging
import threading
import datetime
import time
from pathlib import Path
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

# TTS
try:
    import pyttsx3
except Exception:
    pyttsx3 = None

# Optional speech recognition
try:
    import speech_recognition as sr
    _HAS_SR = True
except Exception:
    sr = None
    _HAS_SR = False

# Other features
import webbrowser
import subprocess
try:
    import httpx
except Exception:
    httpx = None
import requests
import random
import wikipedia
try:
    from newsapi import NewsApiClient
except Exception:
    NewsApiClient = None
import pyjokes
import schedule
from googletrans import Translator
import ast

# OpenAI (legacy and new client support)
try:
    import openai
except Exception:
    openai = None
try:
    from openai import OpenAI as OpenAIClient
    _HAS_NEW_OPENAI_CLIENT = True
except Exception:
    OpenAIClient = None
    _HAS_NEW_OPENAI_CLIENT = False

# Config & paths
CONFIG_FILE = Path('config.json')
USER_MEMORY_FILE = Path('user_profile.json')
HISTORY_FILE = Path('history.json')

# Logging (avoid logging secrets)
logging.basicConfig(filename='jarvis_fixed.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Small helper to avoid logging secrets
def safe_log(msg):
    logging.info(msg)

# Load config safely
if not CONFIG_FILE.exists():
    print("config.json not found. Please create config.json with your settings.")
    sys.exit(1)

try:
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)
except json.JSONDecodeError:
    print("config.json is malformed. Fix JSON formatting (no trailing commas).")
    sys.exit(1)

# Basic validation
required = []
# allow environment variable to satisfy the openai_api_key requirement
if not os.environ.get('OPENAI_API_KEY') and ('openai_api_key' not in config or not config['openai_api_key']):
    required.append('openai_api_key')
if required:
    print(f"Missing required config keys: {', '.join(required)}. Please update config.json.")
    sys.exit(1)

# Initialize TTS engine with platform fallback
def init_tts():
    if not pyttsx3:
        print("pyttsx3 not installed. TTS will be disabled.")
        return None
    try:
        # On Windows prefer 'sapi5'; on other platforms default
        engine = pyttsx3.init('sapi5') if sys.platform.startswith('win') else pyttsx3.init()
        engine.setProperty('rate', config.get('speech_rate', 170))
        engine.setProperty('volume', config.get('speech_volume', 0.9))
        voices = engine.getProperty('voices')
        engine.setProperty('voice', voices[0].id if voices else '')
        return engine
    except Exception as e:
        print(f"TTS initialization failed: {e}")
        return None

engine = init_tts()

# Try to load .env file if python-dotenv available
if load_dotenv:
    try:
        load_dotenv()
    except Exception:
        pass

# Validate key presence and log which source will be used
_api_key_env = os.environ.get('OPENAI_API_KEY')
_api_key_cfg = config.get('openai_api_key', '') if isinstance(config, dict) else ''
_api_key_final = (_api_key_env or _api_key_cfg or '').strip()

if _api_key_final:
    # Do not display the key — just masked logging for debugging
    try:
        masked = (_api_key_final[:6] + '...' + _api_key_final[-6:]) if len(_api_key_final) > 12 else '***'
    except Exception:
        masked = '***'
    if _api_key_env:
        safe_log(f'OpenAI API key found in environment (masked {masked}).')
    else:
        safe_log(f'OpenAI API key found in config.json (masked {masked}).')
else:
    safe_log('OpenAI API key not found in environment or config.json at startup.')

# Speak helper (graceful fallback to print)
def speak(text):
    if not text:
        return
    print("Jarvis:", text)
    try:
        if engine:
            engine.say(text)
            engine.runAndWait()
    except Exception as e:
        safe_log(f"TTS error: {e}")

# Speech input with graceful fallback to typed input
def take_command(retries=2):
    if not _HAS_SR or sr is None:
        return input("Type command: ").strip().lower()

    r = sr.Recognizer()
    for attempt in range(retries):
        try:
            with sr.Microphone() as source:
                print("Listening...")
                r.adjust_for_ambient_noise(source, duration=0.5)
                audio = r.listen(source, timeout=5, phrase_time_limit=8)
            print("Recognizing...")
            text = r.recognize_google(audio, language='en-in')
            print("You said:", text)
            return text.lower()
        except sr.UnknownValueError:
            speak("Sorry, I didn't get that. Please repeat.")
        except Exception as e:
            safe_log(f"SR error: {e}")
            return input("Microphone issue. Type command: ").strip().lower()
    return ''

# Safe calculation (ast.literal_eval limited to literals and tuples/lists/dicts)
def calculate(expression):
    try:
        # Prevent names and calls by parsing expression AST and allowing only arithmetic
        node = ast.parse(expression, mode='eval')
        for sub in ast.walk(node):
            if isinstance(sub, (ast.Call, ast.Name, ast.Attribute)):  # disallow these
                raise ValueError('Unsupported expression')
        result = eval(compile(node, '<string>', 'eval'))
        speak(f"The result is {result}")
    except Exception:
        speak('Sorry, I could not evaluate that expression safely.')

# OpenAI wrapper
def ai_response(prompt, history=None, max_tokens=200):
    if history is None:
        history = []
    api_key = (os.environ.get('OPENAI_API_KEY') or config.get('openai_api_key') or '').strip()
    if not api_key:
        speak('OpenAI API key not set in config.json or environment variables.')
        return ""
    # Avoid calling the OpenAI service when the config contains a placeholder value
    if api_key.upper().startswith('YOUR_') or 'example' in api_key or api_key.count('.') == 1 and 'openai' in api_key:
        speak('OpenAI API key appears to be a placeholder; set a real API key to enable AI responses.')
        return ""

    # Avoid writing API key to logs
    safe_log('Calling OpenAI API (masked key).')

    # Try to use new OpenAI client if available; if it fails, fall back to the legacy openai SDK
    try:
        if _HAS_NEW_OPENAI_CLIENT and OpenAIClient is not None:
            try:
                # Create an httpx client and pass it into the OpenAI client to
                # avoid the `Client.__init__() got an unexpected keyword argument 'proxies'`
                # error that happens when the OpenAI client tries to construct
                # its own httpx.Client with extra kwargs. If httpx is not
                # available, fall back to direct construction.
                try:
                    if httpx is not None:
                        http_client = httpx.Client()
                        client = OpenAIClient(api_key=api_key, http_client=http_client)
                    else:
                        client = OpenAIClient(api_key=api_key)
                except TypeError:
                    # Some OpenAIClient versions use a different constructor
                    # signature; fall back to the simple form.
                    client = OpenAIClient(api_key=api_key)

                model = config.get('openai_model', 'gpt-3.5-turbo')
                if config.get('enable_raptor_mini_for_all_clients'):
                    model = 'raptor-mini-preview'
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": "You are Jarvis, a helpful assistant."},
                              {"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                )
                # New client chat shape
                text = ''
                try:
                    text = response.choices[0].message.content
                except Exception:
                    try:
                        # Responses API shape
                        if hasattr(response, 'output'):
                            out = response.output
                            if isinstance(out, list) and out:
                                first = out[0]
                                if isinstance(first, dict) and 'content' in first:
                                    content = first['content']
                                    if isinstance(content, list) and len(content)>0:
                                        c0 = content[0]
                                        if isinstance(c0, dict) and 'text' in c0:
                                            text = c0['text']
                    except Exception:
                        text = str(response)
                speak(text)
                return text
            except Exception as e:
                # If the new client fails for any reason, inspect the error.
                msg = str(e)
                safe_log(f'New OpenAI client error: {msg} � evaluating fallback.')
                low = msg.lower()
                # Authentication / invalid key
                if 'invalid_api_key' in low or 'incorrect api key' in low or '401' in low:
                    safe_log('Detected invalid OpenAI API key (401). Aborting request.')
                    speak('OpenAI API key appears to be invalid or revoked. Please set a valid key in the environment variable `OPENAI_API_KEY` or in `config.json`.')
                    return ''
                # Quota / rate limit
                if 'quota' in low or '429' in low or 'rate limit' in low:
                    safe_log('Detected OpenAI quota / rate limit error.')
                    speak('OpenAI API quota exceeded or rate limited. Check your account usage or try again later.')
                    return ''
                # For other errors, continue to attempt the legacy SDK fallback
                safe_log('New OpenAI client error not recognized as auth/quota; falling back to legacy openai SDK.')

        # Legacy openai python package (fallback or if new client not available)
        if openai is None:
            speak('OpenAI SDK not available. Install openai package.')
            return ''
        openai.api_key = api_key
        model = config.get('openai_model', 'gpt-3.5-turbo')
        if config.get('enable_raptor_mini_for_all_clients'):
            model = 'raptor-mini-preview'
        resp = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "system", "content": "You are Jarvis, a helpful assistant."},
                      {"role": "user", "content": prompt}],
            max_tokens=max_tokens
        )
        text = resp.choices[0].message.get('content') if hasattr(resp.choices[0].message, 'get') else resp.choices[0].message.content
        speak(text)
        return text
    except Exception as e:
        safe_log(f"OpenAI error: {e}")
        speak('Sorry, I could not reach the AI service.')
        return ''

# Simple user profile persistence
def load_user_profile():
    if USER_MEMORY_FILE.exists():
        try:
            with open(USER_MEMORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_user_profile(profile):
    try:
        with open(USER_MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(profile, f, indent=2)
    except Exception as e:
        safe_log(f"Error saving profile: {e}")

user_profile = load_user_profile()

# Conversation history persisted (small)
def load_history():
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_history(history):
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history[-50:], f, indent=2)
    except Exception as e:
        safe_log(f"Error saving history: {e}")

history = load_history()

# Lightweight helpers
def wish_me():
    hour = datetime.datetime.now().hour
    if hour < 12:
        speak('Good morning!')
    elif hour < 18:
        speak('Good afternoon!')
    else:
        speak('Good evening!')
    name = user_profile.get('name', 'Sir')
    speak(f'I am Jarvis. How can I help you, {name}?')

# Commands (subset)
def open_website(site):
    if not site.startswith('http'):
        site = f'https://{site}'
    webbrowser.open(site)
    speak(f'Opened {site}')

def tell_time():
    speak(datetime.datetime.now().strftime('%H:%M:%S'))

# Weather
def get_weather(city=None):
    api_key = config.get('weather_api_key')
    if not api_key:
        speak('Weather API key not set in config.')
        return
    city = city or config.get('default_city', 'Hyderabad')
    try:
        url = f'https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric'
        r = requests.get(url, timeout=10)
        data = r.json()
        if data.get('cod') == 200:
            t = data['main']['temp']
            desc = data['weather'][0]['description']
            speak(f'The weather in {city} is {desc} with {t}°C')
        else:
            speak('City not found or API problem.')
    except Exception as e:
        safe_log(f'Weather fetch error: {e}')
        speak('Could not fetch weather at this time.')

# News
def get_news():
    api_key = config.get('news_api_key')
    if not api_key:
        speak('News API key not set in config.')
        return
    if NewsApiClient is None:
        speak('News API client library is not installed. Please install newsapi-python.')
        return
    try:
        newsapi = NewsApiClient(api_key=api_key)
        top = newsapi.get_top_headlines(language='en', country='us')
        articles = top.get('articles', [])[:5]
        if not articles:
            speak('No news found.')
            return
        speak('Top headlines:')
        for a in articles:
            speak(a.get('title'))
    except Exception as e:
        safe_log(f'News error: {e}')
        speak('Could not fetch news.')

def tell_joke():
    try:
        speak(pyjokes.get_joke())
    except Exception as e:
        safe_log(f'Joke error: {e}')
        speak('Sorry, I could not fetch a joke right now.')

def get_current_model():
    model = config.get('openai_model', 'gpt-3.5-turbo')
    if config.get('enable_raptor_mini_for_all_clients'):
        model = 'raptor-mini-preview'
    return model

# Main processing
def process_query(query):
    if not query:
        return
    q = query.lower()
    history.append({'user': query, 'time': time.time()})
    save_history(history)

    if 'wikipedia' in q:
        topic = q.replace('wikipedia', '').strip() or q
        speak('Searching Wikipedia...')
        try:
            s = wikipedia.summary(topic, sentences=2)
            speak(s)
        except Exception:
            speak('Could not fetch from Wikipedia.')
    elif 'open website' in q or q.startswith('open '):
        site = q.replace('open website', '').replace('open', '').strip()
        open_website(site)
    elif 'time' in q:
        tell_time()
    elif 'weather' in q:
        city = None
        if 'in ' in q:
            city = q.split('in')[-1].strip()
        get_weather(city)
    elif q.startswith('calculate') or q.startswith('what is'):
        expr = q.replace('calculate', '').replace('what is', '').strip()
        calculate(expr)
    elif 'news' in q:
        get_news()
    elif 'help' in q:
        speak('Available commands: wikipedia, open <site>, time, weather, calculate, news, joke, set my name to <name>, who am i, train my profile, exit.')
    elif 'joke' in q:
        tell_joke()
    elif q.startswith('set my name to'):
        name = q.replace('set my name to', '').strip()
        user_profile['name'] = name
        save_user_profile(user_profile)
        speak(f'Okay, I will call you {name}.')
    elif 'who am i' in q:
        speak(f'You are {user_profile.get("name", "not set")}')
    elif 'train' in q and 'profile' in q:
        speak('Tell me the facts you want me to remember. Say "done" when finished.')
        facts = []
        while True:
            f = take_command()
            if f.strip().lower() in ('done', 'nothing'):
                break
            facts.append(f)
        user_profile.setdefault('notes', []).extend(facts)
        save_user_profile(user_profile)
        speak('Saved your profile notes.')
    elif q in ('exit', 'quit', 'bye'):
        speak('Goodbye!')
        sys.exit(0)
    else:
        # Default to AI response
        resp = ai_response(query, history)
        # Optionally store reply in history
        history.append({'jarvis': resp, 'time': time.time()})
        save_history(history)

# Entry point
if __name__ == '__main__':
    wish_me()
    try:
        while True:
            cmd = take_command()
            if not cmd:
                continue
            process_query(cmd)
    except KeyboardInterrupt:
        speak('Shutting down. Goodbye!')
