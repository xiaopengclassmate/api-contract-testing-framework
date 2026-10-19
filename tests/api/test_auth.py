from __future__ import annotations

from datetime import datetime, timedelta, timezone

import allure
import jwt
import pytest

from app import settings
from utils.contract import validate_schema


@allure.feature("认证")
@allure.story("JWT 登录")
@pytest.mark.smoke
class TestAuth:
    @allure.title("正确账号密码可以换取 JWT")
    def test_login_success(self, anonymous_client):
        response = anonymous_client.post(
            "/api/v1/auth/token",
            json={
                "username": settings.ADMIN_USERNAME,
                "password": settings.ADMIN_PASSWORD,
            },
            expected_status=200,
        )

        body = response.json()
        validate_schema(body, "token.json")
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == settings.JWT_EXPIRE_MINUTES * 60

    @allure.title("错误密码返回 401")
    @pytest.mark.parametrize(
        ("username", "password"),
        [
            (settings.ADMIN_USERNAME, "wrong-password"),
            ("unknown-user", settings.ADMIN_PASSWORD),
        ],
        ids=["wrong-password", "unknown-user"],
    )
    def test_login_invalid_credentials(
        self, anonymous_client, username, password
    ):
        response = anonymous_client.post(
            "/api/v1/auth/token",
            json={"username": username, "password": password},
            expected_status=401,
        )

        body = response.json()
        validate_schema(body, "error.json")
        assert body["detail"] == "Invalid username or password"

    @allure.title("未携带 Token 访问订单接口返回 401")
    def test_orders_require_token(self, anonymous_client):
        response = anonymous_client.get(
            "/api/v1/orders", expected_status=401
        )

        validate_schema(response.json(), "error.json")
        assert "bearer" in response.json()["detail"].lower()

    @allure.title("伪造 Token 返回 401")
    def test_invalid_token(self, anonymous_client):
        response = anonymous_client.get(
            "/api/v1/orders",
            headers={"Authorization": "Bearer not-a-jwt"},
            expected_status=401,
        )

        validate_schema(response.json(), "error.json")

    @allure.title("过期 Token 返回 401")
    def test_expired_token(self, anonymous_client):
        now = datetime.now(timezone.utc)
        expired = jwt.encode(
            {
                "sub": settings.ADMIN_USERNAME,
                "iat": now - timedelta(hours=2),
                "exp": now - timedelta(hours=1),
            },
            settings.JWT_SECRET,
            algorithm=settings.JWT_ALGORITHM,
        )

        response = anonymous_client.get(
            "/api/v1/orders",
            headers={"Authorization": f"Bearer {expired}"},
            expected_status=401,
        )

        validate_schema(response.json(), "error.json")

    @allure.title("签名有效但缺少 sub 的 Token 返回 401")
    def test_token_without_subject(self, anonymous_client):
        token = jwt.encode(
            {
                "exp": datetime.now(timezone.utc)
                + timedelta(minutes=5)
            },
            settings.JWT_SECRET,
            algorithm=settings.JWT_ALGORITHM,
        )

        response = anonymous_client.get(
            "/api/v1/orders",
            headers={"Authorization": f"Bearer {token}"},
            expected_status=401,
        )

        assert response.json()["detail"] == "Invalid token payload"

    @allure.title("健康检查无需鉴权")
    def test_health(self, anonymous_client):
        response = anonymous_client.get("/health", expected_status=200)
        assert response.json() == {"status": "ok"}
