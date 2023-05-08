
import http.client
import json
import os
import re
import ssl
import sys
import uuid

AZ_ENDPOINT = "api.cognitive.microsofttranslator.com"
AZ_KEY = os.getenv("AZ_KEY") or "d2b873c5a3f14e72b65221700a948df6"
AZ_REGION = "koreacentral"



def get_translation(text: str, language_to: str, language_from: str = None) -> str:
    
    conn = http.client.HTTPSConnection(AZ_ENDPOINT, context=ssl._create_unverified_context())

    payload = json.dumps([{
        "text": text
    }])

    _headers = {
        'Ocp-Apim-Subscription-Key': AZ_KEY,
        'Ocp-Apim-Subscription-Region': AZ_REGION,
        'Content-type': 'application/json',
        'X-ClientTraceId': '099e49c3-68f8-4432-adf3-df2a8463a3e5'
    }

    # az_path = f"/translate?api-version=3.0&from={language_from}&to={language_to}"
    az_path = f"/translate?api-version=3.0&to={language_to}"
    if language_from:
        az_path += f"&from={language_from}"
    
    conn.request("POST", url=az_path, body=payload, headers=_headers)
    res = conn.getresponse()
    _response = res.read()
    _response = json.loads(_response)
    _response = _response.pop()

    translations = _response['translations']
    detected_language = language_from if language_from else _response['detectedLanguage']['language']

    for translation in translations:
        if translation['to'] == language_to:
            return detected_language, translation['text']

    return "Blank Translation"


def text_shuffle(text: str) -> str:
    # 去除字符串头尾的空白字符
    text = text.strip()
    # "- " 和 "-\n" 表示连字符，直接去除
    # "( +)" 表示匹配一个或多个空格
    text = re.sub(r"-( +|\t|\n)", repl="", string=text)
    text = re.sub(r"( +|\t)", repl=" ", string=text)
    # "_" 下划线连字符替换成空格
    text = re.sub(r"_", repl=" ", string=text)
    # \x02 是一个连字符，显示为: information
    return re.sub(r"(\x02|\t|\n)", repl="", string=text)



def is_english_word(text: str) -> bool:
    # en_pattern = r'^\s*[a-zA-Z]+\s*[a-zA-Z]*\s*$'     # 匹配单词和词组
    en_pattern = r'^\s*[a-zA-Z]+\s*$'       # 仅匹配单词
    re.findall(en_pattern, text)
    return True if re.match(en_pattern, text) else False


def is_chinese(text: str) -> int:
    # 如果出现平假名或片假名
    jp_pattern = r'[\u3040-\u30ff]+'
    if re.search(jp_pattern, text, flags=re.UNICODE):
        return 0

    # 如果包含两个汉字，则认为该语句为中文
    # 简体和繁体：[\u4E00-\u9FFF]， 简体：[\u4E00-\u9FA5]
    zh_pattern = r'[\u4E00-\u9FFF]{2,}'
    return re.search(zh_pattern, text)


def assemble_html_body(src_text: str, language_from: str , translated_text: str) -> str:
    css_text = """\
    <style type="text/css">
    p {white-space: pre-wrap;}
    pos {color: #0000FF;}
    example {color: #008080;}
    gray {color: #606060;}
    </style>"""
    aaa1 = "\\\int_{-\\\infty}^{\\\infty} e^{-x^2} dx"

    # print(f'<html>\n<head>\n{css_text}\n<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.13.11/dist/katex.min.css">\n<script src="https://cdn.jsdelivr.net/npm/katex@0.13.11/dist/katex.min.js"></script></head>\n<body>\n<p>{src_text}</p>\n<div id="math"></div>\n<script>katex.render("{aaa1}", document.getElementById("math"));</script>\n</body>\n</html>')
    # print(f'<html>\n<head>\n{css_text}\n</head>\n<body>\n<p>{src_text}</p>\n</body>\n</html>')


    # \x02 是一个不显示的空字符，用作占位符使得html可以渲染空行
    first_line = f"Language From: {language_from}" if language_from != 'en' else ""
    return f"{first_line}<br/>{src_text}<br/><br/>{translated_text}<br/>\x02"



def main():
    if len(sys.argv) <= 1:
        print("Please append text for translate.")
        return None

    src_text = sys.argv[1]
    # src_text = "so  information can be aggregated from different spatiotemporal locations"

    src_text = text_shuffle(src_text)

    # 英语单词或词组直接查本地词典
    if is_english_word(src_text):
        return None
    
    # 如果只有一个汉字，直接查询本地词典
    if re.match(r'^[\u4E00-\u9FFF]$', src_text):
        return None

    language_to = "en" if is_chinese(src_text) else "zh-Hans"

    language_from, translated_text = get_translation(src_text, language_to)

    print(assemble_html_body(src_text, language_from, translated_text))





if __name__ == '__main__':
    main()
