import json
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


class ApiError(RuntimeError):
    pass


class CentralApiClient:
    def __init__(
        self,
        auth_base_url: Optional[str] = None,
        game_base_url: Optional[str] = None,
        timeout: int = 15,
    ) -> None:
        self.auth_base_url = (
            auth_base_url
            or os.getenv("SUBSCRIPTION_CENTER_BASE")
            or "http://172.30.4.21:8001"
        ).rstrip("/")
        self.game_base_url = (
            game_base_url
            or os.getenv("GAME_BACKEND_BASE")
            or "http://172.30.4.21:8002"
        ).rstrip("/")
        self.timeout = timeout
        self.auth_access_token: Optional[str] = None
        self.auth_refresh_token: Optional[str] = None
        self.product_access_token: Optional[str] = None
        self.product_refresh_token: Optional[str] = None
        self.product_session_no: Optional[str] = None
        self.device_fingerprint: Optional[str] = None
        self.device_profile: Dict[str, str] = {}

    def set_auth_tokens(
        self,
        access_token: Optional[str],
        refresh_token: Optional[str],
    ) -> None:
        self.auth_access_token = access_token
        self.auth_refresh_token = refresh_token

    def set_product_session(
        self,
        access_token: Optional[str],
        refresh_token: Optional[str],
        session_no: Optional[str],
        device_fingerprint: Optional[str] = None,
    ) -> None:
        self.product_access_token = access_token
        self.product_refresh_token = refresh_token
        self.product_session_no = session_no
        if device_fingerprint:
            self.device_fingerprint = device_fingerprint

    def clear_product_session(self) -> None:
        self.product_access_token = None
        self.product_refresh_token = None
        self.product_session_no = None

    def set_device_profile(self, device_profile: Dict[str, str]) -> None:
        self.device_profile = dict(device_profile)
        self.device_fingerprint = device_profile.get("deviceFingerprint")

    def register(
        self,
        username: str,
        email: str,
        phone: str,
        password: str,
        nickname: str,
        register_source: str = "DESKTOP",
    ) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/auth/register",
            service="auth",
            json_body={
                "username": username,
                "email": email,
                "phone": phone,
                "password": password,
                "nickname": nickname,
                "registerSource": register_source,
            },
        )

    def login(
        self,
        login_account: str,
        password: str,
        client_type: str,
        product_code: str,
        login_ip: str,
    ) -> Dict[str, Any]:
        payload = self._request(
            "POST",
            "/api/v1/auth/login",
            service="auth",
            json_body={
                "loginAccount": login_account,
                "password": password,
                "clientType": client_type,
                "productCode": product_code,
                "loginIp": login_ip,
            },
        )
        self._capture_auth_tokens(payload)
        return payload

    def refresh_auth_token(self) -> Dict[str, Any]:
        if not self.auth_refresh_token:
            raise ApiError("缺少登录态 refresh token")
        payload = self._request(
            "POST",
            "/api/v1/auth/refresh-token",
            service="auth",
            json_body={"refreshToken": self.auth_refresh_token},
        )
        self._capture_auth_tokens(payload)
        return payload

    def refresh_product_token(self) -> Dict[str, Any]:
        if not self.product_refresh_token:
            raise ApiError("缺少产品态 refresh token")
        payload = self._request(
            "POST",
            "/api/v1/auth/refresh-token",
            service="auth",
            json_body={"refreshToken": self.product_refresh_token},
        )
        self._capture_product_tokens(payload)
        return payload

    def logout(self, session_no: Optional[str] = None) -> Dict[str, Any]:
        body = {"sessionNo": session_no} if session_no else None
        return self._request(
            "POST",
            "/api/v1/auth/logout",
            service="auth",
            auth=True,
            token_scope="product" if self.product_access_token else "auth",
            json_body=body,
        )

    def get_current_account(self) -> Dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/auth/me",
            service="auth",
            auth=True,
            token_scope="auth",
        )

    def upsert_device(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/devices/upsert",
            service="auth",
            auth=True,
            token_scope="auth",
            json_body=payload,
        )

    def get_current_subscription(self, product_code: str) -> Dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/subscriptions/current",
            service="auth",
            auth=True,
            token_scope="auth",
            query={"productCode": product_code},
        )

    def open_trial(
        self,
        product_code: str,
        device_fingerprint: str,
        client_type: str,
        request_id: str,
    ) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/subscriptions/trial/open",
            service="auth",
            auth=True,
            token_scope="auth",
            json_body={
                "productCode": product_code,
                "deviceFingerprint": device_fingerprint,
                "clientType": client_type,
                "requestId": request_id,
            },
        )

    def enter_product(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = self._request(
            "POST",
            "/api/v1/sessions/enter-product",
            service="auth",
            auth=True,
            token_scope="auth",
            json_body=payload,
        )
        self._capture_product_tokens(response)
        return response

    def check_access(
        self,
        product_code: str,
        session_no: str,
        device_fingerprint: str,
    ) -> Dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/subscriptions/access/check",
            service="auth",
            auth=True,
            token_scope="product",
            query={
                "productCode": product_code,
                "sessionNo": session_no,
                "deviceFingerprint": device_fingerprint,
            },
        )

    def create_payment_order(
        self,
        product_code: str,
        plan_code: str,
        order_type: int,
    ) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/payments/orders",
            service="auth",
            auth=True,
            token_scope="auth",
            json_body={
                "productCode": product_code,
                "planCode": plan_code,
                "orderType": order_type,
            },
        )

    def list_draws(self, limit: int = 10) -> List[Dict[str, Any]]:
        payload = self._request(
            "GET",
            "/api/v1/game-of-number/draws/latest",
            service="game",
            auth=True,
            token_scope="product",
            query={"limit": limit},
        )
        return self._unwrap_list(payload)

    def get_recent_stats(self, days: int = 7) -> Dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/game-of-number/stats/recent-days",
            service="game",
            auth=True,
            token_scope="product",
            query={"days": days},
        )

    def list_predictions(self, limit: int = 50) -> List[Dict[str, Any]]:
        payload = self._request(
            "GET",
            "/api/v1/game-of-number/predictions",
            service="game",
            auth=True,
            token_scope="product",
            query={"limit": limit},
        )
        return self._unwrap_list(payload)

    def save_prediction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/game-of-number/predictions",
            service="game",
            auth=True,
            token_scope="product",
            json_body=payload,
        )

    def update_prediction_verification(
        self,
        code: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._request(
            "PUT",
            f"/api/v1/game-of-number/predictions/{urllib.parse.quote(code)}",
            service="game",
            auth=True,
            token_scope="product",
            json_body=payload,
        )

    def get_draw_by_code(self, code: str) -> Dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/game-of-number/draws/by-code",
            service="game",
            auth=True,
            token_scope="product",
            query={"code": code},
        )

    def _request(
        self,
        method: str,
        path: str,
        service: str,
        query: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        auth: bool = False,
        token_scope: str = "auth",
        retry_on_product_reauth: bool = True,
    ) -> Dict[str, Any]:
        base_url = self.auth_base_url if service == "auth" else self.game_base_url
        url = f"{base_url}{path}"
        if query:
            params = {key: value for key, value in query.items() if value is not None}
            url = f"{url}?{urllib.parse.urlencode(params)}"
        headers = {"Accept": "application/json"}
        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if auth:
            token = self._get_token(token_scope)
            if not token:
                raise ApiError("当前缺少可用登录态")
            headers["Authorization"] = f"Bearer {token}"
        if token_scope == "product":
            if not self.product_session_no:
                raise ApiError("当前缺少产品会话，请重新登录")
            headers["X-Session-No"] = self.product_session_no
            if not self.device_fingerprint:
                raise ApiError("当前缺少设备指纹，请重新登录")
            headers["X-Device-Fingerprint"] = self.device_fingerprint
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            error_message = self._extract_error_message(body) or f"请求失败: HTTP {exc.code}"
            if (
                service == "game"
                and token_scope == "product"
                and retry_on_product_reauth
                and self._should_reenter_product(exc.code, error_message)
            ):
                self.reenter_product_session()
                return self._request(
                    method=method,
                    path=path,
                    service=service,
                    query=query,
                    json_body=json_body,
                    auth=auth,
                    token_scope=token_scope,
                    retry_on_product_reauth=False,
                )
            raise ApiError(
                error_message
            ) from exc
        except urllib.error.URLError as exc:
            raise ApiError(f"无法连接{self._service_name(service)}: {exc.reason}") from exc
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ApiError(f"中心服务返回了非 JSON 响应: {raw[:120]}") from exc
        if isinstance(payload, dict) and payload.get("success") is False:
            raise ApiError(str(payload.get("message") or "中心服务返回失败"))
        return payload if isinstance(payload, dict) else {"data": payload}

    def reenter_product_session(self) -> None:
        if not self.auth_access_token:
            raise ApiError("登录态已失效，请重新登录")
        if not self.device_profile:
            raise ApiError("缺少设备信息，请重新登录")
        self.enter_product(
            {
                "productCode": self.device_profile.get("productCode", "GAME_OF_NUMBER"),
                "clientType": self.device_profile.get("clientType", "DESKTOP"),
                "deviceFingerprint": self.device_profile["deviceFingerprint"],
                "installId": self.device_profile["installId"],
                "loginIp": self.device_profile.get("loginIp", "127.0.0.1"),
                "userAgent": "PyQt6 Desktop Client",
                "concurrencyStrategy": "KICK_OLD",
                "requestId": self.device_profile.get("requestId", "enter-product-retry"),
            }
        )

    def _should_reenter_product(self, status_code: int, message: str) -> bool:
        normalized = message.lower()
        return status_code in (401, 403) and (
            "current product session is not available" in normalized
            or "missing required header: x-session-no" in normalized
            or "session" in normalized
        )

    def _get_token(self, token_scope: str) -> Optional[str]:
        if token_scope == "product":
            return self.product_access_token
        return self.auth_access_token

    def _capture_auth_tokens(self, payload: Dict[str, Any]) -> None:
        token_data = payload.get("data", payload)
        access_token = token_data.get("accessToken")
        refresh_token = token_data.get("refreshToken")
        if access_token:
            self.auth_access_token = access_token
        if refresh_token:
            self.auth_refresh_token = refresh_token

    def _capture_product_tokens(self, payload: Dict[str, Any]) -> None:
        token_data = payload.get("data", payload)
        access_token = token_data.get("accessToken")
        refresh_token = token_data.get("refreshToken")
        session_no = token_data.get("sessionNo")
        if access_token:
            self.product_access_token = access_token
        if refresh_token:
            self.product_refresh_token = refresh_token
        if session_no:
            self.product_session_no = str(session_no)

    def _unwrap_list(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = payload.get("data", payload)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("records", "items", "list"):
                value = data.get(key)
                if isinstance(value, list):
                    return value
        return []

    def _service_name(self, service: str) -> str:
        if service == "game":
            return "数字游戏后端服务"
        return "订阅中心"

    def _extract_error_message(self, body: str) -> Optional[str]:
        if not body:
            return None
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return body.strip()[:160]
        if isinstance(payload, dict):
            if payload.get("message"):
                return str(payload["message"])
            if isinstance(payload.get("error"), str):
                return payload["error"]
        return None
