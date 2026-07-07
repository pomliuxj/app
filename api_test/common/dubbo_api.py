import json
import socket
import logging

logger = logging.getLogger(__name__)


class Dubbo:
    """Dubbo 协议客户端 — 通过原生 socket 连接 Dubbo Telnet 端口。

    ``telnetlib`` 在 Python 3.11 废弃、3.13 移除，这里直接用 socket 实现，
    避免额外依赖。
    """

    __init = False
    __encoding = "utf-8"
    __finish = "dubbo>"
    __connect_timeout = 10
    __read_timeout = 10

    def __init__(self, host, port):
        self.host = host
        self.port = port
        if host is not None and port is not None:
            self.__init = True

    def set_finish(self, finish):
        """设置 Dubbo 命令提示符，默认 ``dubbo>``"""
        self.__finish = finish

    def set_encoding(self, encoding):
        """设置响应解码字符集"""
        self.__encoding = encoding

    def set_connect_timeout(self, timeout):
        """连接超时（秒），默认 10"""
        self.__connect_timeout = timeout

    def set_read_timeout(self, timeout):
        """读取超时（秒），默认 10"""
        self.__read_timeout = timeout

    # ── 内部 socket 通信 ──────────────────────────────────────────────
    def _connect(self):
        """建立 socket 连接并返回 socket 对象。"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.__connect_timeout)
        try:
            sock.connect((self.host, self.port))
        except (socket.error, OSError) as err:
            logger.info("[host:%s port:%s] %s", self.host, self.port, err)
            raise ConnectionError(f"telnet timeout: {err}")
        return sock

    @staticmethod
    def _recv_all(sock: socket.socket, finish_bytes: bytes, timeout: float) -> str:
        """从 socket 读取数据直到出现 ``finish_bytes`` 或超时。"""
        sock.settimeout(timeout)
        data = b""
        while finish_bytes not in data:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
            except socket.timeout:
                break
        # 尝试 UTF-8 解码，失败则用 GBK
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("gbk", errors="replace")

    # ── 公共方法 ──────────────────────────────────────────────────────
    def do(self, command: str):
        """向 Dubbo 服务器发送命令并返回响应。"""
        sock = None
        try:
            sock = self._connect()

            # 触发 dubbo 提示符
            sock.sendall(b"\n")
            self._recv_all(sock, self.__finish.encode("utf-8"), self.__read_timeout)

            # 发送命令
            logger.info("DUBBO start")
            sock.sendall(command.encode("utf-8") + b"\n")

            # 读取响应 — 直到 dubbo> 提示符再次出现
            data = self._recv_all(sock, self.__finish.encode("utf-8"), self.__read_timeout)
            data = data.split("\n")[0]
            logger.info("DUBBO Response: %s", data)

            # 尝试 JSON 解析
            if data.startswith("{") or data.startswith("["):
                try:
                    return json.loads(data)
                except json.JSONDecodeError:
                    return data
            return data

        except ConnectionError as e:
            return {"msg": str(e)}
        finally:
            if sock:
                sock.close()

    def invoke(self, interface: str, param: str):
        """invoke 命令封装: ``invoke <interface>(<param>)``"""
        cmd = f"invoke {interface}({param})"
        logger.info(cmd)
        return self.do(cmd)
