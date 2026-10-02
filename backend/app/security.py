"""Same-origin API policy and headers, shared by success and error responses."""
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    "Cache-Control": "private, no-store",
}


class SecurityMiddleware:
    def __init__(self, app, settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def secured_send(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.update(SECURITY_HEADERS)
                if self.settings.app_env == "production":
                    headers["Strict-Transport-Security"] = "max-age=31536000"
            await send(message)

        headers = Headers(scope=scope)
        # Bound JSON parsing before Pydantic/auth; streamed images have their own cap.
        if scope["method"] in ("POST", "PUT", "PATCH", "DELETE") and not scope["path"].endswith("/photos"):
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                if len(body) + len(chunk) > 256 * 1024:
                    return await JSONResponse({"detail": "Payload exceeds the size limit"}, status_code=413)(
                        scope, receive, secured_send)
                body.extend(chunk)
                if not message.get("more_body", False):
                    break
            original_receive = receive
            delivered = False

            async def buffered_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await original_receive()

            receive = buffered_receive
        # Provider callbacks authenticate independently; never grant them browser CORS.
        callbacks = {"/api/ozon/webhook", "/api/telegram/webhook"}
        if scope["method"] not in ("GET", "HEAD", "OPTIONS") and scope["path"] not in callbacks:
            origin = headers.get("origin")
            expected = (self.settings.app_public_url.rstrip("/") if self.settings.app_env == "production"
                        else f"{scope['scheme']}://{headers.get('host', '')}")
            if origin and origin != expected:
                return await JSONResponse({"detail": "Invalid origin"}, status_code=403)(scope, receive, secured_send)
            if headers.get("sec-fetch-site") == "cross-site":
                return await JSONResponse({"detail": "Cross-site request denied"}, status_code=403)(scope, receive, secured_send)
        await self.app(scope, receive, secured_send)


def production_host(settings):
    return urlsplit(settings.app_public_url).hostname
