# -*- encoding: utf-8 -*-
# @Author      : Daxing Zheng
# @Email       : laiguanqixi@gmail.com
# @Author      : Jun Zhou
# @Email       : zj1355097307@outlook.com
# @File        : chat.py
# @Datetime    : 2023-03-02 09:23:19
# @Github      : https://github.com/PatrickZoo/ChatInMarkdown
# @Description :

import argparse
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
from urllib.parse import urlparse

# ssl._create_default_https_context = ssl._create_unverified_context

# OPENAI_URL = "https://api.openai.com/v1/chat/completions"

IGNORE_QUESTION = ["请另起一行输入问题:", "Runtime Message"]
MAGIC_HINT_LINE = "请另起一行输入问题:"
USAGE = r"""
### Question Format
#### 普通问题
读取文件最后不为空的那一行内容作为问题向 ChatGPT 提问

#### 代码问题格式如下
你好，帮我讲一下代码改为递归执行
```python
count = 0
for i in range(100):
    count += i
```

#### 数学问题格式如下
这段数学公式的结果是多少
$$
\sum_{i+1}^{n}(i^2)
$$

### Command
- :save to_file      保存 chatgpt.md 文件中的所有内容到指定文件，文件名默认为当前时间
- :clear             清除 chatgpt.md 文件中的所有内容
"""


def parse_arguments() -> argparse.Namespace:
    """
    由于 Python 不允许变量名使用连字符 "-",
    argparse 会将 'log-file' 自动转为 'log_file'
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--key', help='OpenAI API Key')
    parser.add_argument('--output', default='./chatgpt.md')
    parser.add_argument('--log-file', default='./chat.log')
    parser.add_argument('--log-level', default='info')
    parser.add_argument('--history', default='./history')
    parser.add_argument('--proxy', default='http://127.0.0.1:10809')
    parser.add_argument('--config', default='./config/config.json')
    parser.add_argument('--url', default='https://api.openai.com/v1/chat/completions')
    parser.add_argument('--show-tokens', action='store_true')
    parser.set_defaults(show_tokens=True)

    return parser.parse_args()


def parse_config_file(args: argparse.Namespace) -> argparse.Namespace:
    if not (hasattr(args, "config") and os.path.isfile(args.config)):
        return args
    
    config_mapping = {
        "openai-api-key": "key",
        "output-file": "output",
        "history-path": "history",
        "log-file": "log_file",
        "log-level": "log_level",
        "proxy": "proxy",
        "openai-url": "url",
        "show-tokens": "show_tokens"
    }

    # 读取本地配置文件内容
    with open(args.config, 'r', encoding="utf-8") as f:
        config = json.load(f)

    for key, value in config.items():
        if key not in config_mapping.keys():
            continue

        arg_name = config_mapping[key]
        setattr(args, arg_name, value)

    return args


def file_modified(filepath: str) -> float:
    st_mtime = os.stat(filepath).st_mtime
    return st_mtime


def append_msg_to_file(msg: str, output_file: str, _mode: str = 'a'):
    with open(output_file, mode=_mode, encoding='utf-8') as _f:
        _f.write(msg)


def append_answer(answer: str, output_file: str):
    msg = f"\n==ANSWER ({format_time_now()})==\n"
    msg += f"{answer}\n"
    msg += "== END OF ANSWER ==\n\n***\n"
    msg += f"{MAGIC_HINT_LINE}\n"
    append_msg_to_file(msg, output_file, _mode='a')
    logging.info(f"运行成功，请在 {output_file} 查看结果。")


def append_runtime_msg(msg: str, output_file: str):
    msg = f"\n==Runtime Message ({format_time_now()})== {msg}\n"
    append_msg_to_file(msg, output_file, _mode='a')
    logging.debug(f"{msg.strip()}")


def clear_file(filepath: str):
    msg = f"\n{USAGE}\n{MAGIC_HINT_LINE}\n"
    append_msg_to_file(msg, filepath, _mode='w')


def save_chat_history(filepath: str, new_history_file: str):
    """
    输入参数：
    filepath: 需要操作的文件地址
    new_history_file: 保存的文件名。默认值格式为: 月日_时分_UUID
    """
    # 重命名文件并移动到新的地址上
    os.rename(filepath, new_history_file)
    msg = f"{filepath} 中的内容已保存到 {new_history_file}"
    append_runtime_msg(msg, filepath)
    clear_file(filepath)



def get_connection_with_proxy(hostname:str, proxy:str) -> http.client.HTTPSConnection:
    """
    创建代理连接对象
    """
    proxy_param_obj = urlparse(proxy)

    if proxy_param_obj.scheme == "http":
        conn = http.client.HTTPSConnection(host=proxy_param_obj.netloc, context=ssl._create_unverified_context())
        conn.set_tunnel(hostname)  # 设置需要访问的目标服务器
    elif proxy_param_obj.scheme == "socks5":
        import socks, socket
        socks.set_default_proxy(socks.SOCKS5, proxy_param_obj.hostname, proxy_param_obj.port)
        socket.socket = socks.socksocket
        conn = http.client.HTTPSConnection(hostname, context=ssl._create_unverified_context())
    else:
        raise ValueError("Unsupported scheme of proxy.")

    return conn



def proxy_test(proxy: str) -> bool:

    try:
        conn = get_connection_with_proxy("google.com", proxy)
        conn.request("GET", "/")
        res = conn.getresponse()
        return True if res.status == 301 else False
    except Exception as e:
        logging.error(traceback.format_exc())
        return False


def gpt_connection_test(config: argparse.Namespace) -> bool:
    return with_chat("你好 ChatGPT", config)



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


def ask_chatgpt(question: str, config: argparse.Namespace) -> Optional[str]:
    _headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f"Bearer {config.key}"
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

    url = urlparse(config.url)

    try:
        conn = get_connection_with_proxy(url.hostname, config.proxy)
        conn.request("POST", url.path, body=payload, headers=_headers)
        res = conn.getresponse()
        _response = res.read().decode()
        _response = json.loads(_response)

        if "error" in _response:
            logging.error(_response)
            return _response
            # return f"运行出错: {_response['error']['message']}"

        # _response = requests.post(OPENAI_URL, headers=_headers, data=payload, proxies=PROXIES)
        # _response = _response.json()
        _answer = _response["choices"].pop()["message"]["content"]
        if config.show_tokens:
            usage_tokens = _response["usage"]["total_tokens"]
            _answer = f"{_answer}\n**本次API调用共消耗 {usage_tokens} tokens.**"

        return _answer
    except Exception as e:
        logging.debug(traceback.format_exc())
        return repr(e)



def configure_logging(log_file: str, log_level: str = "INFO"):
    log_level = log_level.upper()
    if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        log_level = "INFO"

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
                "filename": log_file,
                "maxBytes": 1024000,
                "backupCount": 10,
                "encoding": "utf-8"
            }

        },
        "root": {
            "level": log_level,
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


def with_chat(question: str, config: argparse.Namespace):
    output_file = config.output

    if question is None or question.isspace() or question == "":
        logging.warning("请输入问题")
        return False

    logging.info(f"QUESTION: {question}.")
    append_runtime_msg("正在向 ChatGPT 请教，请耐心等待...", output_file)
    answer = ask_chatgpt(question, config)
    # answer = "============ Test ============="

    if answer is None:
        logging.error("运行出错")
        append_runtime_msg("访问 ChatGPT API 出错。", output_file)
    elif "invalid_api_key" in str(answer):
        append_runtime_msg(
            f"Incorrect API key provided: {config.key}. You can find your API key at https://platform.openai.com/account/api-keys.",
            output_file
        )
        raise ValueError("Invalid API Key")
    else:
        append_answer(answer, output_file)


def monitor_loop(config: argparse.Namespace):
    output_file = config.output
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
            append_runtime_msg(f"{repr(e)}", output_file)

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

            history_file = cmds[1] if len(cmds) == 2 else f"{format_time_now('%Y%m%d_%H%M')}"
            history_file = os.path.join(config.history, history_file)
            save_chat_history(output_file, history_file)
            logging.info(f"All content in {output_file} has been backed up to {history_file}")
            continue

        logging.debug("File modified!")
        with_chat(question, config)


def main():
    
    args = parse_arguments()
    config = parse_config_file(args)
    configure_logging(config.log_file, config.log_level)
    logging.info("============ main starting ============")

    if not os.path.exists(config.history):
        os.makedirs(config.history)
    if not os.path.exists(config.output):
        with open(config.output, 'w') as f:
            f.write(f"Created file by {os.path.abspath(__file__)} in {format_time_now()}")


    if not proxy_test(config.proxy):
        logging.error("proxy 无法连接，请检查代理连接后重试")
        append_runtime_msg("proxy 无法连接，请检查代理连接后重试", config.output)
        return False

    append_runtime_msg(f"The proxy is connected correctly with {config.proxy}\n{MAGIC_HINT_LINE}", config.output)
    
    gpt_connection_test(config)

    logging.warning(f"开始循环监听 {os.path.abspath(config.output)} 文件")
    monitor_loop(config)



if __name__ == '__main__':
    main()

