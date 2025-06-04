import json
import re
import requests
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound

def get_video_id(url):
    regex = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(regex, url)
    if match:
        return match.group(1)
    return None

def get_proxy():
    """Fetch a proxy from Geonode and return a proxy dict for requests."""
    try:
        resp = requests.get(
            "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc",
            timeout=5
        )
        data = resp.json()
        for item in data.get('data', []):
            ip = item.get('ip')
            port = item.get('port')
            protocol = item.get('protocols', ['http'])[0]
            if ip and port:
                proxy_url = f"{protocol}://{ip}:{port}"
                return {"http": proxy_url, "https": proxy_url}
    except Exception:
        return None
    return None

def fetch_transcript(video_url, lang_codes=None):
    if lang_codes is None:
        lang_codes = ['en', 'bn', 'hi', 'ar']  # English, Bangla, Hindi, Arabic

    try:
        video_id = get_video_id(video_url)
        if not video_id:
            return {"error": "Invalid YouTube URL"}, 400

        proxy = get_proxy()
        if not proxy:
            return {"error": "Could not obtain a proxy."}, 500

        # Patch requests in youtube_transcript_api to use proxy
        orig_request = requests.request
        def proxy_request(method, url, **kwargs):
            kwargs['proxies'] = proxy
            kwargs['timeout'] = 10
            return orig_request(method, url, **kwargs)
        requests.request = proxy_request

        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=lang_codes)
        except NoTranscriptFound:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            found = False
            # Fallback: Try generated+translatable in bn, hi, ar
            for candidate in ['bn', 'hi', 'ar']:
                for t in transcript_list:
                    if t.is_generated and t.language_code == candidate and t.is_translatable:
                        transcript = t.translate('en').fetch()
                        found = True
                        break
                if found:
                    break
            if not found:
                return {"error": "No suitable transcripts found."}, 404

        transcript_text = "\n".join([item['text'] for item in transcript])
        return {"transcript": transcript_text}, 200
    except Exception as e:
        return {"error": str(e)}, 500
    finally:
        # Restore requests for serverless environments
        requests.request = requests.sessions.Session.request

def handler(request, response):
    if request.method == "POST":
        data = request.json
        url = data.get("url") if data else None
    else:
        url = request.args.get("url")
    if not url:
        response.status_code = 400
        response.headers['Content-Type'] = 'application/json'
        response.body = json.dumps({"error": "Missing YouTube URL parameter."})
        return response

    result, status = fetch_transcript(url)
    response.status_code = status
    response.headers['Content-Type'] = 'application/json'
    response.body = json.dumps(result)
    return response
