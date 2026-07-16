from . import adb, utils

PROXY_NAMESPACE = "global"
PROXY_KEY = "http_proxy"
PROXY_HOST = "global_http_proxy_host"
PROXY_PORT = "global_http_proxy_port"


def cmd_set(serial: str | None, host: str, port: int):
    utils.info(f"Setting proxy to {host}:{port}...")
    import shlex
    val = shlex.quote(f"{host}:{port}")
    adb.settings_put(serial, PROXY_NAMESPACE, PROXY_KEY, val)
    utils.success(f"Proxy set to {host}:{port}")


def cmd_get(serial: str | None, json_output: bool = False):
    raw = adb.settings_get(serial, PROXY_NAMESPACE, PROXY_KEY)
    if not raw or raw in ("null", ""):
        if json_output:
            utils.stdprint('{"proxy": null}')
        else:
            utils.info("No proxy configured")
        return

    if json_output:
        import json
        utils.stdprint(json.dumps({"proxy": raw}, indent=2))
    else:
        utils.success(f"Proxy: {raw}")


def cmd_clear(serial: str | None):
    utils.info("Clearing proxy...")
    adb.settings_put(serial, PROXY_NAMESPACE, PROXY_KEY, ":0")
    utils.success("Proxy cleared")
