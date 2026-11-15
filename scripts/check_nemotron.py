"""Check NVIDIA hosted API access. Uses Python's standard library only."""
import json
import os
import sys
import urllib.error
import urllib.request

MODEL = 'nvidia/nemotron-3.5-super-vl-120b-a12b'
URL = 'https://integrate.api.nvidia.com/v1/chat/completions'


def main():
    key = os.environ.get('NVIDIA_API_KEY', '').strip()
    if not key:
        print('NVIDIA_API_KEY is empty. Set it in this same PowerShell window.', file=sys.stderr)
        return 1
    payload = dict(model=MODEL,
        messages=[{'role': 'user', 'content': 'Reply with exactly READY.'}],
        temperature=0, max_tokens=128, stream=False,
        chat_template_kwargs={'enable_thinking': False})
    request = urllib.request.Request(URL, data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
    print(f'Contacting NVIDIA model: {MODEL}', flush=True)
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            result = json.load(response)
        text = result['choices'][0]['message']['content']
        if not isinstance(text, str) or not text.strip():
            raise ValueError('No answer text returned')
    except urllib.error.HTTPError as exc:
        messages = {400: 'NVIDIA rejected the request parameters.',
            401: 'NVIDIA rejected the API key.',
            403: 'This account/key does not have access to the requested model.',
            404: 'The model or endpoint was not found.',
            429: 'NVIDIA rate or quota limit reached. Try again later.'}
        print(f'HTTP {exc.code}: {messages.get(exc.code, "NVIDIA API request failed.")}',
            file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f'Network request failed ({type(exc).__name__}). Check connectivity and retry.',
            file=sys.stderr)
        return 1
    except (ValueError, KeyError, IndexError, TypeError):
        print('NVIDIA returned an unexpected or empty response.', file=sys.stderr)
        return 1
    print(f'Connection successful. Model response: {text.strip()}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
