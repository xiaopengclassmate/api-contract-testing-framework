"""可选的第三方公开 API 契约测试（需要外网，默认不进入 CI 主流程）。"""

from __future__ import annotations

import allure
import pytest
import requests

from utils.contract import validate_schema

BASE_URL = "https://jsonplaceholder.typicode.com"


@allure.feature("第三方 API 契约")
@pytest.mark.external
class TestJsonPlaceholder:
    @allure.title("GET /posts/1 返回符合 Post 契约的 JSON")
    def test_get_post_contract(self):
        response = requests.get(f"{BASE_URL}/posts/1", timeout=15)
        assert response.status_code == 200
        validate_schema(response.json(), "post.json")

    @allure.title("POST /posts 回显创建内容且符合契约")
    def test_create_post_contract(self):
        payload = {
            "userId": 7,
            "title": "contract-testing-demo",
            "body": "created by api-contract-testing-framework",
        }
        response = requests.post(
            f"{BASE_URL}/posts", json=payload, timeout=15
        )
        assert response.status_code == 201

        body = response.json()
        validate_schema(body, "post.json")
        assert body["title"] == payload["title"]
        assert body["body"] == payload["body"]
