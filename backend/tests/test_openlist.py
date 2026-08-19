"""OpenList 核心接口冒烟测试（无登录，本地部署）。"""


async def _create_task(client, name: str) -> dict:
    res = await client.post(
        "/api/openlist/tasks",
        json={"name": name, "output_dir": "/tv", "process_path": f"/emby/{name}"},
    )
    assert res.json()["code"] == 200, res.json()
    return res.json()["data"]


async def _create_preset(client, name: str) -> dict:
    res = await client.post(
        "/api/openlist/presets",
        json={"name": name, "preset_path": f"/emby/{name}", "sort_order": 0},
    )
    assert res.json()["code"] == 200, res.json()
    return res.json()["data"]


async def test_health(client):
    res = await client.get("/api/health")
    body = res.json()
    assert body["code"] == 200
    assert body["data"]["status"] == "ok"


async def test_openlist_config_auto_seeded(client):
    """启动自动 seed 默认全局配置。"""
    res = await client.get("/api/openlist/config")
    body = res.json()
    assert body["code"] == 200
    assert body["data"]["max_concurrent"] >= 1


async def test_server_crud(client):
    res = await client.post(
        "/api/openlist/servers",
        json={"name": "本机", "server_url": "http://127.0.0.1:5244", "token": "test-token"},
    )
    server = res.json()["data"]
    assert server["id"] > 0
    res = await client.get("/api/openlist/servers")
    ids = [s["id"] for s in res.json()["data"]["list"]]
    assert server["id"] in ids


async def test_task_batch_delete(client):
    t1 = await _create_task(client, "任务A")
    t2 = await _create_task(client, "任务B")
    res = await client.post(
        "/api/openlist/tasks/batch-delete",
        json={"ids": [t1["id"], t2["id"]]},
    )
    assert res.json()["code"] == 200, res.json()
    res = await client.get("/api/openlist/tasks")
    remaining = {t["id"] for t in res.json()["data"]["list"]}
    assert not ({t1["id"], t2["id"]} & remaining)


async def test_task_batch_delete_missing_id_rolls_back(client):
    t1 = await _create_task(client, "任务C")
    res = await client.post(
        "/api/openlist/tasks/batch-delete",
        json={"ids": [t1["id"], 999999]},
    )
    assert res.json()["code"] == 404
    res = await client.get("/api/openlist/tasks")
    remaining = {t["id"] for t in res.json()["data"]["list"]}
    assert t1["id"] in remaining


async def test_preset_batch_delete(client):
    p1 = await _create_preset(client, "预设X")
    p2 = await _create_preset(client, "预设Y")
    res = await client.post(
        "/api/openlist/presets/batch-delete",
        json={"ids": [p1["id"], p2["id"]]},
    )
    assert res.json()["code"] == 200, res.json()
    res = await client.get("/api/openlist/presets")
    remaining = {p["id"] for p in res.json()["data"]["list"]}
    assert not ({p1["id"], p2["id"]} & remaining)


async def test_execution_create_and_cancel(client):
    task = await _create_task(client, "执行测试")
    res = await client.post(
        "/api/openlist/servers",
        json={"name": "本机", "server_url": "http://127.0.0.1:5244", "token": "t"},
    )
    server_id = res.json()["data"]["id"]
    res = await client.post(
        "/api/openlist/executions",
        json={"task_id": task["id"], "server_id": server_id},
    )
    execution = res.json()["data"]
    assert execution["status"] == "running"
    res = await client.post(
        "/api/openlist/executions/cancel",
        json={"execution_id": execution["id"]},
    )
    assert res.json()["data"]["cancelled"] is True
