"""OpenList 核心接口冒烟测试（无登录，本地部署）。"""

from app.business.openlist import service as service_module


class FakeOpenListAPI:
    """模拟 OpenList API：记录调用次数，/bad 目录不存在，/emby 下有两个子目录。"""

    list_calls = 0

    def __init__(self, base_url, token="", verify_ssl=False):
        self.base_url = base_url
        self.token = token
        self.verify = verify_ssl

    async def list_files(self, path, **kwargs):
        type(self).list_calls += 1
        if path == "/bad":
            raise Exception("not found")
        if path == "/emby":
            return {
                "content": [
                    {"name": "电视剧", "path": "/emby/电视剧", "is_dir": True, "modified": 1700000000000},
                    {"name": "电影", "path": "/emby/电影", "is_dir": True, "modified": 1700000000001},
                    {"name": "readme.txt", "path": "/emby/readme.txt", "is_dir": False},
                ]
            }
        return {"content": []}

    async def create_dir(self, path):
        return True

    async def remove_path(self, path):
        return True


async def _reset_fake():
    FakeOpenListAPI.list_calls = 0


async def _create_task(client, name: str) -> dict:
    res = await client.post(
        "/api/openlist/tasks",
        # server_id=1 为 seed 自动创建的默认服务器
        json={"name": name, "output_dir": "/tv", "process_path": f"/emby/{name}", "server_id": 1},
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


# ---------- 父级目录配置 / 校验 / 目录缓存 ----------

async def test_server_parent_dirs_crud(client, monkeypatch):
    """父级目录：保存返回、更新替换、删除清理。"""
    monkeypatch.setattr(service_module, "OpenListAPI", FakeOpenListAPI)
    await _reset_fake()
    res = await client.post(
        "/api/openlist/servers",
        json={
            "name": "主库",
            "server_url": "http://127.0.0.1:5244",
            "token": "t",
            "parent_dirs": ["/emby", "/music"],
            "skip_validation": True,
        },
    )
    body = res.json()
    assert body["code"] == 200, body
    server_id = body["data"]["id"]
    assert body["data"]["parent_dirs"] == ["/emby", "/music"]

    # 服务器列表也返回父级目录
    res = await client.get("/api/openlist/servers")
    item = next(s for s in res.json()["data"]["list"] if s["id"] == server_id)
    assert item["parent_dirs"] == ["/emby", "/music"]

    # 更新替换父级目录
    res = await client.post(
        f"/api/openlist/servers/{server_id}",
        json={"parent_dirs": ["/emby"], "skip_validation": True},
    )
    assert res.json()["code"] == 200
    assert res.json()["data"]["parent_dirs"] == ["/emby"]

    # 删除后列表不再返回
    res = await client.post("/api/openlist/servers/delete", json={"id": server_id})
    assert res.json()["code"] == 200
    res = await client.get("/api/openlist/servers")
    assert not any(s["id"] == server_id for s in res.json()["data"]["list"])


async def test_server_parent_dir_format_validation(client, monkeypatch):
    """不带 / 自动补全前缀；含 .. 或非法字符仍拒绝保存。"""
    monkeypatch.setattr(service_module, "OpenListAPI", FakeOpenListAPI)
    # 不写 / 自动补全（emby -> /emby），校验通过并规范化存储
    res = await client.post(
        "/api/openlist/servers",
        json={"server_url": "http://x", "token": "t", "parent_dirs": ["emby"]},
    )
    assert res.json()["code"] == 200, res.json()
    assert res.json()["data"]["parent_dirs"] == ["/emby"]
    # 非法路径：.. 、非法字符
    for bad in ["/emby/../x", "/emby\\x"]:
        res = await client.post(
            "/api/openlist/servers",
            json={"server_url": "http://x", "parent_dirs": [bad]},
        )
        assert res.json()["code"] == 400, f"{bad} -> {res.json()}"


async def test_server_parent_dir_validation_fail(client, monkeypatch):
    """存在性/读写校验失败（/bad 不存在）时阻止保存并给出错误原因。"""
    monkeypatch.setattr(service_module, "OpenListAPI", FakeOpenListAPI)
    res = await client.post(
        "/api/openlist/servers",
        json={"server_url": "http://x", "token": "t", "parent_dirs": ["/bad"]},
    )
    body = res.json()
    assert body["code"] == 400
    assert "校验失败" in body["msg"]
    # 未保存成功（seed 的默认服务器仍在，但该 url 不应出现）
    res = await client.get("/api/openlist/servers")
    assert not any(s["server_url"] == "http://x" for s in res.json()["data"]["list"])


async def test_server_skip_validation(client, monkeypatch):
    """跳过校验时允许保存（服务器暂时不可达等场景）。"""
    monkeypatch.setattr(service_module, "OpenListAPI", FakeOpenListAPI)
    res = await client.post(
        "/api/openlist/servers",
        json={"server_url": "http://x", "token": "t", "parent_dirs": ["/bad"], "skip_validation": True},
    )
    assert res.json()["code"] == 200


async def test_server_dirs_cache_priority(client, monkeypatch):
    """校验通过后自动缓存一级子目录；dirs 查询缓存优先，refresh 强制回源。"""
    monkeypatch.setattr(service_module, "OpenListAPI", FakeOpenListAPI)
    await _reset_fake()
    res = await client.post(
        "/api/openlist/servers",
        json={"server_url": "http://127.0.0.1:5244", "token": "t", "parent_dirs": ["/emby"]},
    )
    server_id = res.json()["data"]["id"]
    # 创建时：校验 list_files(1) + 预缓存 list_files(1) = 2 次
    calls_after_create = FakeOpenListAPI.list_calls
    assert calls_after_create == 2

    # 查询命中缓存：不再发起服务器请求，且含名称/路径/最后修改时间
    res = await client.get(f"/api/openlist/servers/{server_id}/dirs")
    body = res.json()
    assert body["code"] == 200
    dirs = body["data"]["list"]
    assert [d["name"] for d in dirs] == ["电视剧", "电影"]
    assert dirs[0]["path"] == "emby/电视剧"
    assert dirs[0]["modified"]
    assert FakeOpenListAPI.list_calls == calls_after_create

    # 手动刷新：强制回源
    res = await client.post(f"/api/openlist/servers/{server_id}/dirs/refresh", json={"path": "/emby"})
    assert res.json()["code"] == 200
    assert res.json()["data"]["count"] == 2
    assert FakeOpenListAPI.list_calls == calls_after_create + 1


async def test_dir_execution_create_and_cancel(client, monkeypatch):
    """目录执行：task_id=0 + 快照字段；取消按 execution_id。"""
    monkeypatch.setattr(service_module, "OpenListAPI", FakeOpenListAPI)
    res = await client.post(
        "/api/openlist/servers",
        json={"server_url": "http://127.0.0.1:5244", "token": "t", "skip_validation": True},
    )
    server_id = res.json()["data"]["id"]
    res = await client.post(
        "/api/openlist/executions/dirs",
        json={
            "server_id": server_id,
            "dirs": [
                {"path": "emby/电视剧", "output_dir": "/电视剧"},
                {"path": "emby/电影", "output_dir": "/电影"},
            ],
        },
    )
    body = res.json()
    assert body["code"] == 200, body
    executions = body["data"]["list"]
    assert len(executions) == 2
    first = executions[0]
    assert first["task_id"] == 0
    assert first["task_name"] == "电视剧"
    assert first["process_path"] == "emby/电视剧"
    assert first["output_dir"] == "/电视剧"

    # 任务历史聚合出现「目录执行」分组
    res = await client.get("/api/openlist/history")
    groups = res.json()["data"]["list"]
    assert any(g["task_id"] == 0 and g["task_name"] == "目录执行" for g in groups)

    # 取消（task_id=0 → 按 execution_id 取消）
    res = await client.post("/api/openlist/executions/cancel", json={"execution_id": first["id"]})
    assert res.json()["data"]["cancelled"] is True


# ---------- 任务强关联服务器 ----------

async def test_task_server_filter(client):
    """任务带服务器信息，可按服务器筛选。"""
    await _create_task(client, "任务S1")  # seed 服务器 id=1
    res = await client.post(
        "/api/openlist/servers",
        json={"server_url": "http://s2", "token": "t", "skip_validation": True},
    )
    sid2 = res.json()["data"]["id"]
    res = await client.post(
        "/api/openlist/tasks",
        json={"name": "任务S2", "output_dir": "/tv", "process_path": "/x", "server_id": sid2},
    )
    assert res.json()["code"] == 200, res.json()

    # 任务列表带服务器信息
    res = await client.get("/api/openlist/tasks")
    item = next(t for t in res.json()["data"]["list"] if t["name"] == "任务S1")
    assert item["server_id"] == 1 and item["server_url"]

    # 按服务器筛选
    res = await client.get("/api/openlist/tasks", params={"server_id": 1})
    names = [t["name"] for t in res.json()["data"]["list"]]
    assert "任务S1" in names and "任务S2" not in names
    res = await client.get("/api/openlist/tasks", params={"server_id": sid2})
    names = [t["name"] for t in res.json()["data"]["list"]]
    assert names == ["任务S2"]


async def test_execution_server_mismatch(client):
    """执行时任务与服务器不匹配应被拒绝（强关联）。"""
    res = await client.post(
        "/api/openlist/servers",
        json={"server_url": "http://s2", "token": "t", "skip_validation": True},
    )
    sid2 = res.json()["data"]["id"]
    res = await client.post(
        "/api/openlist/tasks",
        json={"name": "错配任务", "output_dir": "/tv", "process_path": "/x", "server_id": sid2},
    )
    tid = res.json()["data"]["id"]
    # 用 seed 服务器（id=1）执行任务（属于服务器2）→ 400
    res = await client.post("/api/openlist/executions", json={"task_id": tid, "server_id": 1})
    assert res.json()["code"] == 400
    assert "不匹配" in res.json()["msg"]
