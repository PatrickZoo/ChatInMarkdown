# -*- encoding: utf-8 -*-
# @Author      : Daxing Zheng
# @Email       : laiguanqixi@gmail.com
# @Author      : Jun Zhou
# @Email       :
# @File        : chat.py
# @Datetime    : 2023-03-02 09:23:19
# @Github      : https://github.com/PatrickZoo/ChatInMarkdown
# @Description :

import datetime
import http.client
import io
import json
import logging
import logging.config
import os
import re
import ssl
import time
import traceback
from typing import List, Optional, Union
import uuid



# 读取本地配置文件内容
with open('./config/config.json', 'r', encoding="utf-8") as f:
    config = json.load(f)


OPENAI_URL = "https://api.openai.com/v1/chat/completions"
# 获取配置文件内容
OPENAI_API_KEY = config['OPENAI_API_KEY']
OUTPUT_FILE = config['OUTPUT_FILE']
LOG_FILE = config['LOG_FILE']
HISTORY_DIR = "./history"
HTTP_PROXY_SERVER = config['PROXY_HOST']  # https代理地址
HTTP_PROXY_PORT = config['PROXY_PORT']  # https代理端口

IGNORE_QUESTION = ["请另起一行输入问题:", "Runtime Message"]

MAGIC_HINT_LINE = "请另起一行输入问题:"


def file_modified(filepath: str) -> float:
    st_mtime = os.stat(filepath).st_mtime
    return st_mtime


def clear_file(filepath: str):
    with open(filepath, 'w', encoding="utf-8") as _f:
        _f.write(f"\n{MAGIC_HINT_LINE}\n")


def save_chat_history(filepath: str, newfilename: str):
    """
    输入参数：
    filepath: 需要操作的文件地址
    newfilename: 保存的文件名。默认值格式为: 月日_时分_UUID
    """
    newpath = os.path.join(HISTORY_DIR, newfilename)
    # 重命名文件并移动到新的地址上
    os.rename(filepath, newpath)
    clear_file(filepath)


def proxy_test() -> bool:
    conn = http.client.HTTPSConnection(HTTP_PROXY_SERVER, HTTP_PROXY_PORT, context=ssl._create_unverified_context())
    conn.set_tunnel("google.com")  # 设置需要访问的目标服务器
    try:
        conn.request("GET", "/")
        res = conn.getresponse()
        return True if res.status == 301 else False
    except Exception as e:
        logging.error(traceback.format_exc())
        return False


def format_time_now(format:str = "%Y-%m-%d %H:%M:%S") -> str:
    return datetime.datetime.now().strftime(format)


def clean_question(question: str) -> str:
    """
    对获取的问题做清洗
    """
    if question is None:
        return None

    if question.isspace() or question == "":
        return None

    if "Runtime Message" in question:
        return None

    if MAGIC_HINT_LINE in question:
        # question = re.sub(r'.*请另起一行输入问题:(.*)', r'\1', question).strip()
        question = re.sub(rf'.*{MAGIC_HINT_LINE}(.*)', r'\1', question).strip()
        if question == "":
            return None

    return question


def get_question(input_file: str) -> str:
    with open(input_file, 'rb') as f:
        file_lines = len(f.readlines())
        # 如果文件无内容
        if (file_lines < 1):
            clear_file(input_file)
            return None
        # 如果文件只有一行
        if (file_lines == 1):
            f.seek(0)  # 将文件指针移到文件开始处
            first_line = f.readline()
            # 删除换行符、零宽字符
            first_line = re.sub(r"([\u200B-\u200F]|\t|\n)", repl="", string=first_line)
            return first_line if not first_line.isspace() and first_line != "" else None

        # 移动文件指针到文件末尾，并倒退两个 bytes
        f.seek(-2, os.SEEK_END)
        last_line, pos = reverse_readline(f)
        if last_line:
            if "```" in last_line:
                return read_code_block(f, "```")
            elif last_line == "$$":
                return read_code_block(f, "$$")

        return last_line


def reverse_readline(f: io.BufferedReader) -> List[Union[str, int]]:
    """
    逆序读取文件行，忽略空白行
    @return 当前行字符串和当前文件指针
    """
    pos = f.tell()
    if pos < 0:
        return None, pos

    while True:
        # 将文件指针移动到当前行的上一行行尾
        # f.read(1)如果读取到'\n'，表示到达上一行行尾，同时文件指针会继续移动 1 个 bytes，会移动到当前行的行首
        while f.read(1) != b'\n':
            if f.tell() < 2:
                return None, f.tell()
            f.seek(-2, os.SEEK_CUR)

        # 记录当前指针位置(行首)
        pos = f.tell()
        last_line = f.readline().decode()
        # 删除零宽字符、制表符、换行符
        last_line = re.sub(r"([\u200B-\u200F]|\t|\n)", repl="", string=last_line)
        # 去除头尾的空字符后仍不为空
        if not last_line.isspace() and last_line != "":
            return last_line, pos

        # 如果当前行的内容为空或者都是空格，文件指针回到之前的位置的上一行
        # 如果 pos <= 2
        if pos <= 2:
            return None, pos
        f.seek(pos - 2)


def read_code_block(f: io.BufferedReader, block_type: str) -> str:
    """
    读取代码块类型的问题
    """
    lines = list()
    quotes_pair = 0

    # 匹配到一对 markdown 代码块标记 ``` ``` 或数学公式标记 $$ $$ 后停止
    while quotes_pair < 2:
        # 读取最后一行，并追加到list中
        last_line, pos = reverse_readline(f)
        if last_line is None:
            raise ValueError(f"markdown 代码块标记符不匹配")

        lines.append(last_line)
        if block_type in last_line:
            quotes_pair += 1
        f.seek(pos - 2)

    # 再读取代码块上一行内容作为 QUESTION
    last_line, pos = reverse_readline(f)

    last_line = clean_question(last_line)
    if last_line:
        lines.append(last_line)

    # 对 list 中内容逆序后给每一行添加换行符，组合成字符串
    lines.reverse()
    return '\n'.join(lines)


def ask_chatgpt(question: str) -> Optional[str]:
    _headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f"Bearer {OPENAI_API_KEY}"
    }
    payload = json.dumps({
        "model": "gpt-3.5-turbo",
        "messages": [
            {
                "role": "user",
                "content": question
            }
        ]
    })

    try:

        # socks.set_default_proxy(socks.SOCKS5, '127.0.0.1', 1088)
        # socket.socket = socks.socksocket

        # conn = http.client.HTTPSConnection("api.openai.com")
        # conn.set_tunnel("127.0.0.1", 10808)
        # 创建代理连接对象
        conn = http.client.HTTPSConnection(HTTP_PROXY_SERVER, HTTP_PROXY_PORT, context=ssl._create_unverified_context())
        conn.set_tunnel("api.openai.com")  # 设置需要访问的目标服务器
        conn.request("POST", "/v1/chat/completions", body=payload, headers=_headers)
        res = conn.getresponse()
        _response = res.read().decode()
        _response = json.loads(_response)

        if "error" in _response:
            logging.error(_response)
            return f"运行出错: {_response['error']['message']}"

        # _response = requests.post(OPENAI_URL, headers=_headers, data=payload, proxies=PROXIES)
        # _response = _response.json()
        _answer = _response["choices"].pop()["message"]["content"]

        usage_tokens = _response["usage"]["total_tokens"]
        return f"{_answer}\n**本次API调用共消耗 {usage_tokens} tokens.**"
    except Exception as e:
        logging.debug(traceback.format_exc())
        return repr(e)


def append_answer(answer: str, output_file: str):
    with open(output_file, 'a', encoding="utf-8") as f:
        f.write(f"\n==ANSWER ({format_time_now()})==\n")
        f.write(f"{answer}\n")
        f.write(f"\n{MAGIC_HINT_LINE}\n")
        logging.info(f"运行成功，请在 {OUTPUT_FILE} 查看结果。")


def append_msg_to_file(msg: str, output_file: str):
    with open(output_file, 'a', encoding="utf-8") as f:
        f.write(f"\n==Runtime Message ({format_time_now()})=={msg}")
        logging.debug(f"{msg.strip()}")


def configure_logging():
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "brief": {
                "format": "[%(asctime)s - %(name)s - %(levelname)s] - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S"
            },
            "precise": {
                "format": "[%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s] - %(message)s"
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "DEBUG",
                "formatter": "precise",
                "stream": "ext://sys.stdout"
            },
            "log_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "INFO",
                "formatter": "brief",
                "filename": LOG_FILE,
                "maxBytes": 1024000,
                "backupCount": 10,
                "encoding": "utf-8"
            }

        },
        "root": {
            "level": logging.DEBUG,
            "handlers": ["console", "log_file"]
        },
        "loggers": {
            "__check_user_exist": {
                "level": logging.ERROR,
                "handlers": ["console", "log_file"]
            }
        }
    }

    logging.config.dictConfig(logging_config)


def with_chat(question: str, output_file: str):
    if question is None or question.isspace() or question == "":
        logging.warning("请输入问题")
        return False

    logging.info(f"QUESTION: {question}.")
    append_msg_to_file("正在向 ChatGPT 请教，请耐心等待...\n", output_file)
    answer = ask_chatgpt(question)
    # answer = "============ Test ============="

    if answer is None:
        logging.error("运行出错")
        append_msg_to_file("访问 ChatGPT API 出错。\n", output_file)
    else:
        append_answer(answer, output_file)


def monitor_loop(output_file: str):
    last_modified = file_modified(output_file)

    while True:
        time.sleep(1)
        current_modified = file_modified(output_file)
        if current_modified <= last_modified:
            continue

        last_modified = current_modified
        question = None
        try:
            question = get_question(output_file)
        except ValueError as e:
            logging.debug(e)
            append_msg_to_file(f"{repr(e)}", output_file)

        question = clean_question(question)
        if not question:
            logging.debug("Blank question or runtime message. Ignored")
            continue

        if question in (":clear", "：clear"):
            logging.debug(f"clear file: {output_file}")
            clear_file(output_file)
            continue

        # 有参数
        if question.startswith((":save", "：save")):
            cmds = question.split()
            if len(cmds) not in (1, 2):
                logging.warning(f"Save chat history to file failed.")
                continue

            history_file = cmds[1] if len(cmds) == 2 else f"{format_time_now('%m%d_%H%M')}_{str(uuid.uuid4())[0:6]}"
            save_chat_history(output_file, history_file)
            continue

        logging.debug("File modified!")
        with_chat(question, output_file)


def main():
    if not os.path.exists(HISTORY_DIR):
        os.makedirs(HISTORY_DIR)
    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'w') as f:
            f.write(f"Created file by {os.path.abspath(__file__)} in {format_time_now()}")

    configure_logging()

    if not proxy_test():
        logging.error("proxy 无法连接，请检查代理连接后重试")
        append_msg_to_file("proxy 无法连接，请检查代理连接后重试", OUTPUT_FILE)
        return False

    append_msg_to_file(
        f"proxy 连接正常: http://{HTTP_PROXY_SERVER}:{HTTP_PROXY_PORT}\n{MAGIC_HINT_LINE}\n",
        OUTPUT_FILE
    )

    logging.warning(f"开始循环监听 {os.path.abspath(OUTPUT_FILE)} 文件")
    monitor_loop(OUTPUT_FILE)



if __name__ == '__main__':
    main()
    # test()
