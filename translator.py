import http.client
import json
import os
import re
import ssl
import sys
import uuid

AZ_ENDPOINT = "api.cognitive.microsofttranslator.com"
AZ_KEY = os.getenv("AZ_KEY") or "d4e72b65221700a948df6"
AZ_REGION = "koreacentral"



def get_translation(text: str, language_from: str, language_to: str) -> str:
    
    conn = http.client.HTTPSConnection(AZ_ENDPOINT, context=ssl._create_unverified_context())

    payload = json.dumps([{
        "text": text
    }])

    _headers = {
        'Ocp-Apim-Subscription-Key': AZ_KEY,
        'Ocp-Apim-Subscription-Region': AZ_REGION,
        'Content-type': 'application/json',
        'X-ClientTraceId': '099e49c3-68f8-aacf-adf3-df2a8463a3e5'
    }

    az_path = f"/translate?api-version=3.0&from={language_from}&to={language_to}"

    conn.request("POST", url=az_path, body=payload, headers=_headers)
    res = conn.getresponse()
    _response = res.read()
    _response = json.loads(_response)
    translations = _response.pop()['translations']
    for translation in translations:
        if translation['to'] == language_to:
            return translation['text']


def text_shuffle(text: str) -> str:
    # 去除字符串头尾的空白字符
    text = text.strip()
    # "- " 和 "-\n" 表示连字符，直接去除
    # "( +)" 表示匹配一个或多个空格
    text = re.sub(r"-( +|\t|\n)", repl="", string=text)
    # "_" 下划线连字符替换成空格
    text = re.sub(r"_", repl=" ", string=text)
    # \x02 是一个连字符，显示为: information
    return re.sub(r"(\x02|\t|\n)", repl="", string=text)


def is_chinese(text: str) -> bool:
    _count = 0
    for _char in text:
        if '\u4e00' <= _char <= '\u9fa5':
            _count += 1
            # 如果包含三个汉字，则认为该语句为中文
            if _count >= 3:
                return True
    return False


def assemble_html_body(src_text: str, translated_text: str) -> str:
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
    return f"<br/>\n{src_text}<br/><br/>{translated_text}<br/>\x02"



def main():
    if len(sys.argv) <= 1:
        print("Please append text for translate.")
        return None

    src_text = sys.argv[1]
    # src_text = "so  information can be aggregated from different spatiotemporal locations"

    src_text = text_shuffle(src_text)

    if is_chinese(src_text):
        language_from, language_to = ("zh-Hans", "en")
    else:
        # 如果不是中文，并且单词个数少于2个，则直接使用本地词典
        if len(src_text.split(" ")) <= 1:
            return None
        language_from, language_to = ("en", "zh-Hans")

    text = get_translation(src_text, language_from, language_to)

    print(assemble_html_body(src_text, text))





if __name__ == '__main__':
    main()
