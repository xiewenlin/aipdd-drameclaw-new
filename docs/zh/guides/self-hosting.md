<!-- lang-switch -->
[English](../../en/guides/self-hosting.md) · **简体中文**

# 自托管手册（Docker）

DramaClaw CE 默认运行 `api` 和 `web`。所有云模型统一连接到你配置的一个 NewAPI 服务。

## 启动

```bash
git clone https://github.com/dramaclaw/dramaclaw.git
cd dramaclaw
cp .env.example .env
docker compose up -d --build
```

建议至少 2 vCPU / 4 GB 内存；部署前修改 `.env` 中的密码类默认值。

## 配置模型

1. 打开 `http://localhost:8080` → 设置 → 模型配置。
2. 填写一个 NewAPI 地址和 API Key，测试连接。
3. 同步 `/models`。
4. 为每项功能绑定模型。无法分类的模型不会自动绑定，可从全部模型中手动选择。

所有项目共享该配置，不支持项目或请求覆盖。官方入口只是 [获取 NewAPI 服务](https://newapi.chonghuayunke.com) 的外链，获取后仍按上述流程填写地址和 Key。

如使用仓库附带的 NewAPI 容器：

```bash
docker compose -f docker-compose.selfhosted.yml up -d --build
```

在 NewAPI 自身管理上游渠道和映射，再将可访问地址和 runtime token 填入模型配置页。DramaClaw 不再提供云 Provider 直连配置。

## 运维与排错

```bash
docker compose ps
docker compose logs -f api
docker compose down
git pull
docker compose up -d --build
```

| 现象 | 排查 |
|---|---|
| 容器无法启动 | 查看 `docker compose logs api`。 |
| 模型同步失败 | 检查全局 NewAPI 地址、Key 和 `/models`。 |
| 功能无法调用 | 检查功能绑定并运行功能测试。 |
| Cognee 使用旧配置 | 按设置页提示重启 API。 |

## 相关

- [配置模型](../getting-started/configuring-models.md)
- [环境变量参考](../reference/environment-variables.md)